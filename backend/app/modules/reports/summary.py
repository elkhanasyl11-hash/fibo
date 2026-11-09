"""Fibo Reports: the period summary of a workshop, and its CSV export.

build_summary loads the workshop's machines, the incidents CREATED in [date_from, date_to] and the
readings of the period, and applies the rules in downtime.py. Default period: the last 30 days.
CSV: UTF-8 with BOM (so Excel shows Cyrillic), ";" as separator (the list separator of Russian-locale
Excel), one row per machine plus a TOTAL row; numbers use a dot as decimal separator.
"""

import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainValidationError
from app.db.base import utcnow
from app.models.incident import Incident
from app.models.machine import Machine
from app.models.reading import Reading
from app.modules.reports.downtime import IncidentFacts, machine_downtime, top_causes
from app.services import workshops as workshops_service

DEFAULT_PERIOD = timedelta(days=30)
CSV_COLUMNS = [
    "machine_id",
    "machine",
    "incidents",
    "failures",
    "downtime_hours",
    "loss_kzt",
    "ongoing_hours",
    "ongoing_loss_kzt",
    "operating_hours",
    "operating_hours_source",
    "mtbf_hours",
]


def resolve_period(
    date_from: datetime | None, date_to: datetime | None, now: datetime
) -> tuple[datetime, datetime]:
    date_to = date_to or now
    date_from = date_from or date_to - DEFAULT_PERIOD
    if date_from >= date_to:
        raise DomainValidationError("'from' must be before 'to'")
    return date_from, date_to


def _facts(incident: Incident) -> IncidentFacts:
    return IncidentFacts(
        incident.status,
        incident.level,
        incident.created_at,
        incident.downtime_hours,
        incident.loss_kzt,
        list(incident.causes or []),
    )


async def build_summary(
    session: AsyncSession,
    workshop_id: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    now: datetime | None = None,
) -> dict:
    now = now or utcnow()
    workshop = await workshops_service.get_or_404(session, workshop_id)
    start, end = resolve_period(date_from, date_to, now)
    period_hours = (end - start).total_seconds() / 3600
    machine_stmt = select(Machine).where(Machine.workshop_id == workshop_id).order_by(Machine.id)
    machines = list((await session.scalars(machine_stmt)).all())
    ids = [m.id for m in machines]
    incident_stmt = select(Incident).where(
        Incident.machine_id.in_(ids), Incident.created_at >= start, Incident.created_at <= end
    )
    incidents = list((await session.scalars(incident_stmt)).all())
    counter_stmt = select(Reading.machine_id, Reading.operating_hours).where(
        Reading.machine_id.in_(ids),
        Reading.recorded_at >= start,
        Reading.recorded_at <= end,
        Reading.operating_hours.is_not(None),
    )
    counters = (await session.execute(counter_stmt)).all()

    rows, all_facts = [], []
    for machine in machines:
        facts = [_facts(i) for i in incidents if i.machine_id == machine.id]
        all_facts += facts
        values = [hours for machine_id, hours in counters if machine_id == machine.id]
        stats = machine_downtime(
            facts, machine.downtime_cost_per_hour_kzt, values, period_hours, min(now, end)
        )
        rows.append({"machine_id": machine.id, "machine": machine.name, **vars(stats)})

    return {
        "workshop_id": workshop.id,
        "workshop": workshop.name,
        "is_demo": workshop.is_demo,
        "period_from": start,
        "period_to": end,
        "totals": {
            "incidents": len(incidents),
            "failures": sum(r["failures"] for r in rows),
            "downtime_hours": round(sum(r["downtime_hours"] for r in rows), 2),
            "loss_kzt": sum((r["loss_kzt"] for r in rows), Decimal(0)),
            "ongoing_hours": round(sum(r["ongoing_hours"] for r in rows), 2),
            "ongoing_loss_kzt": sum((r["ongoing_loss_kzt"] for r in rows), Decimal(0)),
        },
        "machines": rows,
        "top_causes": [{"cause": cause, "count": count} for cause, count in top_causes(all_facts)],
    }


def to_csv(summary: dict) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for row in summary["machines"]:
        writer.writerow(["" if row[c] is None else row[c] for c in CSV_COLUMNS])
    totals = summary["totals"]
    writer.writerow(
        [
            "",
            "ИТОГО",
            totals["incidents"],
            totals["failures"],
            totals["downtime_hours"],
            totals["loss_kzt"],
            totals["ongoing_hours"],
            totals["ongoing_loss_kzt"],
            "",
            "",
            "",
        ]
    )
    return ("﻿" + buffer.getvalue()).encode("utf-8")  # BOM: Excel then reads the file as UTF-8
