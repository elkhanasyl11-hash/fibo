"""JSON-schema validated LLM client for OpenAI-compatible chat completion APIs."""

import asyncio
import base64
import json
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from fibo_ai.core.errors import LLMUnavailableError
from fibo_ai.core.files import sniff_media_type
from fibo_ai.core.llm.base import LLMClient
from fibo_ai.schemas.common import Usage
from fibo_ai.settings import Settings

T = TypeVar("T", bound=BaseModel)


class OpenAICompatClient(LLMClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._failures = 0
        self._open_until = 0.0

    def _credentials(self) -> tuple[str, str]:
        provider = self.settings.llm_provider.lower()
        if provider == "gemini":
            key = self.settings.gemini_api_key
            base_url = self.settings.openai_base_url or ("https://generativelanguage.googleapis.com/v1beta/openai")
        else:
            key = self.settings.openai_api_key
            base_url = self.settings.openai_base_url or "https://api.openai.com/v1"
        if not key:
            raise LLMUnavailableError("LLM API key is not configured")
        return key, base_url.rstrip("/")

    async def generate_json(
        self,
        prompt: str,
        schema: type[T],
        images: list[bytes] | None = None,
        temperature: float = 0.0,
        timeout_s: float = 15.0,
    ) -> tuple[T, Usage]:
        if time.monotonic() < self._open_until:
            raise LLMUnavailableError("LLM circuit breaker is open")
        key, base_url = self._credentials()
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        content = f"{prompt}\n\nReturn one JSON object that validates against this schema:\n{schema_json}"
        if images:
            parts: list[dict[str, Any]] = [{"type": "text", "text": content}]
            for image in images:
                mime = sniff_media_type(image[:32])
                if mime not in {"image/png", "image/jpeg"}:
                    raise LLMUnavailableError("Vision input must be PNG or JPEG")
                encoded = base64.b64encode(image).decode("ascii")
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{encoded}"},
                    }
                )
            user_content: str | list[dict[str, Any]] = parts
        else:
            user_content = content
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_content}]
        payload: dict[str, Any] = {
            "model": self.settings.llm_vision_model if images else self.settings.llm_model,
            "response_format": {"type": "json_object"},
            "messages": messages,
        }
        if self.settings.llm_reasoning_effort:  # reasoning model: temperature is rejected (HTTP 400)
            payload["reasoning_effort"] = self.settings.llm_reasoning_effort
        else:
            payload["temperature"] = temperature
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            for attempt in range(2):
                try:
                    response = await client.post(
                        f"{base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {key}"},
                        json=payload,
                    )
                    response.raise_for_status()
                    body = response.json()
                    text = body["choices"][0]["message"]["content"]
                    if isinstance(text, list):
                        text = "".join(str(part.get("text", "")) for part in text if isinstance(part, dict))
                    parsed = schema.model_validate_json(str(text))
                    self._failures = 0
                    usage_body = body.get("usage", {})
                    return parsed, Usage(
                        llm_input_tokens=int(usage_body.get("prompt_tokens", 0)),
                        llm_output_tokens=int(usage_body.get("completion_tokens", 0)),
                    )
                except (httpx.HTTPError, KeyError, ValueError, ValidationError) as exc:
                    last_error = exc
                    if attempt == 0 and isinstance(exc, ValidationError):
                        messages.append(
                            {
                                "role": "user",
                                "content": f"Correct the JSON to match the schema. Validation: {exc}",
                            }
                        )
                        continue
                    if attempt == 0 and isinstance(exc, httpx.HTTPStatusError):
                        await asyncio.sleep(0.2)
                        continue
        self._failures += 1
        if self._failures >= 3:
            self._open_until = time.monotonic() + 30.0
        raise LLMUnavailableError(
            "Structured LLM request failed",
            details={"reason": type(last_error).__name__ if last_error else "unknown"},
        ) from last_error
