"""Shared-secret dependencies for the bot and the dashboard."""

import pytest

from app.core import security
from app.core.errors import AuthError


async def test_bot_token_accepts_correct_secret(monkeypatch):
    monkeypatch.setattr(security.settings, "bot_shared_secret", "s3cret")
    await security.require_bot_token("s3cret")


@pytest.mark.parametrize("token", [None, "", "wrong"])
async def test_bot_token_rejects_missing_or_wrong(monkeypatch, token):
    monkeypatch.setattr(security.settings, "bot_shared_secret", "s3cret")
    with pytest.raises(AuthError):
        await security.require_bot_token(token)


async def test_dashboard_key_disabled_when_not_configured(monkeypatch):
    monkeypatch.setattr(security.settings, "dashboard_api_key", None)
    await security.require_dashboard_key(None, None)


async def test_dashboard_key_enforced_when_configured(monkeypatch):
    monkeypatch.setattr(security.settings, "dashboard_api_key", "key-1")
    monkeypatch.setattr(security.settings, "bot_shared_secret", "s3cret")
    await security.require_dashboard_key("key-1", None)
    with pytest.raises(AuthError):
        await security.require_dashboard_key(None, None)
    with pytest.raises(AuthError):
        await security.require_dashboard_key("key-2", None)


async def test_dashboard_endpoints_accept_the_bot_token(monkeypatch):
    monkeypatch.setattr(security.settings, "dashboard_api_key", "key-1")
    monkeypatch.setattr(security.settings, "bot_shared_secret", "s3cret")
    await security.require_dashboard_key(None, "s3cret")
    with pytest.raises(AuthError):
        await security.require_dashboard_key(None, "wrong")
