"""Fibo AI client: every request matches the contract, errors are typed, retries are bounded."""

import json
import re

import httpx
import pytest

from fibo_ai_client import FiboAIClient, FiboAIError, timeout_for
from tests.contract import CONTRACT

BASELINE = {"request_id": "r", "machine_id": "m-42", "embedder_id": "mfcc_baseline", "sha256": "x"}
CALLS = [  # one call per wrapped endpoint (22)
    ("get_health", {}),
    ("get_ready", {}),
    ("get_models_meta", {}),
    ("predict_risk", {"data": {"machine_id": "m-42", "features": {}}}),
    ("rank_machines", {"machines": [{"machine_id": "m-42"}]}),
    ("what_if", {"machine_id": "m-42", "current": {}, "overrides": {}}),
    ("detect_anomaly", {"machine_id": "m-42", "history": [], "latest": {}}),
    ("route_audio", {"file_path": "/app/data/media/voice/a.ogg"}),
    ("create_baseline", {"machine_id": "m-42", "file_paths": ["/m/1.ogg", "/m/2.ogg", "/m/3.ogg"]}),
    ("analyze_audio", {"machine_id": "m-42", "file_path": "/m/a.ogg", "baseline_ref": BASELINE}),
    (
        "transcribe",
        {"file_path": "/m/v.ogg", "language_hint": "ru", "profile": "metalworking", "catalog_machines": ["ЧПУ-2"]},
    ),
    ("parse_symptom", {"text": "гудит", "catalog_machines": ["ЧПУ-2"]}),
    ("check_image_quality", {"file_path": "/m/p.jpg"}),
    ("read_panel", {"file_path": "/m/p.jpg", "machine_id": "m-42", "workshop_id": "ws-3"}),
    ("compare_tool", {"file_path_ref": "/m/r.jpg", "file_path_cur": "/m/c.jpg"}),
    ("detect_part_defect", {"file_path": "/m/p.jpg"}),
    ("index_manual", {"manual_id": "man-7", "machine_id": "m-42", "file_path": "/m/x.pdf"}),
    ("get_manual_status", {"manual_id": "man-7"}),
    ("query_manual", {"machine_id": "m-42", "query": "шпиндель"}),
    (
        "analyze_incident",
        {
            "workshop_id": "ws-3",
            "machine_id": "m-42",
            "voice_file_path": "/m/v.ogg",
            "catalog_machines": ["ЧПУ-2"],
            "context": {"criticality": 3},
        },
    ),
    ("operator_chat", {"machine_id": "m-42", "question": "как?"}),
    ("dashboard_chat", {"workshop_id": "ws-3", "query": "риск"}),
]


def contract_key(path: str) -> str:
    return re.sub(r"^/v1/manuals/[^/]+/status$", "/v1/manuals/{id}/status", path)


def recording_client(responses: list[httpx.Response]) -> tuple[FiboAIClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responses[min(len(seen) - 1, len(responses) - 1)]

    return FiboAIClient("http://ai:8001", token="t", transport=httpx.MockTransport(handler), retry_waits=(0, 0)), seen


@pytest.mark.parametrize(("method", "kwargs"), CALLS, ids=[c[0] for c in CALLS])
async def test_every_request_matches_the_contract(method, kwargs):
    client, seen = recording_client([httpx.Response(200, json={})])
    await getattr(client, method)(**kwargs)
    request = seen[0]
    expected_method, allowed, required = CONTRACT[contract_key(request.url.path)]
    assert request.method == expected_method
    assert request.headers["authorization"] == "Bearer t"
    body = json.loads(request.content) if request.content else {}
    assert set(body) <= allowed, f"fields not in contract: {set(body) - allowed}"
    assert required <= set(body), f"missing required fields: {required - set(body)}"
    assert None not in body.values()


def test_all_22_endpoints_are_covered():
    assert len(CONTRACT) == 22 == len(CALLS)


def test_baseline_needs_three_clips_and_sends_no_clip_count():
    client, _ = recording_client([httpx.Response(200, json={})])
    with pytest.raises(ValueError):
        import asyncio

        asyncio.run(client.create_baseline("m-42", ["/m/1.ogg"]))


async def test_error_envelope_becomes_fibo_ai_error():
    envelope = {
        "error": {
            "code": "PHOTO_QUALITY_LOW",
            "message": "blurry",
            "retriable": False,
            "details": {"issues": ["blur"]},
            "retake_advice_ru": "Переснимите",
            "retake_advice_kk": "Қайта",
        }
    }
    client, seen = recording_client([httpx.Response(422, json=envelope)])
    with pytest.raises(FiboAIError) as error:
        await client.read_panel("/m/p.jpg")
    assert (error.value.status, error.value.code, error.value.retriable) == (422, "PHOTO_QUALITY_LOW", False)
    assert error.value.details["retake_advice_ru"] == "Переснимите" and error.value.details["issues"] == ["blur"]
    assert len(seen) == 1  # input errors are never retried


async def test_503_is_retried_then_succeeds():
    unavailable = httpx.Response(503, json={"error": {"code": "LLM_UNAVAILABLE", "message": "", "retriable": True}})
    client, seen = recording_client([unavailable, unavailable, httpx.Response(200, json={"ok": True})])
    assert await client.analyze_incident(workshop_id="ws-3") == {"ok": True}
    assert len(seen) == 3


async def test_transport_failure_is_unreachable_after_two_retries():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("refused")

    client = FiboAIClient("http://ai:8001", transport=httpx.MockTransport(handler), retry_waits=(0, 0))
    with pytest.raises(FiboAIError) as error:
        await client.get_ready()
    assert (error.value.status, error.value.code, error.value.retriable) == (0, "UNREACHABLE", True)
    assert len(calls) == 3


async def test_non_envelope_error_is_still_typed():
    client, _ = recording_client([httpx.Response(404, text="Not Found")])
    with pytest.raises(FiboAIError) as error:
        await client.get_manual_status("man-7")
    assert error.value.code == "HTTP_404"


def test_per_endpoint_timeouts():
    assert timeout_for("/v1/incident/analyze") == 12 and timeout_for("/v1/vision/panel") == 8
    assert timeout_for("/v1/speech/transcribe") == 6 and timeout_for("/v1/manuals/index") == 15
    assert timeout_for("/v1/risk/predict") == 5
