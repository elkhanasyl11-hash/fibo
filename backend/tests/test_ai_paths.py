"""Backend paths with FIBO_AI_PROVIDER=sidecar against the AI service's real answer shapes (D78, D81):
incident card, safety floor, citations, input errors, rejected requests, fallback, risk, panel photo and
audio baseline artifacts. The AI service is an httpx.MockTransport routed by path; no network (R3).
"""

import json
from datetime import timedelta

import httpx
import pytest

from app.core.config import settings
from app.db.base import utcnow
from app.models.baseline import Baseline
from app.models.machine import Machine
from app.modules.ai_gateway import provider
from app.modules.ai_gateway.client import FiboAIClient
from app.modules.machine.feature_map import ReadingValues
from app.modules.machine.risk_model_part import model_part
from app.profiles.loader import get_profiles
from tests import ai_samples
from tests.audio_samples import tone, wav_bytes
from tests.conftest import BOT_HEADERS
from tests.image_samples import jpeg, tool_image
from tests.test_ai_contract import incident as ai_incident_schema
from tests.test_ai_contract import risk as ai_risk_schema
from tests.test_pipeline import offline_audio, operator, say, upload  # noqa: F401  (fixtures + helpers)


def envelope(status_code: int, code: str, **details) -> httpx.Response:
    body = {"error": {"code": code, "message": "", "retriable": False, "details": details}}
    return httpx.Response(status_code, json=body)


def ok(body: dict):
    return lambda request: httpx.Response(200, json=body)


