"""Shared-secret checks used as FastAPI dependencies.

Two callers talk to this backend:
  - the Telegram bot, which sends header X-Fibo-Bot-Token (must equal settings.bot_shared_secret);
  - the web dashboard, which sends header X-Fibo-Api-Key when settings.dashboard_api_key is set.
    When dashboard_api_key is None (local development) the check is skipped.

require_dashboard_key also accepts a valid bot token: the bot is a trusted internal client and
uses some dashboard endpoints too (poll an incident, resolve it, confirm panel readings).
Bot-only endpoints (/bot/*, /ingest/*) use require_bot_token and do NOT accept the dashboard key.

This is not user authentication (out of scope for the MVP, see docs/decisions.md). It only keeps
random clients away from the API. secrets.compare_digest avoids leaking the secret via timing.
"""

import secrets

from fastapi import Header, Request

from app.core.config import settings
from app.core.errors import AuthError


def _matches(given: str | None, expected: str) -> bool:
    return given is not None and secrets.compare_digest(given.encode(), expected.encode())


async def require_bot_token(x_fibo_bot_token: str | None = Header(default=None)) -> None:
    """Allow the request only if it carries the bot's shared secret."""
    if not _matches(x_fibo_bot_token, settings.bot_shared_secret):
        raise AuthError("Invalid or missing X-Fibo-Bot-Token")


async def require_dashboard_key(
    x_fibo_api_key: str | None = Header(default=None),
    x_fibo_bot_token: str | None = Header(default=None),
    request: Request = None,
) -> None:
    """Allow: dashboard key disabled (dev), or matching dashboard key, or a valid bot token."""
    expected = settings.dashboard_api_key
    if request is not None:
        public = request.url.path in {
            "/api/v1/health",
            "/api/v1/profiles",
            "/api/v1/onboarding/questions",
            "/api/v1/auth/register",
            "/api/v1/auth/login",
            "/api/v1/auth/logout",
        }
        if public:
            return
        auth_header = request.headers.get("authorization", "")
        scheme, _, bearer = auth_header.partition(" ")
        token = bearer if scheme.lower() == "bearer" else request.cookies.get("fibo_session")
        if not public and token:
            from app.core.web_scope import authorize_browser

            await authorize_browser(request, token)
            return
        if not public and not token and settings.env != "test":
            if _matches(x_fibo_bot_token, settings.bot_shared_secret) or (
                expected and _matches(x_fibo_api_key, expected)
            ):
                return
            raise AuthError("Sign in to continue")
    if expected is None or _matches(x_fibo_api_key, expected):
        return
    if _matches(x_fibo_bot_token, settings.bot_shared_secret):
        return
    raise AuthError("Invalid or missing X-Fibo-Api-Key")
