"""Baseline upload API and the audio branch of the incident pipeline."""

import pytest

from app.core.config import settings
from tests.audio_samples import machine_sound, wav_bytes
from tests.conftest import BOT_HEADERS
from tests.test_pipeline import upload


@pytest.fixture(autouse=True)
def offline_audio(monkeypatch):
    monkeypatch.setattr(settings, "ffmpeg_binary", "no-such-ffmpeg-binary")


async def _baseline(client, machine_id: int, seed: int, headers=None):
    files = {"file": (f"ref{seed}.wav", wav_bytes(machine_sound(seed)), "audio/wav")}
    return await client.post(
        f"/api/v1/machines/{machine_id}/baselines/audio", files=files, headers=headers or {}
    )


@pytest.fixture
async def machine_with_baseline(client, make_workshop, make_machine):
    workshop = await make_workshop()
    machine = await make_machine(workshop["id"])
    for seed, expected_ready in ((1, False), (2, False), (3, True)):
        response = await _baseline(client, machine["id"], seed, headers=BOT_HEADERS)  # the bot may upload
        assert response.status_code == 201, response.text
        assert response.json()["ready"] is expected_ready
    body = {
        "telegram_id": 880000 + machine["id"],
        "full_name": "Ерлан",
        "invite_code": workshop["invite_code"],
        "role": "master",
    }
    assert (await client.post("/api/v1/bot/register", json=body, headers=BOT_HEADERS)).status_code == 201
    return machine, body["telegram_id"]


async def test_baselines_listed(client, machine_with_baseline):
    machine, _ = machine_with_baseline
    listed = (await client.get(f"/api/v1/machines/{machine['id']}/baselines")).json()
    assert [b["recordings_in_baseline"] for b in listed] == [1, 2, 3]
    assert all(b["kind"] == "audio" and b["url"].startswith("/api/v1/media/audio/") for b in listed)


async def test_too_short_baseline_is_422(client, make_workshop, make_machine):
    machine = await make_machine((await make_workshop())["id"])
    files = {"file": ("short.wav", wav_bytes(machine_sound(1, seconds=1.0)), "audio/wav")}
    response = await client.post(f"/api/v1/machines/{machine['id']}/baselines/audio", files=files)
    assert response.status_code == 422


async def test_healthy_sound_is_normal_with_spectrogram(client, machine_with_baseline):
    machine, telegram_id = machine_with_baseline
    data = wav_bytes(machine_sound(42))
    incident_id = (await upload(client, telegram_id, machine["id"], data=data, mode="machine_sound")).json()[
        "incident_id"
    ]
    incident = (await client.get(f"/api/v1/incidents/{incident_id}")).json()
    assert incident["status"] == "open" and incident["level"] == "normal"
    assert incident["audio_zscore"] < 2
    kinds = [a["kind"] for a in incident["attachments"]]
    assert kinds == ["audio", "spectrogram"]
    png = await client.get(incident["attachments"][1]["url"])
    assert png.status_code == 200 and png.content.startswith(b"\x89PNG")


async def test_noisy_sound_is_critical_although_mock_card_says_normal(client, machine_with_baseline):
    machine, telegram_id = machine_with_baseline
    data = wav_bytes(machine_sound(42, anomaly="noise"))
    incident_id = (await upload(client, telegram_id, machine["id"], data=data, mode="machine_sound")).json()[
        "incident_id"
    ]
    incident = (await client.get(f"/api/v1/incidents/{incident_id}")).json()
    assert incident["level"] == "critical" and incident["audio_zscore"] > 3
    assert "σ" in incident["card_text"] and "шумность спектра" in incident["card_text"]
    assert incident["manual_pages"] == []  # invented page dropped here too

    score = (await client.post("/api/v1/risk-scores/recompute", json={"machine_id": machine["id"]})).json()[0]
    assert "s_audio" in score["inputs_used"]
    assert {s["name"]: s["value"] for s in score["signals"]}["s_audio"] == 1.0
