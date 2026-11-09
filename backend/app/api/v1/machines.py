"""Fibo Machine: CRUD for machines + the machine summary page. Thin layer: logic in services."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_session, require_dashboard_key
from app.models.machine import Machine
from app.schemas.machine import MachineCreate, MachineRead, MachineSummary, MachineUpdate
from app.services import machines as machines_service

router = APIRouter(prefix="/machines", tags=["Fibo Machine"], dependencies=[Depends(require_dashboard_key)])


@router.post("", response_model=MachineRead, status_code=status.HTTP_201_CREATED, summary="Add machine")
async def create_machine(payload: MachineCreate, session: AsyncSession = Depends(get_session)) -> Machine:
    return await machines_service.create_machine(session, payload)


@router.get("", response_model=list[MachineRead], summary="List machines of a workshop")
async def list_machines(
    workshop_id: int, page: Pagination = Depends(), session: AsyncSession = Depends(get_session)
) -> list[Machine]:
    return await machines_service.list_for_workshop(session, workshop_id, page.limit, page.offset)


@router.get("/{machine_id}", response_model=MachineRead, summary="Get machine")
async def get_machine(machine_id: int, session: AsyncSession = Depends(get_session)) -> Machine:
    return await machines_service.get_or_404(session, machine_id)


@router.get("/{machine_id}/summary", response_model=MachineSummary, summary="Machine page")
async def get_machine_summary(
    machine_id: int, session: AsyncSession = Depends(get_session)
) -> MachineSummary:
    """Machine + latest risk score + open incidents + last 10 readings."""
    return await machines_service.build_summary(session, machine_id)


@router.patch("/{machine_id}", response_model=MachineRead, summary="Update machine")
async def update_machine(
    machine_id: int, payload: MachineUpdate, session: AsyncSession = Depends(get_session)
) -> Machine:
    machine = await machines_service.get_or_404(session, machine_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(machine, field, value)
    await session.commit()
    await session.refresh(machine)
    return machine


@router.delete("/{machine_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete machine")
async def delete_machine(machine_id: int, session: AsyncSession = Depends(get_session)) -> None:
    """Also deletes its readings, risk scores, baselines, manuals and incidents (ON DELETE CASCADE)."""
    machine = await machines_service.get_or_404(session, machine_id)
    await session.delete(machine)
    await session.commit()
