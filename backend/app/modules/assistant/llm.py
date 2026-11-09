"""Fibo Assistant: the one gateway to external AI (chat with JSON output, tool calls, speech-to-text).

Two implementations of the same LLMClient interface, chosen by FIBO_AI_MODE:
  live  LiveLLMClient: any OpenAI-compatible HTTP API (base URL, key, model names from settings).
  mock  MockLLMClient: deterministic answers from mock_fixtures.py, no network. Used by tests, the
        demo seed and offline demos — our insurance if the API fails during the live demo.

Error handling of the live client (spec 6.3):
  - timeout on every call (settings.llm_timeout_s);
  - 2 retries with waits of 1 s and 3 s, ONLY for timeouts, network errors, HTTP 429 and 5xx;
    other 4xx are our mistake and are not retried;
  - JSON answers are validated with the Pydantic schema; one repair attempt, then an error;
  - when everything fails: ExternalServiceError with the provider in `details`. Never silent.
"""

import base64
import json
import logging
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_chain,
    wait_fixed,
)

from app.core.config import settings
from app.core.errors import ExternalServiceError, ModelUnavailableError
from app.modules.assistant import mock_fixtures

logger = logging.getLogger("fibo.assistant.llm")


class LLMClient(Protocol):
    async def chat_json(
        self, messages: list[dict], schema: type[BaseModel], *, images: list[Path] | None = None
    ) -> BaseModel: ...

    async def chat_tools(self, messages: list[dict], tools: list[dict]) -> dict: ...

    async def transcribe(self, wav_path: Path, language: str | None) -> str: ...


class _Retryable(Exception):
    """A failure worth retrying (timeout, network error, 429, 5xx)."""


def _schema_instruction(schema: type[BaseModel]) -> str:
    return "Return ONLY a JSON object that matches this JSON Schema:\n" + json.dumps(
        schema.model_json_schema(), ensure_ascii=False
    )


def _with_images(messages: list[dict], images: list[Path]) -> list[dict]:
    """Attach images to the last user message as data URLs (OpenAI vision format)."""
    parts = [{"type": "text", "text": messages[-1]["content"]}]
    for path in images:
        encoded = base64.b64encode(path.read_bytes()).decode()
        mime = {".png": "image/png", ".webp": "image/webp"}.get(path.suffix.lower(), "image/jpeg")
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})
    return [*messages[:-1], {"role": "user", "content": parts}]


def _sampling(reasoning_effort: str) -> dict:
    """Omit optional parameters by default; explicit settings follow the provider's model contract."""
    if reasoning_effort == "auto":
        return {}
    return {"temperature": 0} if reasoning_effort == "off" else {"reasoning_effort": reasoning_effort}


def missing_llm_settings() -> list[str]:
    values = {
        "FIBO_LLM_BASE_URL": settings.llm_base_url,
        "FIBO_LLM_API_KEY": settings.llm_api_key,
        "FIBO_LLM_MODEL": settings.llm_model,
    }
    return [name for name, value in values.items() if not value or value.strip() in ("", "set-in-env")]


def _message(payload: dict) -> dict:
    try:
        message = payload["choices"][0]["message"]
        if not isinstance(message, dict):
            raise TypeError
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise TypeError
        calls = message.get("tool_calls") or []
        if not isinstance(calls, list) or len(calls) > 16:
            raise TypeError
        for call in calls:
            if (
                not isinstance(call, dict)
                or not isinstance(call.get("id"), str)
                or not isinstance(call.get("function"), dict)
                or not isinstance(call["function"].get("name"), str)
                or not isinstance(call["function"].get("arguments", "{}"), str)
            ):
                raise TypeError
        if not calls and not (content or "").strip():
            raise ValueError
        return message
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ExternalServiceError(
            "AI provider returned an invalid or empty answer", details={"reason": "invalid_response"}
        ) from exc


