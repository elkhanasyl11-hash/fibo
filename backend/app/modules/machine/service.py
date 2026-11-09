"""Fibo Machine: risk service — recompute (and store), ranking, what-if, history.

compute_score() is the single place where a score is computed. recompute (stores the result),
what-if (never stores) and the demo seed's history all call it, so they can never disagree.

Steps of compute_score(machine, as_of, overrides):
  1. inputs.load_inputs: readings, incidents, maintenance as of that moment
  2. what-if overrides are applied to plain copies (never to database rows)
  3. model (only if the profile allows it): feature_map -> AI service or local RiskModel -> p + SHAP
     (risk_model_part.py)
  4. Isolation Forest on the reading history
  5. signals -> risk_index (weights from the profile) -> priority_kzt
All CPU-heavy parts (XGBoost, SHAP, Isolation Forest) run in asyncio.to_thread.
"""

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.db.session import SessionLocal
from app.models.machine import Machine
from app.models.risk_score import RiskScore
from app.models.workshop import Workshop
from app.modules.machine import risk_index as ri
from app.modules.machine.anomaly import detect_anomaly
from app.modules.machine.feature_map import ReadingValues
from app.modules.machine.inputs import load_inputs
from app.modules.machine.priority import priority_kzt
from app.modules.machine.risk_model_part import model_part
from app.profiles.loader import get_profiles
from app.schemas.risk_score import WhatIfOverrides
from app.services import machines as machines_service

logger = logging.getLogger("fibo.machine.service")


@dataclass
class ScoreResult:
    machine_id: int
    computed_at: datetime
    failure_probability: float | None
    risk_index: float
    priority_kzt: Decimal
    shap_factors: list[dict]  # kind = "shap" | "signal" | "note"
    is_anomaly: bool
    inputs_used: list[str]
    model_version: str
    is_demo: bool  # from the machine; not stored (risk_scores has no such column)


def _apply_overrides(readings: list[ReadingValues], overrides: WhatIfOverrides, as_of: datetime):
    changes = {
        k: v
        for k, v in overrides.model_dump(include={"load_pct", "spindle_rpm", "temperature_c"}).items()
        if v is not None
    }
    if not changes:
        return readings
    if not readings:
        return [ReadingValues(recorded_at=as_of, **changes)]
    return [*readings[:-1], replace(readings[-1], **changes)]


async def compute_score(
    session: AsyncSession,
    machine_id: int,
    as_of: datetime | None = None,
    overrides: WhatIfOverrides | None = None,
) -> ScoreResult:
    as_of = as_of or utcnow()
    machine = await machines_service.get_or_404(session, machine_id)
    workshop = await session.get(Workshop, machine.workshop_id)
    profile = get_profiles()[workshop.profile]
    inputs = await load_inputs(session, machine, as_of)
    readings = inputs.readings
    hours_since_maintenance = inputs.hours_since_maintenance
    if overrides is not None:
        readings = _apply_overrides(readings, overrides, as_of)
        if overrides.maintenance_done:
            hours_since_maintenance = 0.0

    p_model, model_version, explanation = await model_part(
        profile, machine, readings, as_of, overrides.tool_wear_min if overrides else None
    )

    anomaly = await asyncio.to_thread(detect_anomaly, [vars(r) for r in readings])
    explanation.append(
        {"kind": "note", "topic": "anomaly", "code": anomaly.reason, "columns": anomaly.columns}
    )

    signals = ri.Signals(
        p_model=p_model,
        s_audio=ri.audio_signal(inputs.audio_z),
        s_visual=ri.visual_signal(inputs.visual_level),
        s_overdue=ri.overdue_signal(hours_since_maintenance, machine.maintenance_interval_hours),
        s_history=ri.history_signal(inputs.problem_incidents),
    )
    index, used = ri.combine(signals, profile.risk_weights)
    explanation += [{"kind": "signal", **entry} for entry in ri.signal_entries(signals, profile.risk_weights)]
    priority = priority_kzt(
        index,
        machine.criticality,
        machine.downtime_cost_per_hour_kzt,
        machine.avg_repair_hours,
        machine.batch_value_kzt,
        workshop.profile,
    )
    return ScoreResult(
        machine.id,
        as_of,
        p_model,
        index,
        priority,
        explanation,
        anomaly.is_anomaly,
        used,
        model_version,
        machine.is_demo,
    )


