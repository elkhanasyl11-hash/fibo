"""LLM client: mock is deterministic; live client retries only transient errors and repairs JSON once."""

import json

import httpx
import pytest
from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import ExternalServiceError, ModelUnavailableError
from app.modules.assistant import llm, mock_fixtures
from app.modules.assistant.extraction import SymptomExtraction


class Answer(BaseModel):
    value: int


def chat_reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "https://llm.invalid/v1")
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_model", "test-model")
    monkeypatch.setattr(llm.LiveLLMClient, "retry_waits", (0, 0))

    def make(responses: list):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            item = responses[min(len(calls) - 1, len(responses) - 1)]
            if isinstance(item, Exception):
                raise item
            return item

        client = llm.LiveLLMClient()
        client.transport = httpx.MockTransport(handler)
        return client, calls

    return make


async def test_retries_5xx_then_succeeds(live):
    client, calls = live([httpx.Response(503), httpx.Response(429), chat_reply('{"value": 7}')])
    assert (await client.chat_json([{"role": "user", "content": "x"}], Answer)).value == 7
    assert len(calls) == 3
    assert calls[0].headers["authorization"] == "Bearer test-key"
    assert json.loads(calls[0].content)["response_format"] == {"type": "json_object"}


async def test_timeouts_are_retried_then_reported(live):
    client, calls = live([httpx.ReadTimeout("slow")])
    with pytest.raises(ExternalServiceError) as error:
        await client.chat_json([{"role": "user", "content": "x"}], Answer)
    assert len(calls) == 3 and error.value.details["provider"] == "openai-compatible"


async def test_4xx_is_not_retried(live):
    client, calls = live([httpx.Response(400, json={"error": "bad"})])
    with pytest.raises(ExternalServiceError):
        await client.chat_json([{"role": "user", "content": "x"}], Answer)
    assert len(calls) == 1


async def test_invalid_json_gets_one_repair(live):
    client, calls = live([chat_reply("not json"), chat_reply('{"value": 3}')])
    assert (await client.chat_json([{"role": "user", "content": "x"}], Answer)).value == 3
    assert len(calls) == 2 and "not valid JSON" in json.loads(calls[1].content)["messages"][-1]["content"]

    client, calls = live([chat_reply('{"value": "nope"}')])
    with pytest.raises(ExternalServiceError):
        await client.chat_json([{"role": "user", "content": "x"}], Answer)
    assert len(calls) == 2


async def test_transcription_request(live, tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF....WAVE")
    client, calls = live([httpx.Response(200, json={"text": " Привет "})])
    assert await client.transcribe(wav, "kk") == "Привет"
    assert calls[0].url.path.endswith("/audio/transcriptions") and b'name="language"' in calls[0].content


def test_live_mode_without_config_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", None)
    with pytest.raises(ModelUnavailableError):
        llm.LiveLLMClient()


async def test_mock_is_deterministic():
    client = llm.get_llm_client()
    assert isinstance(client, llm.MockLLMClient)
    payload = json.dumps({"task": "extract_symptoms", "transcript": "Шпиндель гудит"})
    first = await client.chat_json([{"role": "user", "content": payload}], SymptomExtraction)
    second = await client.chat_json([{"role": "user", "content": payload}], SymptomExtraction)
    assert first == second and first.urgency == "medium" and "шпинделя" in first.symptom
    assert mock_fixtures.transcript_for(b"abc") == mock_fixtures.transcript_for(b"abc")
