"""Demo data: two synthetic workshops for the live demo and for the frontend team.

Run from backend/ after `alembic upgrade head`:
    python -m app.db.seed            # create the demo data if it does not exist yet
    python -m app.db.seed --reset    # delete all demo workshops (and everything in them), recreate

Honesty rule: every row created here has is_demo=True (workshops, machines, readings, incidents)
and the workshop names say "демо-данные". Real workshops are never touched: --reset deletes only
workshops with is_demo=True. Random values use a fixed seed, so every run creates the same data
(timestamps are relative to "now", so the history always ends today).
"""

import argparse
import asyncio
import random
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import IncidentInput, IncidentLevel, IncidentStatus, Profile, ReadingSource, Role, utcnow
from app.db.seed_data import (
    BAKERY_BATCH_VALUE_KZT,
    BAKERY_MACHINES,
    DEMO_INCIDENTS,
    DRIFTING_MACHINES,
    FOOD_TEMPERATURE_C,
    METAL_MACHINES,
    TOOL_CHANGED_HOURS_AGO,
)
from app.db.session import SessionLocal
from app.models import Incident, Machine, Reading, User, Workshop
from app.modules.machine.risk_model import RiskModel, set_active_model
from app.modules.machine.service import compute_score, save_score
from app.services.incidents import compute_downtime

READING_DAYS = 30
READINGS_PER_DAY = 2


@dataclass
class SeedResult:
    created: bool
    workshops: int = 0
    machines: int = 0
    readings: int = 0
    incidents: int = 0
    risk_scores: int = 0


def _machines(workshop: Workshop, rows: list, now, batch_value: str | None) -> list[Machine]:
    return [
        Machine(
            workshop=workshop,
            name=name,
            type=type_,
            model=model,
            criticality=crit,
            downtime_cost_per_hour_kzt=Decimal(cost),
            avg_repair_hours=repair,
            maintenance_interval_hours=interval,
            last_maintenance_at=now - timedelta(days=days_since),
            tool_changed_at=now - timedelta(hours=TOOL_CHANGED_HOURS_AGO[name])
            if name in TOOL_CHANGED_HOURS_AGO
            else None,
            batch_value_kzt=Decimal(batch_value) if batch_value else None,
            is_demo=True,
        )
        for name, type_, model, crit, cost, repair, interval, days_since in rows
    ]


def _readings(machine: Machine, rng: random.Random, now, drifting: bool) -> list[Reading]:
    """Twice-daily readings for 30 days. A drifting machine's load and temperature rise in the last week."""
    readings = []
    total = READING_DAYS * READINGS_PER_DAY
    for i in range(total):
        recorded_at = now - timedelta(hours=12 * (total - i))
        drift = max(0, i - (total - 14)) / 14 if drifting else 0.0  # 0 -> 1 over the last 7 days
        values: dict = {"operating_hours": round(4200 + i * 9.5, 1), "extra": None}
        if machine.type in {"cnc_mill", "lathe"}:
            values["spindle_rpm"] = round(rng.gauss(2800 if machine.type == "cnc_mill" else 1200, 120))
            values["load_pct"] = round(rng.gauss(55 + 30 * drift, 4), 1)
            values["temperature_c"] = round(rng.gauss(36 + 22 * drift, 1.5), 1)
        elif machine.type in {"dough_mixer", "deck_oven", "proofer"}:
            values["temperature_c"] = round(rng.gauss(FOOD_TEMPERATURE_C.get(machine.type, 28), 3), 1)
            values["extra"] = {"humidity_pct": round(rng.gauss(75 - 15 * drift, 2), 1)}
        else:
            values["temperature_c"] = round(rng.gauss(45, 2), 1)
        readings.append(
            Reading(
                machine=machine, recorded_at=recorded_at, source=ReadingSource.FORM, is_demo=True, **values
            )
        )
    return readings


