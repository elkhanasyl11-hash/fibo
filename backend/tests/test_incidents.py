"""Incidents: create (as ingest will), feed filters, detail with attachment URLs, resolve maths."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.errors import ConflictError
from app.db.base import IncidentInput, IncidentLevel, IncidentStatus
from app.models import Incident, Machine
from app.services import incidents as incidents_service

T0 = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)


def test_compute_downtime_exact():
    hours, loss = incidents_service.compute_downtime(
        T0, datetime(2026, 11, 7, 13, 30, tzinfo=UTC), Decimal("15000")
    )
    assert hours == 3.5 and loss == Decimal("52500.00")
    # 20 minutes at 10 000 KZT/h = 3333.333... -> rounded half-up to the tiyn
    hours, loss = incidents_service.compute_downtime(
        T0, datetime(2026, 11, 7, 10, 20, tzinfo=UTC), Decimal("10000")
    )
    assert hours == 0.3333 and loss == Decimal("3333.33")


async def _machine(session, make_workshop, make_machine, cost: str = "15000.00") -> Machine:
    workshop = await make_workshop()
    data = await make_machine(workshop["id"], downtime_cost_per_hour_kzt=cost)
    return await session.get(Machine, data["id"])


async def test_resolve_with_fixed_timestamps(session, make_workshop, make_machine):
    machine = await _machine(session, make_workshop, make_machine)
    incident = Incident(
        machine_id=machine.id, input_type=IncidentInput.VOICE, created_at=T0, status=IncidentStatus.OPEN
    )
    session.add(incident)
    await session.commit()

    resolved = await incidents_service.resolve_incident(
        session, incident.id, now=datetime(2026, 11, 7, 13, 30, tzinfo=UTC)
    )
    assert resolved.status == "resolved"
    assert resolved.resolved_at == datetime(2026, 11, 7, 13, 30, tzinfo=UTC)
    assert resolved.downtime_hours == 3.5
    assert resolved.loss_kzt == Decimal("52500.00")

    with pytest.raises(ConflictError):
        await incidents_service.resolve_incident(session, incident.id)


async def test_incident_api_flow(client, session, make_workshop, make_machine):
    machine = await _machine(session, make_workshop, make_machine)
    incident = await incidents_service.create_received(
        session,
        machine=machine,
        user=None,
        input_type=IncidentInput.PHOTO,
        attachment_path="photo/2026/11/x.png",
    )
    assert incident.status == "received"

    detail = await client.get(f"/api/v1/incidents/{incident.id}")
    assert detail.status_code == 200
    attachment = detail.json()["attachments"][0]
    assert attachment["kind"] == "photo" and attachment["url"] == "/api/v1/media/photo/2026/11/x.png"

    feed = await client.get(
        "/api/v1/incidents", params={"workshop_id": machine.workshop_id, "status": "received"}
    )
    assert [i["id"] for i in feed.json()] == [incident.id]
    other = await client.get("/api/v1/incidents", params={"machine_id": machine.id, "status": "open"})
    assert other.json() == []

    still_analysing = await client.patch(f"/api/v1/incidents/{incident.id}/resolve")
    assert still_analysing.status_code == 409  # audit fix: no "Resolved" while the pipeline runs
    assert still_analysing.json()["error"]["details"]["status"] == "received"
    incident.status = IncidentStatus.OPEN  # the pipeline finished
    await session.commit()

    resolved = await client.patch(f"/api/v1/incidents/{incident.id}/resolve")
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["status"] == "resolved" and body["downtime_hours"] >= 0
    assert isinstance(body["loss_kzt"], str)

    again = await client.patch(f"/api/v1/incidents/{incident.id}/resolve")
    assert again.status_code == 409 and again.json()["error"]["code"] == "conflict"
    assert (await client.get("/api/v1/incidents/999999")).status_code == 404


async def test_feed_level_filter(client, session, make_workshop, make_machine):
    machine = await _machine(session, make_workshop, make_machine)
    session.add_all(
        [
            Incident(machine_id=machine.id, input_type=IncidentInput.VOICE, level=IncidentLevel.CRITICAL),
            Incident(machine_id=machine.id, input_type=IncidentInput.VOICE, level=IncidentLevel.NORMAL),
        ]
    )
    await session.commit()
    feed = await client.get("/api/v1/incidents", params={"machine_id": machine.id, "level": "critical"})
    assert [i["level"] for i in feed.json()] == ["critical"]
