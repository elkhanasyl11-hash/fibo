"""Fibo Assistant: machine manuals (PDF passports) for retrieval with page numbers.

POST /machines/{id}/manuals  upload a PDF -> 202; indexing runs in the background
GET  /machines/{id}/manuals  list
GET  /manuals/{id}           indexing status (poll until ready / failed)
"""

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_session, require_dashboard_key
from app.core.errors import NotFoundError
from app.db.base import IndexStatus
from app.models.manual import Manual
from app.pipelines import manual_pipeline
from app.schemas.manual import ManualRead
from app.services import machines as machines_service
from app.storage import files

router = APIRouter(tags=["Fibo Assistant"], dependencies=[Depends(require_dashboard_key)])


@router.post(
    "/machines/{machine_id}/manuals",
    response_model=ManualRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a PDF manual",
)
async def upload_manual(
    machine_id: int,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> Manual:
    await machines_service.get_or_404(session, machine_id)
    stored = await files.save_upload(file, kind="manual")
    manual = Manual(
        machine_id=machine_id,
        file_path=stored,
        original_filename=(file.filename or "manual.pdf")[:255],
        index_status=IndexStatus.PENDING,
    )
    session.add(manual)
    await session.commit()
    await session.refresh(manual)
    background.add_task(manual_pipeline.index_manual, manual.id)  # id only
    return manual


@router.get("/machines/{machine_id}/manuals", response_model=list[ManualRead], summary="Manuals of a machine")
async def list_manuals(
    machine_id: int, page: Pagination = Depends(), session: AsyncSession = Depends(get_session)
) -> list[Manual]:
    await machines_service.get_or_404(session, machine_id)
    stmt = (
        select(Manual)
        .where(Manual.machine_id == machine_id)
        .order_by(Manual.created_at, Manual.id)
        .limit(page.limit)
        .offset(page.offset)
    )
    return list((await session.scalars(stmt)).all())


@router.get("/manuals/{manual_id}", response_model=ManualRead, summary="Manual indexing status")
async def get_manual(manual_id: int, session: AsyncSession = Depends(get_session)) -> Manual:
    manual = await session.get(Manual, manual_id)
    if manual is None:
        raise NotFoundError(f"Manual {manual_id} not found", details={"manual_id": manual_id})
    return manual
