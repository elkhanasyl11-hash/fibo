"""Incidents: creation (from ingest), feed with filters, detail, resolve with downtime/loss.

Downtime and loss (compute_downtime):
    downtime_hours = (resolved_at - created_at) in hours
    loss_kzt       = downtime_hours x machine.downtime_cost_per_hour_kzt, rounded to 0.01 tenge
The loss is computed from exact seconds with Decimal, so no float rounding creeps into money.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, DomainValidationError, NotFoundError
from app.db.base import IncidentInput, IncidentLevel, IncidentStatus, utcnow
from app.models.attachment import Attachment
from app.models.incident import Incident
from app.models.machine import Machine
from app.models.user import User
from app.services import users as users_service

SECONDS_PER_HOUR = Decimal(3600)
CENT = Decimal("0.01")


@dataclass
class IncidentFilters:
    workshop_id: int | None = None
    machine_id: int | None = None
    status: IncidentStatus | None = None
    level: IncidentLevel | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


def compute_downtime(
    created_at: datetime, resolved_at: datetime, cost_per_hour: Decimal
) -> tuple[float, Decimal]:
    """Return (downtime_hours, loss_kzt) for an incident that lasted from created_at to resolved_at."""
    if resolved_at < created_at:
        raise DomainValidationError("resolved_at is before created_at")
    seconds = Decimal(str((resolved_at - created_at).total_seconds()))
    hours = seconds / SECONDS_PER_HOUR
    loss = (hours * Decimal(cost_per_hour)).quantize(CENT, rounding=ROUND_HALF_UP)
    return round(float(hours), 4), loss


async def get_or_404(session: AsyncSession, incident_id: int) -> Incident:
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise NotFoundError(f"Incident {incident_id} not found", details={"incident_id": incident_id})
    return incident


async def get_detail_or_404(session: AsyncSession, incident_id: int) -> Incident:
    """Incident with its attachments loaded (async sessions cannot lazy-load relationships)."""
    stmt = select(Incident).where(Incident.id == incident_id).options(selectinload(Incident.attachments))
    incident = await session.scalar(stmt)
    if incident is None:
        raise NotFoundError(f"Incident {incident_id} not found", details={"incident_id": incident_id})
    return incident


async def list_incidents(session: AsyncSession, filters: IncidentFilters, limit: int, offset: int):
    """Incident feed, newest first."""
    stmt = select(Incident)
    if filters.workshop_id is not None:
        stmt = stmt.join(Machine, Machine.id == Incident.machine_id).where(
            Machine.workshop_id == filters.workshop_id
        )
    if filters.machine_id is not None:
        stmt = stmt.where(Incident.machine_id == filters.machine_id)
    if filters.status is not None:
        stmt = stmt.where(Incident.status == filters.status)
    if filters.level is not None:
        stmt = stmt.where(Incident.level == filters.level)
    if filters.date_from is not None:
        stmt = stmt.where(Incident.created_at >= filters.date_from)
    if filters.date_to is not None:
        stmt = stmt.where(Incident.created_at <= filters.date_to)
    stmt = stmt.order_by(Incident.created_at.desc(), Incident.id.desc()).limit(limit).offset(offset)
    return list((await session.scalars(stmt)).all())


async def create_received(
    session: AsyncSession,
    *,
    machine: Machine,
    user: User | None,
    input_type: IncidentInput,
    attachment_path: str | None,
    transcript: str | None = None,
) -> Incident:
    """Create an incident in status RECEIVED (used by /ingest/*): the uploaded file attached, or for a
    typed message (TEXT) no file and the text as the transcript."""
    incident = Incident(
        machine_id=machine.id,
        user_id=user.id if user else None,
        input_type=input_type,
        status=IncidentStatus.RECEIVED,
        transcript=transcript,
    )
    if attachment_path is not None:
        incident.attachments.append(Attachment(kind=input_type.value, file_path=attachment_path))
    session.add(incident)
    await session.commit()
    await session.refresh(incident)
    return incident


async def resolve_incident(session: AsyncSession, incident_id: int, now: datetime | None = None) -> Incident:
    """Mark as RESOLVED and compute downtime + loss. `now` is injectable for tests."""
    incident = await get_or_404(session, incident_id)
    if incident.status == IncidentStatus.RESOLVED:
        raise ConflictError(
            f"Incident {incident_id} is already resolved", details={"incident_id": incident_id}
        )
    if incident.status in (IncidentStatus.RECEIVED, IncidentStatus.PROCESSING):
        # The pipeline would overwrite the status when it finishes and "un-resolve" the incident.
        raise ConflictError(
            f"Incident {incident_id} is still being analysed",
            details={"incident_id": incident_id, "status": incident.status.value},
        )
    machine = await session.get(Machine, incident.machine_id)
    resolved_at = now or utcnow()
    hours, loss = compute_downtime(incident.created_at, resolved_at, machine.downtime_cost_per_hour_kzt)
    incident.status = IncidentStatus.RESOLVED
    incident.resolved_at = resolved_at
    incident.downtime_hours = hours
    incident.loss_kzt = loss
    await session.commit()
    await session.refresh(incident)
    return incident


async def prepare_retry(session: AsyncSession, incident_id: int) -> Incident:
    """Only FAILED incidents can be re-processed; they go back to RECEIVED."""
    incident = await get_or_404(session, incident_id)
    if incident.status != IncidentStatus.FAILED:
        raise ConflictError(
            f"Incident {incident_id} is {incident.status.value}, only failed incidents can be retried",
            details={"incident_id": incident_id, "status": incident.status.value},
        )
    incident.status = IncidentStatus.RECEIVED
    await session.commit()
    return incident


async def escalation_targets(session: AsyncSession, incident_id: int) -> tuple[Incident, Machine, list[int]]:
    """The incident, its machine and the Telegram ids of the workshop's masters."""
    incident = await get_or_404(session, incident_id)
    machine = await session.get(Machine, incident.machine_id)
    masters = await users_service.list_masters(session, machine.workshop_id)
    return incident, machine, [m.telegram_id for m in masters if m.telegram_id is not None]