@pytest.fixture
def ai(monkeypatch):
    """Sidecar provider; ai(v1_incident_analyze=handler, ...) sets the AI answers per path."""
    monkeypatch.setattr(settings, "ai_provider", "sidecar")
    calls: list[httpx.Request] = []

    def answer(**routes):
        def route(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            handler = routes.get(request.url.path.strip("/").replace("/", "_").replace("-", "_"))
            return handler(request) if handler else httpx.Response(404, json={})

        transport = httpx.MockTransport(route)
        monkeypatch.setattr(
            provider, "make_client", lambda: FiboAIClient("http://ai", transport=transport, retry_waits=())
        )
        return calls

    return answer


async def incident_of(client, response) -> dict:
    assert response.status_code == 202, response.text
    incident_id = response.json()["incident_id"]
    return (await client.get(f"/api/v1/incidents/{incident_id}", headers=BOT_HEADERS)).json()


async def test_ai_card_keeps_only_cited_pages(client, operator, ai):  # noqa: F811
    telegram_id, machine, workshop = operator
    calls = ai(v1_incident_analyze=ok(ai_samples.incident()))
    incident = await incident_of(client, await upload(client, telegram_id, machine["id"]))
    assert incident["status"] == "open" and incident["ai_source"] == "ai" and incident["degraded"] == []
    assert incident["level"] == "warning" and incident["confidence"] == 0.66  # "attention" -> warning
    assert incident["manual_pages"] == [12]  # page 99 was claimed by a cause but not cited
    text = incident["card_text"]
    assert "Износ подшипника шпинделя" in text and "1. Снизить обороты" in text and "<b>" not in text
    body = json.loads(calls[0].content)
    ai_incident_schema.IncidentAnalyzeRequest.model_validate(body)  # the real AI schema accepts it
    assert body["workshop_id"] == f"ws-{workshop['id']}" and body["machine_id"] == f"m-{machine['id']}"
    assert body["voice_file_path"].startswith("/app/data/media/")
    assert body["context"]["criticality"] == "high" and body["context"]["cost_per_hour_kzt"] == 15000


async def test_danger_in_ai_findings_forces_critical(client, operator, ai):  # noqa: F811
    telegram_id, machine, _ = operator
    answer = ai_samples.incident(card={"level": "normal", "findings": ["Из двигателя пошёл дым"]})
    ai(v1_incident_analyze=ok(answer))
    incident = await incident_of(client, await upload(client, telegram_id, machine["id"]))
    assert incident["safety_triggered"] is True and incident["level"] == "critical"
    assert incident["card_text"].startswith("⛔")


async def test_ai_safety_triggers_force_critical(client, operator, ai):  # noqa: F811
    telegram_id, machine, _ = operator
    answer = ai_samples.incident(card={"level": "normal"}, signals={"safety_triggers": ["гар*"]})
    ai(v1_incident_analyze=ok(answer))
    incident = await incident_of(client, await upload(client, telegram_id, machine["id"]))
    assert incident["safety_triggered"] is True and incident["level"] == "critical"


async def test_audio_without_ai_baseline_uses_builtin(client, operator, ai):  # noqa: F811
    telegram_id, machine, _ = operator
    calls = ai()  # no AI baseline can be built: the machine has no reference recordings
    response = await upload(client, telegram_id, machine["id"], mode="machine_sound")
    incident = await incident_of(client, response)
    assert incident["ai_source"] == "builtin" and incident["degraded"] == ["ai_baseline_missing"]
    assert not [c for c in calls if c.url.path == "/v1/incident/analyze"]


async def test_ai_baseline_missing_answer_uses_builtin(client, operator, ai, monkeypatch):  # noqa: F811
    telegram_id, machine, _ = operator
    say(monkeypatch, "Шпиндель гудит на высоких оборотах")
    ai(v1_incident_analyze=lambda r: envelope(404, "BASELINE_MISSING"))
    incident = await incident_of(client, await upload(client, telegram_id, machine["id"]))
    assert incident["status"] == "open" and incident["ai_source"] == "builtin"
    assert "ai_baseline_missing" in incident["degraded"] and incident["level"] == "warning"


async def test_ai_audio_level_is_a_floor(client, operator, ai):  # noqa: F811
    telegram_id, machine, _ = operator
    artifact = {**ai_samples.BASELINE, "machine_id": f"m-{machine['id']}"}
    answer = ai_samples.incident(
        card={"level": "normal"}, signals={"audio_z": 18.5, "audio_level": "critical"}
    )
    calls = ai(v1_audio_baseline=ok(artifact), v1_incident_analyze=ok(answer))
    for seed in range(3):
        files = {"file": (f"b{seed}.wav", wav_bytes(tone(freq=200 + seed)), "audio/wav")}
        assert (
            await client.post(f"/api/v1/machines/{machine['id']}/baselines/audio", files=files)
        ).status_code == 201
    incident = await incident_of(
        client, await upload(client, telegram_id, machine["id"], mode="machine_sound")
    )
    assert incident["ai_source"] == "ai" and incident["level"] == "critical"  # the AI's measured level wins
    assert incident["audio_zscore"] is None and "18.5σ" in incident["card_text"]  # other scale: shown only
    sent = json.loads(calls[-1].content)
    ai_incident_schema.IncidentAnalyzeRequest.model_validate(sent)
    assert sent["baseline_ref"] == artifact and sent["audio_file_path"].startswith("/app/data/media/")


async def test_unreachable_ai_falls_back_to_builtin(client, operator, ai, monkeypatch):  # noqa: F811
    telegram_id, machine, _ = operator
    say(monkeypatch, "Шпиндель гудит на высоких оборотах")
    ai(v1_incident_analyze=lambda r: (_ for _ in ()).throw(httpx.ConnectError("down", request=r)))
    incident = await incident_of(client, await upload(client, telegram_id, machine["id"]))
    assert incident["status"] == "open" and incident["ai_source"] == "builtin"
    assert incident["degraded"] == ["ai_sidecar_unavailable"] and incident["level"] == "warning"


async def test_input_error_gives_retake_card(client, operator, ai):  # noqa: F811
    telegram_id, machine, _ = operator
    ai(v1_incident_analyze=lambda r: envelope(422, "PHOTO_QUALITY_LOW", retake_advice_ru="Протрите объектив"))
    files = {"file": ("tool.jpg", jpeg(tool_image()), "image/jpeg")}
    form = {"telegram_id": str(telegram_id), "machine_id": str(machine["id"])}
    response = await client.post("/api/v1/ingest/photo", data=form, files=files, headers=BOT_HEADERS)
    incident = await incident_of(client, response)
    assert incident["status"] == "open" and incident["level"] == "normal"
    assert incident["card_text"] == "📷 Протрите объектив"


async def test_rejected_request_fails_the_incident(client, operator, ai):  # noqa: F811
    telegram_id, machine, _ = operator
    ai(v1_incident_analyze=lambda r: envelope(400, "VALIDATION_ERROR"))
    incident = await incident_of(client, await upload(client, telegram_id, machine["id"]))
    assert incident["status"] == "failed" and "ai: VALIDATION_ERROR" in incident["error_message"]


async def test_builtin_provider_marks_incidents_builtin(client, operator, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "ai_provider", "builtin")
    telegram_id, machine, _ = operator
    say(monkeypatch, "Шпиндель гудит на высоких оборотах")
    incident = await incident_of(client, await upload(client, telegram_id, machine["id"]))
    assert incident["ai_source"] == "builtin" and incident["degraded"] == []


def _risk_case():
    profile = next(p for p in get_profiles().values() if p.model_applicable)
    now = utcnow()
    machine = Machine(
        id=5,
        workshop_id=2,
        name="ЧПУ",
        type="cnc_mill",
        criticality=3,
        avg_repair_hours=4.0,
        downtime_cost_per_hour_kzt=15000,
        tool_changed_at=now - timedelta(hours=2),
    )
    readings = [ReadingValues(recorded_at=now, spindle_rpm=1500, load_pct=50, temperature_c=40)]
    return profile, machine, readings, now


async def test_risk_probability_from_ai(started_app, ai):
    calls = ai(v1_risk_predict=ok(ai_samples.RISK))
    profile, machine, readings, now = _risk_case()
    p_model, version, explanation = await model_part(profile, machine, readings, now, None)
    assert (p_model, version) == (0.42, "0.1.0-stub")
    assert explanation[0]["feature"] == "spindle_load_pct" and explanation[0]["source"] == "ai"
    sent = json.loads(calls[0].content)
    ai_risk_schema.RiskRequest.model_validate(sent)  # the real AI schema accepts it
    assert sent["machine_id"] == "m-5" and sent["readings"]["spindle_load_pct"] == 50
    assert sent["readings"]["tool_hours"] == pytest.approx(2.0, abs=0.01) and "features" not in sent
    assert sent["context"]["criticality"] == "high"


@pytest.mark.parametrize(
    ("handler", "code"),
    [
        (lambda r: envelope(503, "LLM_UNAVAILABLE"), "ai_sidecar_unavailable"),
        (lambda r: envelope(400, "VALIDATION_ERROR"), "ai_rejected:VALIDATION_ERROR"),
    ],
)
async def test_risk_falls_back_to_local_model(started_app, ai, handler, code):
    ai(v1_risk_predict=handler)
    p_model, _version, explanation = await model_part(*_risk_case(), None)
    assert p_model is None  # no local artifacts in tests -> index-only, but never an exception
    assert {"kind": "note", "topic": "degraded", "code": code} in explanation


async def _panel(client, machine_id):
    files = {"file": ("panel.jpg", jpeg(tool_image()), "image/jpeg")}
    data = {"machine_id": str(machine_id)}
    return await client.post("/api/v1/readings/panel-photo", data=data, files=files, headers=BOT_HEADERS)


async def test_panel_photo_from_ai_keeps_response_shape(client, make_workshop, make_machine, ai):
    machine = await make_machine((await make_workshop())["id"])
    ai(v1_vision_panel=ok(ai_samples.PANEL))
    response = await _panel(client, machine["id"])
    assert response.status_code == 200, response.text
    result = response.json()
    assert "spindle_rpm" in [v["field"] for v in result["values"]]
    assert "load_pct" in [r["field"] for r in result["rejected"]]  # 400 % fails the backend range check
    ai(v1_vision_panel=lambda r: envelope(422, "PHOTO_QUALITY_LOW"))
    assert (await _panel(client, machine["id"])).status_code == 422
    ai(v1_vision_panel=lambda r: envelope(400, "VALIDATION_ERROR"))
    assert (await _panel(client, machine["id"])).status_code == 200  # rejected -> backend OCR, not 500


async def test_third_recording_stores_ai_baseline_artifact(client, session, make_workshop, make_machine, ai):
    machine = await make_machine((await make_workshop())["id"])
    artifact = {**ai_samples.BASELINE, "machine_id": f"m-{machine['id']}"}
    calls = ai(v1_audio_baseline=ok(artifact))
    for seed in range(3):
        files = {"file": (f"b{seed}.wav", wav_bytes(tone(freq=200 + seed)), "audio/wav")}
        response = await client.post(f"/api/v1/machines/{machine['id']}/baselines/audio", files=files)
        assert response.status_code == 201, response.text
    assert len(calls) == 1  # only once there are 3 recordings
    newest = await session.get(Baseline, response.json()["baseline"]["id"])
    await session.refresh(newest)
    assert newest.stats["ai_artifact"] == artifact and "n_recordings" in newest.stats
