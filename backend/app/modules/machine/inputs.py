"""Fibo Machine: gather everything the risk computation needs for one machine at a moment in time.

`as_of` makes the computation reproducible for any past moment: only readings and incidents that
existed at that time are used (the demo seed uses this to build a risk history for the chart).

Raw inputs collected here (turned into 0..1 signals by risk_index.py):
  readings          last 30 days before as_of, oldest -> newest, as plain ReadingValues copies
  audio_z           latest machine-sound z-score of the last 7 days
  visual_level      latest photo-check level of the last 7 days
  problem_incidents warning/critical incidents of the last 30 days + older ones unresolved at as_of
  hours_since_maintenance  wall-clock hours since machines.last_maintenance_at
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import IncidentInput, IncidentLevel
from app.models.incident import Incident
from app.models.machine import Machine
from app.models.reading import Reading
from app.modules.machine.feature_map import ReadingValues

READINGS_WINDOW = timedelta(days=30)
MAX_READINGS = 500
SENSOR_WINDOW = timedelta(days=7)
HISTORY_WINDOW = timedelta(days=30)
PROBLEM_LEVELS = (IncidentLevel.WARNING, IncidentLevel.CRITICAL)


@dataclass
class MachineInputs:
    readings: list[ReadingValues]
    audio_z: float | None
    visual_level: str | None
    problem_incidents: int
    hours_since_maintenance: float | None


async def load_readings(session: AsyncSession, machine_id: int, as_of: datetime) -> list[ReadingValues]:
    stmt = (
        select(Reading)
        .where(
            Reading.machine_id == machine_id,
            Reading.recorded_at <= as_of,
            Reading.recorded_at >= as_of - READINGS_WINDOW,
        )
        .order_by(Reading.recorded_at.desc(), Reading.id.desc())
        .limit(MAX_READINGS)
    )
    rows = list((await session.scalars(stmt)).all())
    rows.reverse()  # oldest -> newest
    return [
        ReadingValues(r.recorded_at, r.spindle_rpm, r.load_pct, r.temperature_c, r.operating_hours, r.extra)
        for r in rows
    ]


def _was_open_at(incident: Incident, as_of: datetime) -> bool:
    return incident.resolved_at is None or incident.resolved_at > as_of


def summarize_incidents(incidents: list[Incident], as_of: datetime) -> tuple[float | None, str | None, int]:
    """(audio_z, visual_level, problem_incidents) from a machine's incidents created before as_of."""
    recent = sorted(
        (i for i in incidents if as_of - SENSOR_WINDOW <= i.created_at <= as_of), key=lambda i: i.created_at
    )
    audio = [i.audio_zscore for i in recent if i.audio_zscore is not None]
    photos = [i.level.value for i in recent if i.input_type == IncidentInput.PHOTO and i.level is not None]
    problems = sum(
        1
        for i in incidents
        if i.created_at <= as_of
        and i.level in PROBLEM_LEVELS
        and (i.created_at >= as_of - HISTORY_WINDOW or _was_open_at(i, as_of))
    )
    return (audio[-1] if audio else None), (photos[-1] if photos else None), problems


async def load_inputs(session: AsyncSession, machine: Machine, as_of: datetime) -> MachineInputs:
    readings = await load_readings(session, machine.id, as_of)
    incidents = list(
        (
            await session.scalars(
                select(Incident).where(Incident.machine_id == machine.id, Incident.created_at <= as_of)
            )
        ).all()
    )
    audio_z, visual_level, problems = summarize_incidents(incidents, as_of)
    hours = None
    if machine.last_maintenance_at is not None:
        hours = max(0.0, (as_of - machine.last_maintenance_at).total_seconds() / 3600)
    return MachineInputs(readings, audio_z, visual_level, problems, hours)