class LiveLLMClient:
    provider = "openai-compatible"
    retry_waits: tuple[float, float] = (1.0, 3.0)  # tests set (0, 0)

    def __init__(self) -> None:
        missing = missing_llm_settings()
        if missing:
            raise ModelUnavailableError(
                "AI API is not configured", details={"reason": "not_configured", "missing": missing}
            )
        self.base_url = settings.llm_base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
        self.transport: httpx.AsyncBaseTransport | None = None  # tests inject httpx.MockTransport

    async def _post_once(self, path: str, **kwargs) -> dict:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_s, transport=self.transport) as client:
            try:
                response = await client.post(f"{self.base_url}{path}", headers=self.headers, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                raise _Retryable(type(exc).__name__) from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise _Retryable(f"HTTP {response.status_code}")
        if response.status_code >= 400:  # our request is wrong: retrying will not help
            raise ExternalServiceError(
                "AI provider rejected the request",
                details={
                    "provider": self.provider,
                    "status": response.status_code,
                    "path": path,
                    "reason": "authentication"
                    if response.status_code in (401, 403)
                    else "provider_configuration",
                },
            )
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError
            return payload
        except ValueError as exc:
            raise ExternalServiceError(
                "AI provider returned invalid JSON", details={"reason": "invalid_response"}
            ) from exc

    async def _post(self, path: str, **kwargs) -> dict:
        retrying = AsyncRetrying(
            retry=retry_if_exception_type(_Retryable),
            stop=stop_after_attempt(3),
            wait=wait_chain(*(wait_fixed(w) for w in self.retry_waits)),
        )
        try:
            async for attempt in retrying:
                with attempt:
                    return await self._post_once(path, **kwargs)
        except RetryError as exc:
            reason = str(exc.last_attempt.exception())
            logger.error("AI call failed after retries", extra={"path": path, "reason": reason})
            raise ExternalServiceError(
                "AI provider is unavailable",
                details={
                    "provider": self.provider,
                    "reason": "rate_limited" if reason == "HTTP 429" else "unavailable",
                },
            ) from exc
        raise AssertionError("unreachable")

    async def chat_json(self, messages, schema, *, images=None):
        model = settings.llm_vision_model if images else settings.llm_model
        conversation = [{"role": "system", "content": _schema_instruction(schema)}, *messages]
        if images:
            conversation = _with_images(conversation, images)
        for attempt in range(2):  # first answer + one repair attempt
            body = {
                "model": model,
                "messages": conversation,
                "response_format": {"type": "json_object"},
                **_sampling(settings.llm_reasoning_effort),
            }
            content = _message(await self._post("/chat/completions", json=body)).get("content") or ""
            try:
                return schema.model_validate_json(content)
            except ValidationError as exc:
                logger.warning(
                    "AI returned invalid JSON", extra={"attempt": attempt, "errors": exc.error_count()}
                )
                conversation = [
                    *conversation,
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": "Your answer was not valid JSON for the schema. Errors: "
                        f"{exc.errors(include_url=False)[:5]}. Return valid JSON matching the schema.",
                    },
                ]
        raise ExternalServiceError("AI returned invalid JSON twice", details={"provider": self.provider})

    async def chat_tools(self, messages, tools):
        body = {
            "model": settings.llm_model,
            "messages": messages,
            **_sampling(settings.llm_reasoning_effort),
        }
        if tools:  # an empty list means "answer now, no more tools"; the API rejects "tools": []
            body["tools"] = tools
        return _message(await self._post("/chat/completions", json=body))

    async def transcribe(self, wav_path, language):
        data = {"model": settings.whisper_model}
        if language:
            data["language"] = language
        files = {"file": (wav_path.name, wav_path.read_bytes(), "audio/wav")}
        return (await self._post("/audio/transcriptions", data=data, files=files))["text"].strip()


class MockLLMClient:
    """Deterministic, offline. Reads the same messages a live model would get."""

    provider = "mock"

    async def chat_json(self, messages, schema, *, images=None):
        payload = json.loads(messages[-1]["content"])
        return schema.model_validate(mock_fixtures.answer(schema.__name__, payload))

    async def chat_tools(self, messages, tools):
        return mock_fixtures.tool_answer(messages, tools)

    async def transcribe(self, wav_path, language):
        return mock_fixtures.transcript_for(wav_path.read_bytes())


def get_llm_client() -> LLMClient:
    if settings.ai_mode == "live":
        return LiveLLMClient()
    return MockLLMClient()
