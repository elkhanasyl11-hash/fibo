"""Sidecar first, builtin as automatic fallback (integration contract section 4.3, decision D76).

Every call goes through with_fallback():
  FIBO_AI_PROVIDER=builtin       -> the builtin module only (the default; tests, no AI container)
  sidecar answers in shape       -> Outcome(source="ai", value=<adapted>)
  ContractError / non-JSON 2xx   -> builtin, degraded "ai_contract_mismatch"
  FiboAIError, by classify():
    unavailable                  -> builtin, degraded "ai_sidecar_unavailable"
    input                        -> Outcome(source="ai", input_error=<error>): the caller shows the
                                    explanatory card (messages.py); the builtin would fail the same way
    recoverable                  -> on_recoverable() once (e.g. rebuild the baseline), else builtin
    soft                         -> builtin, degraded "ai_manual_not_indexed"
    bug + 400/413/415 codes      -> AIRequestRejected: the incident is FAILED with "ai: <code>"
    bug otherwise                -> builtin, degraded "ai_contract_mismatch" (401/403: "ai_auth_failed")
Nothing here touches the database; safety, citations and the card stay with the caller (R4–R6).
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.core.config import settings
from app.modules.ai_gateway import adapters
from app.modules.ai_gateway.client import FiboAIClient, FiboAIError
from app.modules.ai_gateway.errors import AIRequestRejected, ContractError, classify, fails_incident

log = logging.getLogger("fibo.ai_gateway")

DEGRADED = {
    "unavailable": "ai_sidecar_unavailable",
    "soft": "ai_manual_not_indexed",
    "recoverable": "ai_baseline_mismatch",
    "bug": "ai_contract_mismatch",
}
AUTH_STATUSES = {401, 403}  # wrong FIBO_AI_TOKEN: FastAPI answers without the error envelope
AICall = Callable[[FiboAIClient], Awaitable[dict]]


@dataclass
class Outcome:
    source: Literal["ai", "builtin"]
    value: Any = None
    degraded: list[str] = field(default_factory=list)
    input_error: FiboAIError | None = None


def make_client() -> FiboAIClient:
    """One client per call: cheap, and nothing is shared between requests. Tests monkeypatch this."""
    return FiboAIClient(settings.ai_url, settings.ai_token)


def sidecar_enabled() -> bool:
    return settings.ai_provider == "sidecar"


async def _builtin(name: str, fallback: Callable[[], Awaitable[Any]], degraded: str | None) -> Outcome:
    if degraded:
        log.warning("ai %s: falling back to builtin (%s)", name, degraded)
    return Outcome("builtin", await fallback(), [degraded] if degraded else [])


async def with_fallback(
    name: str,
    call: AICall,
    adapt: Callable[[dict], Any],
    fallback: Callable[[], Awaitable[Any]],
    on_recoverable: AICall | None = None,
) -> Outcome:
    if not sidecar_enabled():
        return await _builtin(name, fallback, None)
    async with make_client() as client:
        try:
            return Outcome("ai", adapt(await call(client)))
        except (ContractError, ValueError) as exc:
            log.warning("ai %s: unexpected answer: %s", name, exc)
            return await _builtin(name, fallback, DEGRADED["bug"])
        except FiboAIError as error:
            kind = classify(error)
            log.info("ai %s: %s (%s)", name, error.code, kind)
            if kind == "input":
                return Outcome("ai", input_error=error)
            if kind == "recoverable" and on_recoverable is not None:
                try:
                    return Outcome("ai", adapt(await on_recoverable(client)), ["ai_baseline_rebuilt"])
                except (FiboAIError, ContractError, ValueError) as retry_error:
                    log.warning("ai %s: retry after %s failed: %s", name, error.code, retry_error)
            if kind == "bug" and fails_incident(error):
                raise AIRequestRejected(error) from error
            tag = "ai_auth_failed" if error.status in AUTH_STATUSES else DEGRADED[kind]
            return await _builtin(name, fallback, tag)


# --- one wrapper per backend path (step 6 wires them in) --------------------------------------
async def analyze_incident(request: dict, fallback, on_recoverable: AICall | None = None) -> Outcome:
    """request = FiboAIClient.analyze_incident kwargs; value = adapters.AIIncident."""
    return await with_fallback(
        "incident", lambda c: c.analyze_incident(**request), adapters.parse_incident, fallback, on_recoverable
    )


async def predict_risk(request: dict, fallback) -> Outcome:
    """request = {"machine_id", "workshop_id", "features": {...}}; value = adapters.AIRisk."""
    return await with_fallback("risk", lambda c: c.predict_risk(request), adapters.parse_risk, fallback)


async def read_panel(request: dict, fallback) -> Outcome:
    """request = FiboAIClient.read_panel kwargs; value = vision.panel_ocr.PanelReadout."""
    return await with_fallback("panel", lambda c: c.read_panel(**request), adapters.parse_panel, fallback)


async def build_audio_baseline(machine_id: str, file_paths: list[str], fallback) -> Outcome:
    """value = the BaselineArtifact dict, stored and sent back unchanged as baseline_ref."""
    return await with_fallback(
        "baseline", lambda c: c.create_baseline(machine_id, file_paths), adapters.parse_baseline, fallback
    )


async def index_manual(request: dict, fallback) -> Outcome:
    """request = FiboAIClient.index_manual kwargs; value = (IndexStatus, error, page_count)."""
    return await with_fallback(
        "manual_index", lambda c: c.index_manual(**request), adapters.parse_manual_status, fallback
    )


async def manual_status(manual_id: str, fallback) -> Outcome:
    return await with_fallback(
        "manual_status", lambda c: c.get_manual_status(manual_id), adapters.parse_manual_status, fallback
    )
