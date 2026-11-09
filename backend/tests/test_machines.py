"""Machines CRUD, money format, timezone rule, summary."""


async def test_machine_crud_and_money_format(client, make_workshop, make_machine):
    workshop = await make_workshop()
    machine = await make_machine(workshop["id"], downtime_cost_per_hour_kzt=25000.5)
    assert machine["downtime_cost_per_hour_kzt"] == "25000.50"  # string with 2 decimals
    assert machine["is_demo"] is False

    patched = await client.patch(f"/api/v1/machines/{machine['id']}", json={"criticality": 1})
    assert patched.json()["criticality"] == 1

    listed = await client.get("/api/v1/machines", params={"workshop_id": workshop["id"]})
    assert [m["id"] for m in listed.json()] == [machine["id"]]

    assert (await client.delete(f"/api/v1/machines/{machine['id']}")).status_code == 204
    assert (await client.get(f"/api/v1/machines/{machine['id']}")).status_code == 404


async def test_machine_validation(client, make_workshop):
    workshop = await make_workshop()
    base = {"workshop_id": workshop["id"], "name": "M", "type": "lathe"}
    assert (await client.post("/api/v1/machines", json={**base, "criticality": 4})).status_code == 422
    assert (
        await client.post("/api/v1/machines", json={**base, "downtime_cost_per_hour_kzt": "1.234"})
    ).status_code == 422
    naive = {**base, "last_maintenance_at": "2026-11-01T10:00:00"}
    assert (await client.post("/api/v1/machines", json=naive)).status_code == 422
    aware = {**base, "last_maintenance_at": "2026-11-01T10:00:00+05:00"}
    response = await client.post("/api/v1/machines", json=aware)
    assert response.status_code == 201
    assert response.json()["last_maintenance_at"].startswith("2026-11-01T05:00:00")  # stored as UTC
    assert (await client.post("/api/v1/machines", json={**base, "workshop_id": 99999})).status_code == 404


async def test_summary_of_new_machine(client, make_workshop, make_machine):
    workshop = await make_workshop()
    machine = await make_machine(workshop["id"])
    response = await client.get(f"/api/v1/machines/{machine['id']}/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["machine"]["id"] == machine["id"]
    assert body["latest_risk"] is None
    assert body["open_incidents"] == [] and body["recent_readings"] == []
