"""Fibo Reports: downtime, losses, ongoing incidents, MTBF, top causes, CSV export."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.db.base import IncidentInput, IncidentLevel, IncidentStatus, ReadingSource
from app.models import Incident, Reading
from app.modules.reports.downtime import IncidentFacts, machine_downtime, normalise_cause, top_causes
from app.services import incidents as incidents_service

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def facts(status, level, hours_ago, downtime=None, loss=None, causes=()):
    return IncidentFacts(status, level, NOW - timedelta(hours=hours_ago), downtime, loss, list(causes))


def test_machine_downtime_rules():
    incidents = [
        facts(IncidentStatus.RESOLVED, IncidentLevel.CRITICAL, 30, 3.5, Decimal("52500.00")),
        facts(IncidentStatus.OPEN, IncidentLevel.WARNING, 2),  # still running: 2 h so far
        facts(IncidentStatus.OPEN, IncidentLevel.NORMAL, 1),  # not a failure, but still open: 1 h
    ]
    stats = machine_downtime(incidents, Decimal("15000"), [100.0, 130.0, 160.0], period_hours=720, now=NOW)
    assert (stats.incidents, stats.failures) == (3, 2)
    assert stats.downtime_hours == 3.5 and stats.loss_kzt == Decimal("52500.00")
    assert stats.ongoing_hours == 3.0 and stats.ongoing_loss_kzt == Decimal("45000.00")
    assert (stats.operating_hours, stats.operating_hours_source) == (60.0, "counter")
    assert stats.mtbf_hours == 30.0  # 60 operating hours / 2 failures


def test_calendar_fallback_and_no_failures():
    stats = machine_downtime([], Decimal("1000"), [], period_hours=720, now=NOW)
    assert stats.operating_hours_source == "calendar" and stats.operating_hours == 720
    assert stats.mtbf_hours is None and stats.loss_kzt == Decimal("0.00")


def test_top_causes_are_normalised():
    incidents = [
        facts(IncidentStatus.OPEN, None, 1, causes=["Износ подшипников", "смазка"]),
        facts(IncidentStatus.OPEN, None, 1, causes=["износ  подшипников.", ""]),
    ]
    assert top_causes(incidents) == [("износ подшипников", 2), ("смазка", 1)]
    assert normalise_cause("  Износ Подшипников ") == "износ подшипников"


async def _workshop_with_history(session, make_workshop, make_machine):
    workshop = await make_workshop(name="Отчётный цех")
    machine = await make_machine(workshop["id"], downtime_cost_per_hour_kzt="15000.00")
    resolved = Incident(
        machine_id=machine["id"],
        input_type=IncidentInput.VOICE,
        level=IncidentLevel.CRITICAL,
        status=IncidentStatus.OPEN,
        created_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
        causes=["Износ подшипников"],
    )
    outside = Incident(
        machine_id=machine["id"],
        input_type=IncidentInput.VOICE,
        level=IncidentLevel.WARNING,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )  # before the period
    session.add_all([resolved, outside])
    for day, hours in ((1, 1000.0), (5, 1040.0)):
        session.add(
            Reading(
                machine_id=machine["id"],
                source=ReadingSource.FORM,
                operating_hours=hours,
                recorded_at=datetime(2026, 11, day, 8, 0, tzinfo=UTC),
            )
        )
    await session.commit()
    await incidents_service.resolve_incident(
        session, resolved.id, now=datetime(2026, 11, 1, 13, 30, tzinfo=UTC)
    )
    return workshop, machine


PERIOD = {"from": "2026-10-25T00:00:00Z", "to": "2026-11-06T00:00:00Z"}


async def test_summary_endpoint(client, session, make_workshop, make_machine):
    workshop, machine = await _workshop_with_history(session, make_workshop, make_machine)
    report = (
        await client.get("/api/v1/reports/summary", params={"workshop_id": workshop["id"], **PERIOD})
    ).json()
    assert report["totals"]["incidents"] == 1  # the September incident is outside the period
    assert report["totals"]["loss_kzt"] == "52500.00" and report["totals"]["downtime_hours"] == 3.5
    row = report["machines"][0]
    assert row["machine_id"] == machine["id"] and row["operating_hours"] == 40.0
    assert row["operating_hours_source"] == "counter" and row["mtbf_hours"] == 40.0
    assert report["top_causes"] == [{"cause": "износ подшипников", "count": 1}]
    assert report["is_demo"] is False


async def test_csv_export(client, session, make_workshop, make_machine):
    workshop, _ = await _workshop_with_history(session, make_workshop, make_machine)
    response = await client.get(
        "/api/v1/reports/export.csv", params={"workshop_id": workshop["id"], **PERIOD}
    )
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM for Excel
    lines = response.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("machine_id;machine;incidents") and "ЧПУ-1" in lines[1]
    assert lines[-1].startswith(";ИТОГО;1;1;3.5;52500.00")


async def test_period_validation(client, make_workshop):
    workshop = await make_workshop()
    params = {"workshop_id": workshop["id"]}
    assert (await client.get("/api/v1/reports/summary", params=params)).status_code == 200  # last 30 days
    naive = {**params, "from": "2026-11-01T00:00:00"}
    assert (await client.get("/api/v1/reports/summary", params=naive)).status_code == 422
    reversed_period = {**params, "from": "2026-11-05T00:00:00Z", "to": "2026-11-01T00:00:00Z"}
    assert (await client.get("/api/v1/reports/summary", params=reversed_period)).status_code == 422
    assert (await client.get("/api/v1/reports/summary", params={"workshop_id": 999999})).status_code == 404
