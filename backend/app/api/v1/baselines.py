"""Fibo Machine: baselines — how this machine looks and sounds when it is healthy.

  POST /machines/{id}/baselines/audio  one reference recording (>= 3 recommended); the combined
                                       statistics are recomputed at once
  POST /machines/{id}/baselines/photo  a reference photo of the tool / part (used by Fibo Vision)
  GET  /machines/{id}/baselines        list
The bot (masters) and the dashboard can both upload.
"""

from fastapi import APIRouter, Depends, File, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_session, require_dashboard_key
from app.core.errors import UnsupportedMediaError
from app.db.base import BaselineKind
from app.models.baseline import Baseline
from app.modules.assistant.speech import prepare_wav
from app.modules.machine import audio_baselines
from app.pipelines import ai_sync
from app.schemas.baseline import AudioBaselineCreated, BaselineRead
from app.services import machines as machines_service
from app.storage import files

router = APIRouter(
    prefix="/machines/{machine_id}/baselines",
    tags=["Fibo Machine"],
    dependencies=[Depends(require_dashboard_key)],
)
# Same prefix and auth; a separate router only so the reference photo is listed under "Fibo Vision".
vision_router = APIRouter(
    prefix="/machines/{machine_id}/baselines",
    tags=["Fibo Vision"],
    dependencies=[Depends(require_dashboard_key)],
)


@router.post(
    "/audio",
    response_model=AudioBaselineCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Add a reference sound recording",
)
async def add_audio_baseline(
    machine_id: int, file: UploadFile = File(...), session: AsyncSession = Depends(get_session)
) -> AudioBaselineCreated:
    """Record 10–15 s of the machine running normally. 422 if shorter than 2 s."""
    await machines_service.get_or_404(session, machine_id)
    stored = await files.save_upload(file, kind="audio")
    wav = await prepare_wav(files.resolve_media_path(stored))
    try:
        baseline = await audio_baselines.add_audio_baseline(session, machine_id, stored, wav)
    finally:
        wav.unlink(missing_ok=True)
    await ai_sync.sync_audio_baseline(session, machine_id)  # sidecar only; never fails the upload
    count = baseline.stats["n_recordings"]
    return AudioBaselineCreated(
        baseline=BaselineRead.model_validate(baseline),
        recordings=count,
        recommended=audio_baselines.RECOMMENDED_RECORDINGS,
        ready=count >= audio_baselines.RECOMMENDED_RECORDINGS,
    )


@vision_router.post(
    "/photo",
    response_model=BaselineRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a reference photo",
)
async def add_photo_baseline(
    machine_id: int, file: UploadFile = File(...), session: AsyncSession = Depends(get_session)
) -> Baseline:
    await machines_service.get_or_404(session, machine_id)
    stored = await files.save_upload(file, kind="photo")
    try:
        with Image.open(files.resolve_media_path(stored)) as image:
            stats = {"width": image.width, "height": image.height, "format": image.format}
    except UnidentifiedImageError as exc:
        raise UnsupportedMediaError("Photo cannot be read") from exc
    baseline = Baseline(machine_id=machine_id, kind=BaselineKind.PHOTO, file_path=stored, stats=stats)
    session.add(baseline)
    await session.commit()
    await session.refresh(baseline)
    return baseline


@router.get("", response_model=list[BaselineRead], summary="List baselines")
async def list_baselines(
    machine_id: int, page: Pagination = Depends(), session: AsyncSession = Depends(get_session)
) -> list[Baseline]:
    await machines_service.get_or_404(session, machine_id)
    stmt = (
        select(Baseline)
        .where(Baseline.machine_id == machine_id)
        .order_by(Baseline.created_at, Baseline.id)
        .limit(page.limit)
        .offset(page.offset)
    )
    return list((await session.scalars(stmt)).all())
