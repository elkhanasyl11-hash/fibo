"""The bot's backend client: auth header, error mapping, multipart upload."""

import httpx
import pytest

from bot.api_client import FiboApi, FiboApiError


def api_with(handler) -> FiboApi:
    return FiboApi("http://backend/api/v1", "s3cret", transport=httpx.MockTransport(handler))


def error(status: int, code: str) -> httpx.Response:
    return httpx.Response(
        status, json={"error": {"code": code, "message": code, "details": {}, "request_id": "r"}}
    )


async def test_sends_bot_token_and_returns_none_for_unknown_user():
    seen = []

    def handler(request):
        seen.append(request)
        return error(404, "not_found")

    api = api_with(handler)
    assert await api.get_user(42) is None
    assert seen[0].headers["x-fibo-bot-token"] == "s3cret" and seen[0].url.path == "/api/v1/bot/users/42"


async def test_errors_are_mapped():
    api = api_with(lambda request: error(409, "conflict"))
    with pytest.raises(FiboApiError) as exc:
        await api.resolve(1)
    assert (exc.value.status, exc.value.code) == (409, "conflict")

    def down(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(FiboApiError) as exc:
        await api_with(down).get_incident(1)
    assert exc.value.code == "unreachable"


async def test_voice_upload_is_multipart():
    def handler(request):
        body = request.content
        assert request.url.path == "/api/v1/ingest/voice"
        assert b'name="mode"' in body and b"machine_sound" in body and b'filename="voice.ogg"' in body
        return httpx.Response(202, json={"incident_id": 77, "status": "received"})

    assert await api_with(handler).ingest_voice(1, 2, b"OggS...", "voice.ogg", mode="machine_sound") == 77
