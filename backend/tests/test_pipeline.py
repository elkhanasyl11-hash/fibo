"""End-to-end in mock mode: bot upload -> background pipeline -> incident card; safety; failures; retry."""

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.errors import ExternalServiceError
from app.models import RiskScore
from app.modules.assistant import mock_fixtures, safety, speech
from app.pipelines import incident_pipeline
from tests.audio_samples import silence_wav, tone, wav_bytes
from tests.conftest import BOT_HEADERS

TELEGRAM_ID = 700000


@pytest.fixture(autouse=True)
def offline_audio(monkeypatch):
    monkeypatch.setattr(settings, "ffmpeg_binary", "no-such-ffmpeg-binary")


@pytest.fixture
async def operator(client, make_workshop, make_machine):
    """A workshop with one machine and a registered operator; returns (telegram_id, machine)."""
    workshop = await make_workshop()
    machine = await make_machine(workshop["id"])
    operator.counter = getattr(operator, "counter", 0) + 1
    telegram_id = TELEGRAM_ID + operator.counter
    body = {
        "telegram_id": telegram_id,
        "full_name": "Айбек",
        "invite_code": workshop["invite_code"],
        "role": "operator",
        "language": "ru",
    }
    assert (await client.post("/api/v1/bot/register", json=body, headers=BOT_HEADERS)).status_code == 201
    return telegram_id, machine, workshop


def say(monkeypatch, transcript: str) -> None:
    """Make the mock transcribe return `transcript` and VAD report speech."""
    monkeypatch.setattr(mock_fixtures, "MOCK_TRANSCRIPTS", [transcript])
    monkeypatch.setattr(speech, "has_speech", lambda _path: True)


async def upload(
    client,
    telegram_id,
    machine_id,
    data=None,
    mode="auto",
    headers=BOT_HEADERS,
    name="voice.wav",
    content_type="audio/wav",
):
    files = {"file": (name, data if data is not None else wav_bytes(tone()), content_type)}
    form = {"telegram_id": str(telegram_id), "machine_id": str(machine_id), "mode": mode}
    return await client.post("/api/v1/ingest/voice", data=form, files=files, headers=headers)


async def test_voice_to_card(client, session, operator, monkeypatch):
    telegram_id, machine, _ = operator
    say(monkeypatch, "Шпиндель гудит на высоких оборотах")
    response = await upload(client, telegram_id, machine["id"])
    assert response.status_code == 202, response.text
    incident_id = response.json()["incident_id"]

    incident = (await client.get(f"/api/v1/incidents/{incident_id}", headers=BOT_HEADERS)).json()
    assert incident["status"] == "open" and incident["level"] == "warning"
    assert incident["transcript"] == "Шпиндель гудит на высоких оборотах"
    assert incident["safety_triggered"] is False
    assert incident["manual_pages"] == []  # the mock's invented page 999 was dropped
    assert machine["name"] in incident["card_text"] and "Возможные причины" in incident["card_text"]
    assert incident["attachments"][0]["kind"] == "voice"
    scores = await session.scalar(
        select(func.count()).select_from(RiskScore).where(RiskScore.machine_id == machine["id"])
    )
    assert scores == 1  # risk recomputed after the incident


async def test_safety_keyword_forces_critical_although_mock_says_normal(client, operator, monkeypatch):
    telegram_id, machine, _ = operator
    say(monkeypatch, "Из электрощита идут искры и запах гари")  # mock: no rule -> urgency low -> normal
    incident_id = (await upload(client, telegram_id, machine["id"])).json()["incident_id"]
    incident = (await client.get(f"/api/v1/incidents/{incident_id}")).json()
    assert incident["status"] == "open"
    assert incident["level"] == "critical" and incident["safety_triggered"] is True
    assert incident["card_text"].startswith(safety.STOP_HEADER)


async def test_failure_keeps_safety_card_and_retry_recovers(client, operator, monkeypatch):
    telegram_id, machine, _ = operator
    say(monkeypatch, "Из двигателя пошёл дым")

    async def broken(*args, **kwargs):
        raise ExternalServiceError("AI provider is unavailable", details={"provider": "test"})

    monkeypatch.setattr(incident_pipeline, "extract_symptoms", broken)
    incident_id = (await upload(client, telegram_id, machine["id"])).json()["incident_id"]
    failed = (await client.get(f"/api/v1/incidents/{incident_id}")).json()
    assert failed["status"] == "failed" and failed["error_message"].startswith("extraction:")
    assert failed["safety_triggered"] is True and failed["level"] == "critical"
    assert failed["card_text"].startswith(safety.STOP_HEADER)

    monkeypatch.undo()
    say(monkeypatch, "Из двигателя пошёл дым")
    monkeypatch.setattr(settings, "ffmpeg_binary", "no-such-ffmpeg-binary")
    assert (await client.post(f"/api/v1/incidents/{incident_id}/retry")).status_code == 202
    recovered = (await client.get(f"/api/v1/incidents/{incident_id}")).json()
    assert (
        recovered["status"] == "open"
        and recovered["level"] == "critical"
        and recovered["error_message"] is None
    )
    assert (await client.post(f"/api/v1/incidents/{incident_id}/retry")).status_code == 409