def _incident(
    machine: Machine,
    user: User,
    now,
    *,
    days_ago: float,
    input_type: str,
    level: str,
    verdict: str,
    causes: list[str],
    transcript: str | None = None,
    hours_to_fix: float | None = None,
    safety: bool = False,
) -> Incident:
    """One demo incident; resolved ones get downtime/loss from the same formula as the API."""
    created_at = now - timedelta(days=days_ago)
    incident = Incident(
        machine=machine,
        user=user,
        input_type=IncidentInput(input_type),
        transcript=transcript,
        verdict=verdict,
        level=IncidentLevel(level),
        confidence=0.7,
        causes=causes,
        manual_pages=[],
        status=IncidentStatus.OPEN,
        card_text=f"[ДЕМО] {verdict}",
        safety_triggered=safety,
        created_at=created_at,
        is_demo=True,
    )
    if hours_to_fix is not None:  # resolved: same formula as PATCH /incidents/{id}/resolve
        incident.status = IncidentStatus.RESOLVED
        incident.resolved_at = created_at + timedelta(hours=hours_to_fix)
        incident.downtime_hours, incident.loss_kzt = compute_downtime(
            created_at, incident.resolved_at, machine.downtime_cost_per_hour_kzt
        )
    return incident


async def seed(session: AsyncSession, reset: bool = False, risk_history_days: int = 7) -> SeedResult:
    existing = await session.scalar(select(func.count()).select_from(Workshop).where(Workshop.is_demo))
    if existing and not reset:
        return SeedResult(created=False)
    if existing:
        await session.execute(delete(Workshop).where(Workshop.is_demo))  # cascades to everything inside
        await session.commit()
        # The bulk delete bypasses the session, so forget any objects it still holds: SQLite reuses
        # the freed ids and the new rows would otherwise clash with the stale ones.
        session.expunge_all()

    rng = random.Random(42)
    now = utcnow()
    metal = Workshop(
        name="Цех «Шымкент Металл» (демо-данные)",
        city="Шымкент",
        profile=Profile.METALWORKING,
        invite_code="DEMO01",
        is_demo=True,
    )
    bakery = Workshop(
        name="Пекарня «Нан» (демо-данные)",
        city="Шымкент",
        profile=Profile.BAKERY,
        invite_code="DEMO02",
        is_demo=True,
    )
    operator = User(workshop=metal, full_name="Айбек (демо-оператор)", role=Role.OPERATOR)
    master = User(workshop=metal, full_name="Ерлан (демо-механик)", role=Role.MASTER)
    owner = User(workshop=metal, full_name="Гульнара (демо-владелец)", role=Role.OWNER)
    baker = User(workshop=bakery, full_name="Мадина (демо-пекарь)", role=Role.OPERATOR, language="kk")

    users = {"operator": operator, "master": master, "baker": baker}

    metal_machines = _machines(metal, METAL_MACHINES, now, batch_value=None)
    bakery_machines = _machines(bakery, BAKERY_MACHINES, now, batch_value=BAKERY_BATCH_VALUE_KZT)
    machines_by_name = {m.name: m for m in metal_machines + bakery_machines}
    readings = []
    for machine in machines_by_name.values():
        readings += _readings(machine, rng, now, drifting=machine.name in DRIFTING_MACHINES)

    incidents = []
    for spec in DEMO_INCIDENTS:
        spec = dict(spec)
        machine, user = machines_by_name[spec.pop("machine")], users[spec.pop("user")]
        incidents.append(_incident(machine, user, now, **spec))
    session.add_all([metal, bakery, operator, master, owner, baker, *readings, *incidents])
    await session.commit()

    # Risk history for the chart: one score per day "as of" that day, computed exactly like the API.
    scores = 0
    for machine in machines_by_name.values():
        for days_back in range(risk_history_days, -1, -1):
            await save_score(
                session, await compute_score(session, machine.id, as_of=now - timedelta(days=days_back))
            )
            scores += 1
    return SeedResult(
        created=True,
        workshops=2,
        machines=len(machines_by_name),
        readings=len(readings),
        incidents=len(incidents),
        risk_scores=scores,
    )


async def main(reset: bool) -> None:
    set_active_model(RiskModel.load_or_none(settings.risk_model_dir))  # index-only mode if missing
    async with SessionLocal() as session:
        result = await seed(session, reset=reset)
    if result.created:
        print(f"Demo data created: {result}. Bot invite codes: DEMO01 (metalworking), DEMO02 (bakery).")
    else:
        print("Demo data already exists. Use --reset to recreate it.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create synthetic demo data (is_demo=True).")
    parser.add_argument("--reset", action="store_true", help="delete demo workshops first, then recreate")
    asyncio.run(main(parser.parse_args().reset))
