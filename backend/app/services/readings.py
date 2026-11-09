"""Readings: validation against the workshop's industry profile, saving, history.

Validation rules (validate_reading_values):
  - at least one value must be given;
  - a value is accepted only if the profile defines a range for it (a bakery has no spindle_rpm);
  - every value must lie inside the profile's [min, max] range (this also rejects NaN/inf);
  - `extra` keys must be extra fields of the profile (e.g. humidity_pct for bakery).
All problems are collected and returned together, so the form can highlight every bad field.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainValidationError
from app.db.base import Profile, utcnow
from app.models.reading import Reading
from app.models.user import User
from app.models.workshop import Workshop
from app.profiles.loader import ProfileConfig
from app.schemas.reading import ReadingCreate
from app.services import machines as machines_service

CORE_FIELDS = ("spindle_rpm", "load_pct", "temperature_c", "operating_hours")
# Phone clocks drift; a reading "from the future" by more than this is a mistake.
FUTURE_TOLERANCE = timedelta(minutes=5)


def _check_range(profile: ProfileConfig, field: str, key: str, value: float) -> dict | None:
    value_range = profile.reading_ranges.get(key)
    if value_range is None:
        return {"field": field, "problem": f"not used by profile '{profile.id.value}'"}
    low, high = value_range
    if not low <= value <= high:
        return {"field": field, "problem": f"must be between {low} and {high}", "value": value}
    return None


def validate_reading_values(
    profile: ProfileConfig, values: dict[str, float | None], extra: dict | None
) -> list:
    """Return a list of problems; an empty list means the reading is valid."""
    problems: list[dict] = []
    given = {name: value for name, value in values.items() if value is not None}
    extra = extra or {}
    if not given and not extra:
        return [{"field": "*", "problem": "at least one value is required"}]

    for name, value in given.items():
        problem = _check_range(profile, name, name, value)
        if problem:
            problems.append(problem)

    allowed_extra = {field.name for field in profile.extra_fields}
    for name, value in extra.items():
        if name not in allowed_extra:
            problems.append(
                {"field": f"extra.{name}", "problem": f"not used by profile '{profile.id.value}'"}
            )
            continue
        problem = _check_range(profile, f"extra.{name}", name, value)
        if problem:
            problems.append(problem)
    return problems


async def create_reading(
    session: AsyncSession, payload: ReadingCreate, profiles: dict[Profile, ProfileConfig]
) -> Reading:
    machine = await machines_service.get_or_404(session, payload.machine_id)
    workshop = await session.get(Workshop, machine.workshop_id)
    profile = profiles[workshop.profile]

    values = {name: getattr(payload, name) for name in CORE_FIELDS}
    problems = validate_reading_values(profile, values, payload.extra)
    now = utcnow()
    recorded_at = payload.recorded_at or now
    if recorded_at > now + FUTURE_TOLERANCE:
        problems.append({"field": "recorded_at", "problem": "is in the future"})
    if payload.created_by_user_id is not None:
        author = await session.get(User, payload.created_by_user_id)
        if author is None or author.workshop_id != machine.workshop_id:
            problems.append({"field": "created_by_user_id", "problem": "unknown user in this workshop"})
    if problems:
        raise DomainValidationError("Reading values are not valid", details={"fields": problems})

    reading = Reading(
        **values,
        machine_id=machine.id,
        recorded_at=recorded_at,
        source=payload.source,
        extra=payload.extra or None,
        created_by_user_id=payload.created_by_user_id,
    )
    session.add(reading)
    await session.commit()
    await session.refresh(reading)
    return reading


async def list_history(
    session: AsyncSession,
    machine_id: int,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
    offset: int,
) -> list[Reading]:
    """Readings of one machine, newest first, optionally within [date_from, date_to]."""
    await machines_service.get_or_404(session, machine_id)
    stmt = select(Reading).where(Reading.machine_id == machine_id)
    if date_from is not None:
        stmt = stmt.where(Reading.recorded_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(Reading.recorded_at <= date_to)
    stmt = stmt.order_by(Reading.recorded_at.desc(), Reading.id.desc()).limit(limit).offset(offset)
    return list((await session.scalars(stmt)).all())
