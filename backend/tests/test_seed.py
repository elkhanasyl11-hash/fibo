"""Demo seed: creates labelled demo data, is idempotent, --reset recreates without touching real data."""

from sqlalchemy import func, select

from app.db.seed import seed
from app.models import Incident, Machine, Reading, Workshop


async def _count(session, model, *where):
    return await session.scalar(select(func.count()).select_from(model).where(*where))


async def test_seed_creates_labelled_demo_data(session, make_workshop):
    real = await make_workshop(name="Настоящий цех")
    result = await seed(session, reset=True, risk_history_days=1)
    assert result.created and result.workshops == 2 and result.machines == 9
    assert result.readings == 9 * 60 and result.incidents == 6 and result.risk_scores == 9 * 2

    assert await _count(session, Workshop, Workshop.is_demo) == 2
    assert (
        await _count(
            session,
            Machine,
            Machine.is_demo.is_(False),
            Machine.workshop_id.in_(select(Workshop.id).where(Workshop.is_demo)),
        )
        == 0
    )
    assert (
        await _count(
            session,
            Reading,
            Reading.is_demo.is_(False),
            Reading.machine_id.in_(select(Machine.id).where(Machine.is_demo)),
        )
        == 0
    )
    resolved = (
        await session.scalars(select(Incident).where(Incident.is_demo, Incident.resolved_at.isnot(None)))
    ).all()
    assert {i.downtime_hours for i in resolved} == {5.5, 2.0, 8.0}

    assert (await seed(session)).created is False  # second run without --reset: no duplicates
    again = await seed(session, reset=True, risk_history_days=0)
    assert again.created and await _count(session, Workshop, Workshop.is_demo) == 2
    assert await session.get(Workshop, real["id"]) is not None  # real workshop untouched


async def test_seeded_demo_is_visible_and_labelled_via_api(client, session):
    await seed(session, reset=True, risk_history_days=0)
    workshop = await session.scalar(select(Workshop).where(Workshop.invite_code == "DEMO01"))
    machines = (await client.get("/api/v1/machines", params={"workshop_id": workshop.id})).json()
    assert len(machines) == 6 and all(m["is_demo"] for m in machines)
    feed = (await client.get("/api/v1/incidents", params={"workshop_id": workshop.id})).json()
    assert feed and all(i["is_demo"] for i in feed)
