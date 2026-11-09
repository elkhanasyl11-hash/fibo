"""Fibo AI Client — standalone typed HTTP client for the Fibo AI service (22 endpoints).

Why this shape:
  - one private `_call()` does every request, so timeouts, retries and error parsing are identical
    for all endpoints;
  - errors become `FiboAIError(status, code, message, retriable, details)`, parsed from the service
    envelope `{"error": {code, message, retriable, details}}`; transport failures become
    `code="UNREACHABLE"` (status 0). `retake_advice_ru/kk` stay inside `details`;
  - at most 2 retries (waits 0.5 s, 1.5 s) and only for transport errors, HTTP 429 and 5xx — an input
    error (4xx) gives the same answer on retry, so it is never retried;
  - per-endpoint timeouts: incident analyze 12 s, vision 8 s, transcription 6 s, manual index 15 s,
    everything else 5 s;
  - `None` fields are left out of request bodies (the service forbids unknown fields and some reject null).
Request field names follow AI_INTEGRATION.md and the Phase-0 client generated from the service OpenAPI.
"""

import asyncio
from typing import Any

import httpx

RETRY_WAITS_S = (0.5, 1.5)
DEFAULT_TIMEOUT_S = 5.0
TIMEOUTS_S = {  # path prefix -> seconds (first match wins)
    "/v1/incident/analyze": 12.0,
    "/v1/vision/": 8.0,
    "/v1/speech/transcribe": 6.0,
    "/v1/manuals/index": 15.0,
}


class FiboAIError(Exception):
    """An error answer from the AI service, or a transport failure (status 0, code UNREACHABLE)."""

    def __init__(self, status: int, code: str, message: str, retriable: bool, details: dict) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message = status, code, message
        self.retriable, self.details = retriable, details


def timeout_for(path: str) -> float:
    return next((seconds for prefix, seconds in TIMEOUTS_S.items() if path.startswith(prefix)), DEFAULT_TIMEOUT_S)


def parse_error(response: httpx.Response) -> FiboAIError:
    """Read the service error envelope; anything else becomes code HTTP_<status>."""
    try:
        error = response.json()["error"]
        details = dict(error.get("details") or {})
        for key in ("retake_advice_ru", "retake_advice_kk", "issues"):  # keep advice with the details
            if key in error and key not in details:
                details[key] = error[key]
        return FiboAIError(
            response.status_code,
            str(error["code"]),
            str(error.get("message", "")),
            bool(error.get("retriable", False)),
            details,
        )
    except (ValueError, KeyError, TypeError):
        return FiboAIError(response.status_code, f"HTTP_{response.status_code}", response.text[:200], False, {})


def should_retry(error: FiboAIError) -> bool:
    return error.status == 0 or error.status == 429 or error.status >= 500


def _clean(body: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in body.items() if value is not None}


class FiboAIClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8001",
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_waits: tuple[float, ...] = RETRY_WAITS_S,
    ) -> None:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.client = httpx.AsyncClient(base_url=base_url.rstrip("/"), headers=headers, transport=transport)
        self.retry_waits = retry_waits

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> "FiboAIClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        for attempt in range(len(self.retry_waits) + 1):
            try:
                response = await self.client.request(method, path, json=body, timeout=timeout_for(path))
            except httpx.HTTPError as exc:
                error = FiboAIError(0, "UNREACHABLE", type(exc).__name__, True, {})
            else:
                if response.status_code < 400:
                    return response.json()
                error = parse_error(response)
            if attempt < len(self.retry_waits) and should_retry(error):
                await asyncio.sleep(self.retry_waits[attempt])
                continue
            raise error
        raise AssertionError("unreachable")

    # --- health and meta ---------------------------------------------------------------------
    async def get_health(self) -> dict[str, Any]:
        return await self._call("GET", "/healthz")

    async def get_ready(self) -> dict[str, Any]:
        return await self._call("GET", "/readyz")

    async def get_models_meta(self) -> dict[str, Any]:
        return await self._call("GET", "/v1/meta/models")

    # --- risk --------------------------------------------------------------------------------
    async def predict_risk(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._call("POST", "/v1/risk/predict", data)

    async def rank_machines(self, machines: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._call("POST", "/v1/risk/rank", {"machines": machines})

    async def what_if(self, machine_id: str, current: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
        body = {"machine_id": machine_id, "current": current, "overrides": overrides}
        return await self._call("POST", "/v1/risk/what-if", body)

    async def detect_anomaly(self, machine_id: str, history: list[dict], latest: dict) -> dict[str, Any]:
        body = {"machine_id": machine_id, "history": history, "latest": latest}
        return await self._call("POST", "/v1/anomaly/readings", body)

    # --- audio -------------------------------------------------------------------------------
    async def route_audio(self, file_path: str | None = None, mode: str | None = None) -> dict[str, Any]:
        return await self._call("POST", "/v1/audio/route", _clean({"file_path": file_path, "mode": mode}))

    async def create_baseline(
        self, machine_id: str, file_paths: list[str], embedder_id: str = "mfcc_baseline"
    ) -> dict[str, Any]:
        if len(file_paths) < 3:
            raise ValueError("Provide at least 3 normal reference clips")
        body = {"machine_id": machine_id, "file_paths": file_paths, "embedder_id": embedder_id}
        return await self._call("POST", "/v1/audio/baseline", body)

    async def analyze_audio(self, machine_id: str, file_path: str, baseline_ref: dict[str, Any]) -> dict[str, Any]:
        """baseline_ref = the full BaselineArtifact returned by create_baseline()."""
        body = {"machine_id": machine_id, "file_path": file_path, "baseline_ref": baseline_ref}
        return await self._call("POST", "/v1/audio/analyze", body)

    # --- speech ------------------------------------------------------------------------------
    async def transcribe(
        self,
        file_path: str,
        language_hint: str | None = None,
        profile: str | None = None,
        catalog_machines: list[str] | None = None,
    ) -> dict[str, Any]:
        body = {
            "file_path": file_path,
            "language_hint": language_hint,
            "profile": profile,
            "catalog_machines": catalog_machines,
        }
        return await self._call("POST", "/v1/speech/transcribe", _clean(body))

    async def parse_symptom(
        self, text: str, profile: str = "metalworking", catalog_machines: list[str] | None = None
    ) -> dict[str, Any]:
        body = {"text": text, "profile": profile, "catalog_machines": catalog_machines or []}
        return await self._call("POST", "/v1/speech/parse", body)

    # --- vision ------------------------------------------------------------------------------
    async def check_image_quality(self, file_path: str | None = None, image_b64: str | None = None) -> dict:
        return await self._call("POST", "/v1/vision/quality", _clean({"file_path": file_path, "image_b64": image_b64}))

    async def read_panel(
        self, file_path: str, machine_id: str | None = None, workshop_id: str | None = None, lang: str = "ru"
    ) -> dict[str, Any]:
        body = {"file_path": file_path, "machine_id": machine_id, "workshop_id": workshop_id, "lang": lang}
        return await self._call("POST", "/v1/vision/panel", _clean(body))

    async def compare_tool(self, file_path_ref: str, file_path_cur: str) -> dict[str, Any]:
        body = {"file_path_reference": file_path_ref, "file_path_current": file_path_cur}
        return await self._call("POST", "/v1/vision/tool-compare", body)

    async def detect_part_defect(self, file_path: str, category: str = "metal_nut") -> dict[str, Any]:
        return await self._call("POST", "/v1/vision/part-defect", {"file_path": file_path, "category": category})

    # --- manuals (ids as in the backend mapping: manual "man-7", machine "m-42") ----------------
    async def index_manual(self, manual_id: str, machine_id: str, file_path: str, language: str = "ru") -> dict:
        body = {"manual_id": manual_id, "machine_id": machine_id, "file_path": file_path, "language": language}
        return await self._call("POST", "/v1/manuals/index", body)

    async def get_manual_status(self, manual_id: str) -> dict[str, Any]:
        return await self._call("GET", f"/v1/manuals/{manual_id}/status")

    async def query_manual(self, machine_id: str, query: str, top_k: int = 5) -> dict[str, Any]:
        return await self._call("POST", "/v1/manuals/query", {"machine_id": machine_id, "query": query, "top_k": top_k})

    # --- incident orchestration --------------------------------------------------------------
    async def analyze_incident(
        self,
        workshop_id: str,
        machine_id: str | None = None,
        profile: str = "metalworking",
        lang: str = "ru",
        voice_file_path: str | None = None,
        audio_file_path: str | None = None,
        panel_photo_path: str | None = None,
        tool_photo_path: str | None = None,
        tool_reference_photo_path: str | None = None,
        text: str | None = None,
        context: dict[str, Any] | None = None,
        baseline_ref: dict[str, Any] | None = None,
        answers: dict[str, str] | None = None,
        incident_context: dict[str, Any] | None = None,
        catalog_machines: list[str] | None = None,
    ) -> dict[str, Any]:
        body = {
            "workshop_id": workshop_id,
            "machine_id": machine_id,
            "profile": profile,
            "lang": lang,
            "voice_file_path": voice_file_path,
            "audio_file_path": audio_file_path,
            "panel_photo_path": panel_photo_path,
            "tool_photo_path": tool_photo_path,
            "tool_reference_photo_path": tool_reference_photo_path,
            "text": text,
            "context": context or {},
            "baseline_ref": baseline_ref,
            "answers": answers,
            "incident_context": incident_context,
            "catalog_machines": catalog_machines or [],
        }
        return await self._call("POST", "/v1/incident/analyze", _clean(body))

    # --- assistants --------------------------------------------------------------------------
    async def operator_chat(
        self, machine_id: str, question: str, lang: str = "ru", incident_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        body = {"machine_id": machine_id, "question": question, "lang": lang, "incident_context": incident_context}
        return await self._call("POST", "/v1/assistant/operator", _clean(body))

    async def dashboard_chat(self, workshop_id: str, query: str, lang: str = "ru") -> dict[str, Any]:
        return await self._call(
            "POST", "/v1/assistant/dashboard", {"workshop_id": workshop_id, "query": query, "lang": lang}
        )
