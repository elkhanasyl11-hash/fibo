"""Fixes from the ECC review (group A): audio tolerance, no criticality bias, PATCH nulls, interrupted
work, deleted rows in background tasks, insecure production settings."""

from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.db.base import IncidentInput, IncidentLevel, IncidentStatus, IndexStatus, utcnow
from app.models import Incident, Manual
from app.modules.machine import audio, risk_model
from app.pipelines.incident_pipeline import process_incident
from app.pipelines.manual_pipeline import index_manual
from app.pipelines.recovery import INTERRUPTED, fail_interrupted_work

ARTIFACTS = Path(__file__).resolve().parents[1] / "ml" / "artifacts"


def test_tolerance_widens_for_small_baselines():
    factors = [audio.tolerance_factor(n) for n in (1, 2, 3, 4, 5, 9, 10, 19, 20, 60)]
    assert factors == sorted(factors, reverse=True) and factors[0] == 4.3 and factors[-1] == 1.0
    windows = np.random.default_rng(0).normal(1.0, 1.0, size=(19, len(audio.FEATURES)))
    stats = {"mean": [0.0] * len(audio.FEATURES), "std": [1.0] * len(audio.FEATURES)}
    one = audio.score(windows, {**stats, "n_recordings": 1}).audio_z
    many = audio.score(windows, {**stats, "n_recordings": 20}).audio_z
    assert one == pytest.approx(many / 4.3, rel=0.01)


async def test_failure_probability_does_not_depend_on_criticality(client, make_workshop, make_machine):
    risk_model.set_active_model(risk_model.RiskModel.load(ARTIFACTS))
    try:
        workshop = await make_workshop()
        changed = (utcnow() - timedelta(hours=3)).isoformat()
        probabilities = []
        for criticality in (1, 2, 3):
            machine = await make_machine(workshop["id"], criticality=criticality, tool_changed_at=changed)
            body = {"machine_id": machine["id"], "spindle_rpm": 1500, "load_pct": 70, "temperature_c": 37}
            await client.post("/api/v1/readings", json=body)
            url = "/api/v1/risk-scores/recompute"
            score = (await client.post(url, json={"machine_id": machine["id"]})).json()
            probabilities.append(score[0]["failure_probability"])
        assert probabilities[0] is not None and len(set(probabilities)) == 1
    finally:
        risk_model.set_active_model(None)


async def test_patch_rejects_null_on_required_fields(client, make_workshop, make_machine):
    workshop = await make_workshop()
    machine = await make_machine(workshop["id"])
    url = f"/api/v1/machines/{machine['id']}"
    for body in ({"name": None}, {"criticality": None}, {"downtime_cost_per_hour_kzt": None}):
        response = await client.patch(url, json=body)
        assert response.status_code == 422 and "cannot be null" in response.text, body
    assert (await client.patch(url, json={"model": None})).status_code == 200  # nullable column: allowed
    body = {"full_name": "А", "role": "owner", "workshop_id": workshop["id"]}
    user = (await client.post("/api/v1/users", json=body)).json()
    assert (await client.patch(f"/api/v1/users/{user['id']}", json={"role": None})).status_code == 422


async def test_interrupted_work_is_marked_failed(session, make_workshop, make_machine):
    machine = await make_machine((await make_workshop())["id"])
    stuck = Incident(
        machine_id=machine["id"],
        input_type=IncidentInput.VOICE,
        status=IncidentStatus.PROCESSING,
        safety_triggered=True,
        level=IncidentLevel.CRITICAL,
        card_text="STOP",
    )
    done = Incident(machine_id=machine["id"], input_type=IncidentInput.VOICE, status=IncidentStatus.OPEN)
    manual = Manual(
        machine_id=machine["id"],
        file_path="manual/x.pdf",
        original_filename="x.pdf",
        index_status=IndexStatus.INDEXING,
    )
    session.add_all([stuck, done, manual])
    await session.commit()

    stuck_id, done_id, manual_id = stuck.id, done.id, manual.id
    incidents, manuals = await fail_interrupted_work()
    assert incidents >= 1 and manuals >= 1
    session.expire_all()
    stuck = await session.get(Incident, stuck_id)
    assert stuck.status == IncidentStatus.FAILED and stuck.error_message == INTERRUPTED
    assert stuck.safety_triggered and stuck.card_text == "STOP"  # the stop instruction is kept
    assert (await session.get(Incident, done_id)).status == IncidentStatus.OPEN  # finished work untouched
    assert (await session.get(Manual, manual_id)).index_status == IndexStatus.FAILED


async def test_background_tasks_survive_deleted_rows(started_app):
    await process_incident(987654)  # no exception: logged and skipped
    await index_manual(987654)


def test_production_refuses_guessable_secrets():
    base = {"_env_file": None, "env": "prod", "ai_provider": "builtin"}  # sidecar token: test_ai_gateway.py
    long_key, short_key = "k" * 32, "k" * 30
    with pytest.raises(ValidationError, match="insecure production settings"):
        Settings(**base)
    with pytest.raises(ValidationError, match="FIBO_BOT_SHARED_SECRET"):
        Settings(**base, bot_shared_secret="short", dashboard_api_key=short_key)
    with pytest.raises(ValidationError, match="FIBO_WEB_SESSION_SECRET"):
        Settings(**base, bot_shared_secret="s" * 32, dashboard_api_key=long_key)
    ok = Settings(**base, bot_shared_secret="s" * 32, dashboard_api_key=long_key, web_session_secret="w" * 32)
    assert ok.insecure_reasons() == []
    assert (
        len(Settings(_env_file=None, env="dev", ai_provider="builtin").insecure_reasons()) == 3
    )  # dev: warnings (bot secret, dashboard key, web session secret)
