"""Daily production activity from stored readings and incidents, with no synthetic fill."""

from datetime import UTC, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_dashboard_key
from app.db.base import utcnow
from app.models.incident import Incident
from app.models.machine import Machine
from app.models.reading import Reading
from app.services.workshops import get_or_404

router = APIRouter(prefix="/reports", tags=["Fibo Reports"], dependencies=[Depends(require_dashboard_key)])


@router.get("/activity")
async def activity(
    workshop_id: int,
    days: int = Query(90, ge=7, le=366),
    utc_offset_minutes: int = Query(300, ge=-720, le=840),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await get_or_404(session, workshop_id)
    offset = timedelta(minutes=utc_offset_minutes)
    today = (utcnow() + offset).date()
    start_day = today - timedelta(days=days - 1)
    start = datetime.combine(start_day, time.min, tzinfo=UTC) - offset
    end = start + timedelta(days=days)
    buckets = {
        (start_day + timedelta(days=i)).isoformat(): {"readings": 0, "incidents": 0, "resolved": 0}
        for i in range(days)
    }
    for model, timestamp, key in [
        (Reading, Reading.recorded_at, "readings"),
        (Incident, Incident.created_at, "incidents"),
        (Incident, Incident.resolved_at, "resolved"),
    ]:
        dates = await session.scalars(
            select(timestamp)
            .join(Machine, model.machine_id == Machine.id)
            .where(Machine.workshop_id == workshop_id, timestamp >= start, timestamp < end)
        )
        for stamp in dates:
            date = (stamp + offset).date().isoformat()
            if date in buckets:
                buckets[date][key] += 1
    return {
        "workshop_id": workshop_id,
        "from": start_day.isoformat(),
        "to": today.isoformat(),
        "days": [{"date": date, **counts} for date, counts in buckets.items()],
    }
