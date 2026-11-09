"""Periodic risk recompute, so charts and the heat map fill in without manual "Recompute".

Risk changes with time alone (hours since maintenance grow), but it was only recomputed after a
reading, an incident or a button press, so a new workshop saw one point and an empty chart for days.
Every settings.risk_recompute_minutes the loop recomputes each machine whose latest score is older
than that interval (a machine scored a minute ago by an incident is skipped). One failing machine is
logged and does not stop the others. 0 minutes = off (tests).
"""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import func, select

from app.core.config import settings
from app.db.base import utcnow
from app.db.session import SessionLocal
from app.models.machine import Machine
from app.models.risk_score import RiskScore
from app.modules.machine import service as risk_service

logger = logging.getLogger("fibo.scheduler")
FIRST_RUN_DELAY_S = 30


async def due_machine_ids(interval: timedelta) -> list[int]:
    """Machines with no score, or whose latest score is older than `interval`."""
    latest = (
        select(RiskScore.machine_id, func.max(RiskScore.computed_at).label("at"))
        .group_by(RiskScore.machine_id)
        .subquery()
    )
    stmt = select(Machine.id, latest.c.at).outerjoin(latest, latest.c.machine_id == Machine.id)
    cutoff = utcnow() - interval
    async with SessionLocal() as session:
        rows = (await session.execute(stmt)).all()
    due = []
    for machine_id, at in rows:
        if at is not None and at.tzinfo is None:  # SQLite subquery max() loses the UTC type
            at = at.replace(tzinfo=cutoff.tzinfo)
        if at is None or at <= cutoff:
            due.append(machine_id)
    return due


async def recompute_due(interval: timedelta) -> int:
    """One pass; returns how many machines were recomputed."""
    done = 0
    for machine_id in await due_machine_ids(interval):
        try:
            await risk_service.recompute_risk(machine_id)
            done += 1
        except Exception:  # recompute_risk logged the traceback; keep going with the next machine
            logger.warning("scheduled recompute skipped a machine", extra={"machine_id": machine_id})
    return done


async def run_forever() -> None:
    minutes = settings.risk_recompute_minutes
    if minutes <= 0:
        return
    interval = timedelta(minutes=minutes)
    await asyncio.sleep(FIRST_RUN_DELAY_S)
    while True:
        try:
            done = await recompute_due(interval * 0.9)  # 0.9: a pass that ran a bit late still counts
            logger.info("scheduled risk recompute", extra={"machines": done})
        except Exception:  # database briefly unavailable etc.: logged, next pass in one interval
            logger.exception("scheduled risk recompute failed")
        await asyncio.sleep(interval.total_seconds())