async def save_score(session: AsyncSession, result: ScoreResult) -> RiskScore:
    columns = {name: value for name, value in vars(result).items() if name != "is_demo"}
    score = RiskScore(**columns)
    session.add(score)
    await session.commit()
    await session.refresh(score)
    return score


async def recompute_and_save(session: AsyncSession, machine_id: int) -> RiskScore:
    return await save_score(session, await compute_score(session, machine_id))


async def recompute_risk(machine_id: int) -> None:
    """Background task (after a new reading / incident): receives only the ID, opens its own session."""
    started = utcnow()
    try:
        async with SessionLocal() as session:
            score = await recompute_and_save(session, machine_id)
    except Exception:
        logger.exception("risk recompute failed", extra={"machine_id": machine_id})
        raise
    logger.info(
        "risk recomputed",
        extra={
            "machine_id": machine_id,
            "risk_index": score.risk_index,
            "duration_ms": int((utcnow() - started).total_seconds() * 1000),
        },
    )


async def what_if(session: AsyncSession, machine_id: int, overrides: WhatIfOverrides):
    """(current, scenario) scores, both computed now and neither saved."""
    current = await compute_score(session, machine_id)
    scenario = await compute_score(session, machine_id, as_of=current.computed_at, overrides=overrides)
    return current, scenario


async def ranking(session: AsyncSession, workshop_id: int) -> list[tuple[RiskScore, Machine]]:
    """Latest stored score of every machine in the workshop, highest priority_kzt first."""
    latest = (
        select(
            RiskScore.id.label("score_id"),
            func.row_number()
            .over(
                partition_by=RiskScore.machine_id,
                order_by=(RiskScore.computed_at.desc(), RiskScore.id.desc()),
            )
            .label("position"),
        )
        .join(Machine, Machine.id == RiskScore.machine_id)
        .where(Machine.workshop_id == workshop_id)
        .subquery()
    )
    stmt = (
        select(RiskScore, Machine)
        .join(latest, (RiskScore.id == latest.c.score_id) & (latest.c.position == 1))
        .join(Machine, Machine.id == RiskScore.machine_id)
        .order_by(RiskScore.priority_kzt.desc(), RiskScore.risk_index.desc())
    )
    return [(score, machine) for score, machine in (await session.execute(stmt)).all()]


async def history(
    session: AsyncSession, machine_id: int, date_from, date_to, limit: int, offset: int = 0
) -> list[RiskScore]:
    await machines_service.get_or_404(session, machine_id)
    stmt = select(RiskScore).where(RiskScore.machine_id == machine_id)
    if date_from is not None:
        stmt = stmt.where(RiskScore.computed_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(RiskScore.computed_at <= date_to)
    stmt = stmt.order_by(RiskScore.computed_at.asc(), RiskScore.id.asc()).limit(limit).offset(offset)
    return list((await session.scalars(stmt)).all())


DAILY_MAX_ROWS = 20_000  # a year of hourly scores; the daily view never needs more


async def daily_history(
    session: AsyncSession, machine_id: int, date_from, date_to, utc_offset_minutes: int = 0
) -> list[RiskScore]:
    """The last score of every calendar day (in the caller's time zone), oldest first.

    The scheduler adds a score every hour, so a month holds ~720 rows; charts need one per day.
    """
    rows = await history(session, machine_id, date_from, date_to, DAILY_MAX_ROWS)
    shift = timedelta(minutes=utc_offset_minutes)
    last_of_day: dict = {}
    for score in rows:  # oldest first: a later score of the same day replaces the earlier one
        last_of_day[(score.computed_at + shift).date()] = score
    return list(last_of_day.values())
