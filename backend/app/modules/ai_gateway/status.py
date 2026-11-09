"""AI service status for GET /api/v1/health. Never raises: health must answer even when the AI is down.

ai_sidecar: "disabled" (FIBO_AI_PROVIDER=builtin), "ready" (/readyz answered 2xx within FIBO_AI_TIMEOUT_S),
"unreachable" (anything else). ai_models: /v1/meta/models, cached for MODELS_TTL_S so a dashboard polling
health does not hit the AI service on every request; None until the first successful read.
"""

import logging
import time
from typing import Any

import httpx

from app.core.config import settings

log = logging.getLogger("fibo.ai_gateway")

MODELS_TTL_S = 60.0
_models_cache: dict[str, Any] = {"at": None, "value": None}
_transport: httpx.AsyncBaseTransport | None = None  # tests set an httpx.MockTransport


def _client() -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {settings.ai_token}"} if settings.ai_token else {}
    return httpx.AsyncClient(
        base_url=settings.ai_url.rstrip("/"),
        headers=headers,
        timeout=settings.ai_timeout_s,
        transport=_transport,
    )


def reset_cache() -> None:
    _models_cache.update(at=None, value=None)


async def _models(client: httpx.AsyncClient) -> dict | None:
    fresh = _models_cache["at"] is not None and time.monotonic() - _models_cache["at"] < MODELS_TTL_S
    if fresh:
        return _models_cache["value"]
    response = await client.get("/v1/meta/models")
    response.raise_for_status()
    value = response.json()
    _models_cache.update(at=time.monotonic(), value=value)
    return value


async def ai_status() -> dict[str, Any]:
    if settings.ai_provider != "sidecar":
        return {"ai_sidecar": "disabled", "ai_models": None}
    try:
        async with _client() as client:
            ready = await client.get("/readyz")
            if ready.status_code >= 400:
                return {"ai_sidecar": "unreachable", "ai_models": _models_cache["value"]}
            return {"ai_sidecar": "ready", "ai_models": await _models(client)}
    except (httpx.HTTPError, ValueError) as exc:
        log.info("ai health probe failed: %s", type(exc).__name__)
        return {"ai_sidecar": "unreachable", "ai_models": _models_cache["value"]}
