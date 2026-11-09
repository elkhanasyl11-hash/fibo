"""Fibo Machine: workshops (tenants). Creating one generates its bot invite code."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_session, require_dashboard_key
from app.models.workshop import Workshop
from app.schemas.workshop import WorkshopCreate, WorkshopRead
from app.services import workshops as workshops_service

router = APIRouter(prefix="/workshops", tags=["Fibo Machine"], dependencies=[Depends(require_dashboard_key)])


@router.post("", response_model=WorkshopRead, status_code=status.HTTP_201_CREATED, summary="Create workshop")
async def create_workshop(payload: WorkshopCreate, session: AsyncSession = Depends(get_session)) -> Workshop:
    return await workshops_service.create_workshop(session, payload)


@router.get("", response_model=list[WorkshopRead], summary="List workshops")
async def list_workshops(
    page: Pagination = Depends(), session: AsyncSession = Depends(get_session)
) -> list[Workshop]:
    stmt = select(Workshop).order_by(Workshop.id).limit(page.limit).offset(page.offset)
    return list((await session.scalars(stmt)).all())


@router.get("/{workshop_id}", response_model=WorkshopRead, summary="Get workshop")
async def get_workshop(workshop_id: int, session: AsyncSession = Depends(get_session)) -> Workshop:
    return await workshops_service.get_or_404(session, workshop_id)
