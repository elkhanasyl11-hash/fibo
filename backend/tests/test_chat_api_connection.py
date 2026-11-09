"""The web chat reaches the provider, preserves history, and never silently substitutes fixtures."""

import json

import httpx
import pytest

from app.core.config import settings
from app.core.errors import ExternalServiceError
from app.modules.assistant import llm


def payload(workshop_id):
    return {
        "workshop_id": workshop_id,
        "messages": [
            {"role": "user", "content": "Объясни вибрацию подшипника"},
            {"role": "assistant", "content": "Это колебания."},
            {"role": "user", "content": "А какие станки у нас требуют внимания?"},
        ],
    }


async def test_missing_key_is_reported_without_a_canned_answer(client, make_workshop):
    workshop = await make_workshop()
    status = (await client.get("/api/v1/ai/assistant/status")).json()
    assert not status["configured"]
    assert "FIBO_LLM_API_KEY" in status["missing"]
    response = await client.post("/api/v1/ai/assistant/chat", json=payload(workshop["id"]))
    assert response.status_code == 503
    assert response.json()["error"]["details"]["reason"] == "not_configured"
    assert "answer" not in response.json()


@pytest.fixture
def live_config(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "test-secret")
    monkeypatch.setattr(settings, "llm_base_url", "https://llm.invalid/v1")
    monkeypatch.setattr(settings, "llm_model", "test-model")
    monkeypatch.setattr(settings, "llm_reasoning_effort", "low")
    monkeypatch.setattr(llm.LiveLLMClient, "retry_waits", (0, 0))


async def test_live_round_trip_uses_workshop_tools_and_history(
    client, make_workshop, make_machine, monkeypatch, live_config
):
    workshop = await make_workshop()
    machine = await make_machine(workshop["id"], name="Станок проверки API")
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.headers["authorization"] == "Bearer test-secret"
        assert body["reasoning_effort"] == "low"  # never forcibly replaced with none
        if len(requests) == 1:
            message = {
                "tool_calls": [
                    {
                        "id": "summary",
                        "type": "function",
                        "function": {
                            "name": "get_machine_summary",
                            "arguments": json.dumps({"machine_name_or_id": str(machine["id"])}),
                        },
                    }
                ]
            }
        else:
            assert "Станок проверки API" in body["messages"][-1]["content"]
            message = {"content": "Ответ внешней модели по показаниям вашего станка."}
        return httpx.Response(200, json={"choices": [{"message": message}]})

    original = llm.LiveLLMClient.__init__

    def init(self):
        original(self)
        self.transport = httpx.MockTransport(handler)

    monkeypatch.setattr(llm.LiveLLMClient, "__init__", init)
    response = await client.post("/api/v1/ai/assistant/chat", json=payload(workshop["id"]))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["source"] == "ai" and not result["degraded"]
    assert result["tools_used"] == ["get_machine_summary"]
    assert result["referenced_machine_ids"] == [machine["id"]]
    assert requests[0]["messages"][1:] == payload(workshop["id"])["messages"]
    assert "не требуй выбрать готовый вопрос" in requests[0]["messages"][0]["content"]
    status = (await client.get("/api/v1/ai/assistant/status")).json()
    assert status == {"configured": True, "model": "test-model", "missing": []}
    assert "test-secret" not in json.dumps(status)


@pytest.mark.parametrize(
    "status,reason",
    [(401, "authentication"), (400, "provider_configuration"), (429, "rate_limited"), (503, "unavailable")],
)
async def test_provider_failure_is_visible_not_a_mock_success(
    client, make_workshop, monkeypatch, live_config, status, reason
):
    workshop = await make_workshop()
    original = llm.LiveLLMClient.__init__

    def init(self):
        original(self)
        self.transport = httpx.MockTransport(lambda _: httpx.Response(status))

    monkeypatch.setattr(llm.LiveLLMClient, "__init__", init)
    response = await client.post("/api/v1/ai/assistant/chat", json=payload(workshop["id"]))
    assert response.status_code == 502
    assert response.json()["error"]["details"]["reason"] == reason
    assert "answer" not in response.json()


@pytest.mark.parametrize(
    "body",
    [
        b"not JSON",
        b"{}",
        b'{"choices":[]}',
        b'{"choices":[{"message":{"content":" "}}]}',
        b'{"choices":[{"message":{"tool_calls":[{}]}}]}',
    ],
)
async def test_bad_provider_payload_is_a_controlled_error(monkeypatch, live_config, body):
    client = llm.LiveLLMClient()
    client.transport = httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    with pytest.raises(ExternalServiceError) as error:
        await client.chat_tools([{"role": "user", "content": "Привет"}], [])
    assert error.value.details["reason"] == "invalid_response"
