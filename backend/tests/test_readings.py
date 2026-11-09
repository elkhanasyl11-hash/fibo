"""Readings: profile-based validation, history filters, background recompute hook."""

from app.db.base import Profile
from app.modules.machine import service as risk_service
from app.profiles.loader import load_profiles
from app.services.readings import validate_reading_values

PROFILES = load_profiles()


def test_validation_rules_unit():
    metal, bakery = PROFILES[Profile.METALWORKING], PROFILES[Profile.BAKERY]
    assert validate_reading_values(metal, {"spindle_rpm": 3000, "load_pct": 60}, None) == []
    assert validate_reading_values(metal, {"load_pct": 151}, None)[0]["field"] == "load_pct"
    assert validate_reading_values(metal, {"load_pct": float("nan")}, None)  # NaN is out of range
    assert validate_reading_values(metal, {}, None)[0]["problem"] == "at least one value is required"
    assert "not used" in validate_reading_values(bakery, {"spindle_rpm": 100}, None)[0]["problem"]
    assert validate_reading_values(bakery, {}, {"humidity_pct": 80}) == []
    assert validate_reading_values(bakery, {}, {"humidity_pct": 120})[0]["field"] == "extra.humidity_pct"
    assert validate_reading_values(metal, {}, {"humidity_pct": 80})[0]["field"] == "extra.humidity_pct"


async def test_create_reading_triggers_recompute(client, make_workshop, make_machine, monkeypatch):
    calls = []

    async def fake_recompute(machine_id: int) -> None:
        calls.append(machine_id)

    monkeypatch.setattr(risk_service, "recompute_risk", fake_recompute)
    workshop = await make_workshop()
    machine = await make_machine(workshop["id"])
    body = {"machine_id": machine["id"], "spindle_rpm": 3000, "load_pct": 70, "temperature_c": 40}
    response = await client.post("/api/v1/readings", json=body)
    assert response.status_code == 201, response.text
    assert response.json()["source"] == "form"
    assert calls == [machine["id"]]


async def test_invalid_reading_lists_every_bad_field(client, make_workshop, make_machine):
    workshop = await make_workshop("bakery")
    machine = await make_machine(workshop["id"], type="dough_mixer")
    body = {
        "machine_id": machine["id"],
        "spindle_rpm": 100,
        "extra": {"humidity_pct": 150, "foo": 1},
        "recorded_at": "2099-01-01T00:00:00Z",
    }
    response = await client.post("/api/v1/readings", json=body)
    assert response.status_code == 422
    fields = {item["field"] for item in response.json()["error"]["details"]["fields"]}
    assert fields == {"spindle_rpm", "extra.humidity_pct", "extra.foo", "recorded_at"}


async def test_history_filters_newest_first(client, make_workshop, make_machine):
    workshop = await make_workshop()
    machine = await make_machine(workshop["id"])
    for day in (1, 2, 3):
        body = {"machine_id": machine["id"], "load_pct": 50 + day, "recorded_at": f"2026-10-0{day}T08:00:00Z"}
        assert (await client.post("/api/v1/readings", json=body)).status_code == 201
    url = f"/api/v1/machines/{machine['id']}/readings"
    all_rows = (await client.get(url)).json()
    assert [r["load_pct"] for r in all_rows] == [53, 52, 51]
    window = (
        await client.get(url, params={"from": "2026-10-02T00:00:00Z", "to": "2026-10-02T23:59:59Z"})
    ).json()
    assert [r["load_pct"] for r in window] == [52]
    assert (await client.get(url, params={"limit": 500})).status_code == 422