async def test_machine_sound_without_baseline(client, operator):
    telegram_id, machine, _ = operator
    incident_id = (await upload(client, telegram_id, machine["id"], mode="machine_sound")).json()[
        "incident_id"
    ]
    incident = (await client.get(f"/api/v1/incidents/{incident_id}")).json()
    assert incident["input_type"] == "audio" and incident["status"] == "open"
    assert incident["transcript"] is None and "эталонной записи" in incident["card_text"]


async def test_empty_recording_asks_to_check_the_microphone(client, operator):
    """Telegram Desktop without microphone access sends digital silence: say so, not "no baseline"."""
    telegram_id, machine, _ = operator
    incident_id = (await upload(client, telegram_id, machine["id"], data=silence_wav())).json()["incident_id"]
    incident = (await client.get(f"/api/v1/incidents/{incident_id}")).json()
    assert incident["input_type"] == "voice" and incident["transcript"] is None
    assert incident["verdict"] == "Пустая запись" and "микрофон" in incident["card_text"]
    assert incident["level"] is None and incident["status"] == "resolved"  # not an open incident
    assert "эталон" not in incident["card_text"]


async def test_voice_without_words_and_no_baseline_asks_to_repeat(client, operator, monkeypatch):
    telegram_id, machine, _ = operator
    monkeypatch.setattr(speech, "has_speech", lambda wav: False)
    incident_id = (await upload(client, telegram_id, machine["id"])).json()["incident_id"]
    incident = (await client.get(f"/api/v1/incidents/{incident_id}")).json()
    assert incident["verdict"] == "Речь не распознана" and "текстом" in incident["card_text"]
    assert incident["status"] == "resolved" and incident["level"] is None


async def test_empty_machine_sound_recording_is_not_scored(client, operator):
    telegram_id, machine, _ = operator
    response = await upload(client, telegram_id, machine["id"], data=silence_wav(), mode="machine_sound")
    incident = (await client.get(f"/api/v1/incidents/{response.json()['incident_id']}")).json()
    assert incident["input_type"] == "audio" and incident["verdict"] == "Пустая запись"


async def test_typed_message_to_card(client, operator, monkeypatch):
    telegram_id, machine, _ = operator
    body = {
        "telegram_id": telegram_id,
        "machine_id": machine["id"],
        "text": "  Шпиндель гудит на высоких оборотах ",
    }
    response = await client.post("/api/v1/ingest/text", json=body, headers=BOT_HEADERS)
    assert response.status_code == 202, response.text
    incident = (await client.get(f"/api/v1/incidents/{response.json()['incident_id']}")).json()
    assert incident["input_type"] == "text" and incident["status"] == "open"
    assert incident["transcript"] == "Шпиндель гудит на высоких оборотах" and incident["card_text"]


async def test_typed_message_runs_the_safety_layer(client, operator):
    telegram_id, machine, _ = operator
    body = {"telegram_id": telegram_id, "machine_id": machine["id"], "text": "Из двигателя пошёл дым"}
    response = await client.post("/api/v1/ingest/text", json=body, headers=BOT_HEADERS)
    incident = (await client.get(f"/api/v1/incidents/{response.json()['incident_id']}")).json()
    assert incident["safety_triggered"] is True and incident["level"] == "critical"
    assert incident["card_text"].startswith(safety.STOP_HEADER)


@pytest.mark.parametrize("text", ["", "   "])
async def test_typed_message_must_not_be_empty(client, operator, text):
    telegram_id, machine, _ = operator
    body = {"telegram_id": telegram_id, "machine_id": machine["id"], "text": text}
    assert (await client.post("/api/v1/ingest/text", json=body, headers=BOT_HEADERS)).status_code == 422


async def test_typed_message_needs_bot_token_and_own_machine(client, operator, make_workshop, make_machine):
    telegram_id, machine, _ = operator
    body = {"telegram_id": telegram_id, "machine_id": machine["id"], "text": "шум"}
    assert (await client.post("/api/v1/ingest/text", json=body)).status_code == 401
    other = await make_machine((await make_workshop())["id"])
    foreign = {**body, "machine_id": other["id"]}
    assert (await client.post("/api/v1/ingest/text", json=foreign, headers=BOT_HEADERS)).status_code == 404


async def test_escalate_returns_masters(client, operator, monkeypatch):
    telegram_id, machine, workshop = operator
    body = {
        "telegram_id": 790001,
        "full_name": "Ерлан",
        "invite_code": workshop["invite_code"],
        "role": "master",
    }
    assert (await client.post("/api/v1/bot/register", json=body, headers=BOT_HEADERS)).status_code == 201
    say(monkeypatch, "Станок стучит")
    incident_id = (await upload(client, telegram_id, machine["id"])).json()["incident_id"]
    target = (await client.post(f"/api/v1/incidents/{incident_id}/escalate", headers=BOT_HEADERS)).json()
    assert target["master_telegram_ids"] == [790001] and target["machine_name"] == machine["name"]
    assert target["card_text"]


async def test_ingest_rejections(client, operator, make_workshop, make_machine):
    telegram_id, machine, _ = operator
    assert (await upload(client, telegram_id, machine["id"], headers={})).status_code == 401
    assert (await upload(client, 123, machine["id"])).status_code == 404  # unknown Telegram user
    other = await make_machine((await make_workshop())["id"])
    assert (await upload(client, telegram_id, other["id"])).status_code == 404  # another workshop's machine
    bad = await upload(
        client,
        telegram_id,
        machine["id"],
        data=b"MZ" + b"\x00" * 64,
        name="x.exe",
        content_type="application/octet-stream",
    )
    assert bad.status_code == 415
