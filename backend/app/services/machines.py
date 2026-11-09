"""Machines: lookups scoped to a workshop and the machine summary page."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.base import IncidentStatus
from app.models.incident import Incident
from app.models.machine import Machine
from app.models.reading import Reading
from app.models.risk_score import RiskScore
from app.schemas.incident import IncidentRead
from app.schemas.machine import MachineCreate, MachineRead, MachineSummary
from app.schemas.reading import ReadingRead
from app.schemas.risk_score import RiskScoreRead
from app.services import workshops as workshops_service

ACTIVE_STATUSES = (IncidentStatus.RECEIVED, IncidentStatus.PROCESSING, IncidentStatus.OPEN)
RECENT_READINGS = 10


async def get_or_404(session: AsyncSession, machine_id: int) -> Machine:
    machine = await session.get(Machine, machine_id)
    if machine is None:
        raise NotFoundError(f"Machine {machine_id} not found", details={"machine_id": machine_id})
    return machine


async def get_in_workshop_or_404(session: AsyncSession, machine_id: int, workshop_id: int) -> Machine:
    """Like get_or_404, but a machine of another workshop also counts as "not found"."""
    machine = await get_or_404(session, machine_id)
    if machine.workshop_id != workshop_id:
        raise NotFoundError(f"Machine {machine_id} not found", details={"machine_id": machine_id})
    return machine


async def create_machine(session: AsyncSession, payload: MachineCreate) -> Machine:
    await workshops_service.get_or_404(session, payload.workshop_id)
    machine = Machine(**payload.model_dump())
    session.add(machine)
    await session.commit()
    await session.refresh(machine)
    return machine


async def list_for_workshop(session: AsyncSession, workshop_id: int, limit: int = 200, offset: int = 0):
    stmt = (
        select(Machine)
        .where(Machine.workshop_id == workshop_id)
        .order_by(Machine.id)
        .limit(limit)
        .offset(offset)
    )
    return list((await session.scalars(stmt)).all())


async def build_summary(session: AsyncSession, machine_id: int) -> MachineSummary:
    machine = await get_or_404(session, machine_id)
    latest_risk = await session.scalar(
        select(RiskScore)
        .where(RiskScore.machine_id == machine_id)
        .order_by(RiskScore.computed_at.desc(), RiskScore.id.desc())
        .limit(1)
    )
    open_incidents = await session.scalars(
        select(Incident)
        .where(Incident.machine_id == machine_id, Incident.status.in_(ACTIVE_STATUSES))
        .order_by(Incident.created_at.desc())
    )
    readings = await session.scalars(
        select(Reading)
        .where(Reading.machine_id == machine_id)
        .order_by(Reading.recorded_at.desc())
        .limit(RECENT_READINGS)
    )
    return MachineSummary(
        machine=MachineRead.model_validate(machine),
        latest_risk=RiskScoreRead.model_validate(latest_risk) if latest_risk else None,
        open_incidents=[IncidentRead.model_validate(i) for i in open_incidents],
        recent_readings=[ReadingRead.model_validate(r) for r in readings],
    )
