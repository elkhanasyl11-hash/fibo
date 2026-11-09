"""Risk API: recompute, ranking order, index-only mode, what-if never saves, history, background hook."""

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db.base import utcnow
from app.models import RiskScore
from app.modules.machine import risk_model

ARTIFACTS = Path(__file__).resolve().parents[1] / "ml" / "artifacts"


@pytest.fixture
def with_model():
    risk_model.set_active_model(risk_model.RiskModel.load(ARTIFACTS))
    yield
    risk_model.set_active_model(None)


async def _cnc(client, make_workshop, make_machine, **fields):
    workshop = await make_workshop()
    now = utcnow()
    machine = await make_machine(
        workshop["id"],
        tool_changed_at=(now - timedelta(hours=3)).isoformat(),
        last_maintenance_at=(now - timedelta(days=30)).isoformat(),
        maintenance_interval_hours=500,
        **fields,
    )
    body = {"machine_id": machine["id"], "spindle_rpm": 1500, "load_pct": 90, "temperature_c": 37}
    assert (await client.post("/api/v1/readings", json=body)).status_code == 201
    return workshop, machine


async def test_index_only_mode_without_model(client, make_workshop, make_machine):
    _, machine = await _cnc(client, make_workshop, make_machine)
    response = await client.post("/api/v1/risk-scores/recompute", json={"machine_id": machine["id"]})
    assert response.status_code == 200, response.text
    score = response.json()[0]
    assert score["failure_probability"] is None and score["model_version"] == "none"
    assert "p_model" not in score["inputs_used"] and "s_overdue" in score["inputs_used"]
    assert score["model_not_used_reasons"] == ["risk_model_not_loaded"]
    assert score["shap_top3"] == [] and len(score["signals"]) == 5


async def test_ranking_sorted_with_shap_and_inputs(client, make_workshop, make_machine, with_model):
    workshop, cheap = await _cnc(client, make_workshop, make_machine, downtime_cost_per_hour_kzt="1000.00")
    expensive = await make_machine(
        workshop["id"],
        name="ЧПУ-2",
        downtime_cost_per_hour_kzt="90000.00",
        tool_changed_at=utcnow().isoformat(),
    )
    await client.post(
        "/api/v1/readings", json={"machine_id": expensive["id"], "spindle_rpm": 1500, "load_pct": 90}
    )
    unscored = await make_machine(workshop["id"], name="Новый")
    unscored_machine = unscored["id"]
    await client.post("/api/v1/risk-scores/recompute", json={"machine_id": cheap["id"]})
    await client.post("/api/v1/risk-scores/recompute", json={"machine_id": expensive["id"]})

    body = (await client.get("/api/v1/risk-scores/ranking", params={"workshop_id": workshop["id"]})).json()
    priorities = [float(item["score"]["priority_kzt"]) for item in body["items"]]
    assert priorities == sorted(priorities, reverse=True) and priorities[0] > 0
    assert body["unscored_machine_ids"] == [unscored_machine]
    top = body["items"][0]["score"]
    assert top["failure_probability"] is not None and "p_model" in top["inputs_used"]
    assert len(top["shap_top3"]) == 3 and {"feature", "title_ru", "value", "contribution"} <= set(
        top["shap_top3"][0]
    )
    assert "torque_from_load" in {a["code"] for a in top["assumptions"]}


async def test_what_if_does_not_save_and_moves_risk(client, session, make_workshop, make_machine, with_model):
    _, machine = await _cnc(client, make_workshop, make_machine)
    before = await session.scalar(select(func.count()).select_from(RiskScore))
    body = {
        "machine_id": machine["id"],
        "overrides": {"maintenance_done": True, "load_pct": 30, "tool_wear_min": 0},
    }
    response = await client.post("/api/v1/risk-scores/what-if", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["saved"] is False and data["scenario"]["id"] is None
    assert data["scenario"]["risk_index"] < data["current"]["risk_index"]
    overdue = {s["name"]: s["value"] for s in data["scenario"]["signals"]}["s_overdue"]
    assert overdue == 0
    assert await session.scalar(select(func.count()).select_from(RiskScore)) == before

    bad = await client.post(
        "/api/v1/risk-scores/what-if", json={"machine_id": machine["id"], "overrides": {"load_pct": 999}}
    )
    assert bad.status_code == 422


async def test_new_reading_recomputes_in_background_and_history(client, make_workshop, make_machine):
    _, machine = await _cnc(client, make_workshop, make_machine)  # POST /readings schedules recompute
    await client.post("/api/v1/risk-scores/recompute", json={"machine_id": machine["id"]})
    history = (await client.get(f"/api/v1/machines/{machine['id']}/risk-history")).json()
    assert len(history) == 2  # one from the background task, one explicit
    assert history[0]["computed_at"] <= history[1]["computed_at"]
    summary = (await client.get(f"/api/v1/machines/{machine['id']}/summary")).json()
    assert summary["latest_risk"]["id"] == history[-1]["id"]


async def test_recompute_request_validation(client, make_workshop):
    assert (await client.post("/api/v1/risk-scores/recompute", json={})).status_code == 422
    both = {"machine_id": 1, "workshop_id": 1}
    assert (await client.post("/api/v1/risk-scores/recompute", json=both)).status_code == 422
    workshop = await make_workshop()
    response = await client.post("/api/v1/risk-scores/recompute", json={"workshop_id": workshop["id"]})
    assert response.status_code == 200 and response.json() == []
