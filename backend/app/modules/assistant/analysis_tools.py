"""Read-only diagnostic tools based on actual machine history and calculated scenarios."""

from datetime import timedelta

from sqlalchemy import select

from app.db.base import utcnow
from app.models.reading import Reading
from app.modules.machine import service as risk_service
from app.services import machines as machines_service


async def reading_trends(session, machine, days: int) -> dict:
    rows = list(
        await session.scalars(
            select(Reading)
            .where(Reading.machine_id == machine.id, Reading.recorded_at >= utcnow() - timedelta(days=days))
            .order_by(Reading.recorded_at, Reading.id)
        )
    )
    names = {"temperature_c", "load_pct", "spindle_rpm", "operating_hours"}
    for row in rows:
        names.update((row.extra or {}).keys())
    fields = {}
    for name in sorted(names):
        samples = [
            (
                row.recorded_at,
                getattr(row, name)
                if name in {"temperature_c", "load_pct", "spindle_rpm", "operating_hours"}
                else (row.extra or {}).get(name),
            )
            for row in rows
        ]
        samples = [(stamp, value) for stamp, value in samples if value is not None]
        if samples:
            fields[name] = {
                "samples": len(samples),
                "first": samples[0][1],
                "latest": samples[-1][1],
                "min": min(v for _, v in samples),
                "max": max(v for _, v in samples),
                "change": samples[-1][1] - samples[0][1],
                "latest_at": samples[-1][0].isoformat(),
            }
    return {
        "machine": machine.name,
        "days": days,
        "readings": len(rows),
        "fields": fields,
        "note": "Changes compare the first and last stored readings; this is not a diagnosis or forecast.",
    }


async def maintenance_plan(session, workshop_id: int) -> dict:
    machines = await machines_service.list_for_workshop(session, workshop_id, limit=200)
    scores = {machine.id: score for score, machine in await risk_service.ranking(session, workshop_id)}
    now = utcnow()
    items = []
    for machine in machines:
        elapsed = (
            (now - machine.last_maintenance_at).total_seconds() / 3600
            if machine.last_maintenance_at
            else None
        )
        remaining = (
            machine.maintenance_interval_hours - elapsed
            if elapsed is not None and machine.maintenance_interval_hours
            else None
        )
        score = scores.get(machine.id)
        items.append(
            {
                "machine_id": machine.id,
                "machine": machine.name,
                "last_maintenance_at": machine.last_maintenance_at.isoformat()
                if machine.last_maintenance_at
                else None,
                "hours_until_maintenance": round(remaining, 1) if remaining is not None else None,
                "overdue": remaining is not None and remaining < 0,
                "risk_index": score.risk_index if score else None,
                "priority_kzt": str(score.priority_kzt) if score else None,
            }
        )
    items.sort(key=lambda item: (not item["overdue"], -(float(item["priority_kzt"] or 0))))
    return {
        "machines": items,
        "note": ("Maintenance intervals are calendar hours, not operating hours. "
                 "Missing dates mean no schedule can be calculated."),
    }
