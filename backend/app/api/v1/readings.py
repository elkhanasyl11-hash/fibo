"""Fibo Machine: machine readings (web form, bot, confirmed panel photo).

Saving a reading schedules a risk recomputation in the background (the response does not wait).
POST /readings/panel-photo reads a controller display with Fibo Vision and only RETURNS the values:
a person confirms them, then they are saved with POST /readings (source=panel).
"""

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_profiles, get_session, require_dashboard_key
from app.core.errors import DomainValidationError
from app.models.reading import Reading
from app.models.workshop import Workshop
from app.modules.ai_gateway import messages
from app.modules.ai_gateway import provider as ai_provider
from app.modules.ai_gateway.errors import AIRequestRejected
from app.modules.ai_gateway.ids import m_id, ws_id
from app.modules.ai_gateway.paths import shared_path
from app.modules.assistant.llm import get_llm_client
from app.modules.machine import service as risk_service
from app.modules.vision import panel_ocr
from app.modules.vision.quality import check_quality
from app.schemas.common import UTCDatetime
from app.schemas.reading import PanelPhotoResult, ReadingCreate, ReadingRead
from app.services import machines as machines_service
from app.services import readings as readings_service
from app.storage import files

router = APIRouter(tags=["Fibo Machine"], dependencies=[Depends(require_dashboard_key)])
# Same auth; a separate router only so panel-photo reading is listed under "Fibo Vision".
vision_router = APIRouter(tags=["Fibo Vision"], dependencies=[Depends(require_dashboard_key)])


@router.post(
    "/readings", response_model=ReadingRead, status_code=status.HTTP_201_CREATED, summary="Add reading"
)
async def create_reading(
    payload: ReadingCreate,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    profiles: dict = Depends(get_profiles),
) -> Reading:
    """422 with every bad field listed if a value is outside the workshop profile's ranges."""
    reading = await readings_service.create_reading(session, payload, profiles)
    background.add_task(risk_service.recompute_risk, reading.machine_id)  # ID only, never the session
    return reading


@router.get("/machines/{machine_id}/readings", response_model=list[ReadingRead], summary="Reading history")
async def list_readings(
    machine_id: int,
    date_from: UTCDatetime | None = Query(None, alias="from", description="Inclusive, with timezone"),
    date_to: UTCDatetime | None = Query(None, alias="to", description="Inclusive, with timezone"),
    page: Pagination = Depends(),
    session: AsyncSession = Depends(get_session),
) -> list[Reading]:
    """Newest first."""
    return await readings_service.list_history(
        session, machine_id, date_from, date_to, page.limit, page.offset
    )


async def _readout(machine, stored: str, photo, profile) -> panel_ocr.PanelReadout:
    """AI service first (FIBO_AI_PROVIDER=sidecar), the backend's own panel OCR as fallback (D78).
    The backend validates the values either way, so the response shape never depends on the provider."""

    async def builtin() -> panel_ocr.PanelReadout:
        return await panel_ocr.read_panel(get_llm_client(), photo, profile, machine.type)

    request = {
        "file_path": shared_path(stored),
        "machine_id": m_id(machine.id),
        "workshop_id": ws_id(machine.workshop_id),
    }
    try:
        outcome = await ai_provider.read_panel(request, builtin)
    except AIRequestRejected:  # the AI refused the request itself: the backend's OCR answers instead
        return await builtin()
    if outcome.input_error is not None:
        error = outcome.input_error
        raise DomainValidationError(messages.input_error_text(error, "ru"), details={"reasons": [error.code]})
    return outcome.value


@vision_router.post(
    "/readings/panel-photo", response_model=PanelPhotoResult, summary="Read a display photo (not saved)"
)
async def read_panel_photo(
    machine_id: int = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    profiles: dict = Depends(get_profiles),
) -> PanelPhotoResult:
    """422 if the photo is blurry/dark. Returns suggested values; NOTHING is written to readings."""
    machine = await machines_service.get_or_404(session, machine_id)
    profile = profiles[(await session.get(Workshop, machine.workshop_id)).profile]
    stored = await files.save_upload(file, kind="photo")
    photo = files.resolve_media_path(stored)
    quality = await asyncio.to_thread(check_quality, photo)
    if not quality.ok:
        raise DomainValidationError(
            f"Photo is not usable: {quality.text_ru}", details={"reasons": quality.reasons}
        )
    readout = await _readout(machine, stored, photo, profile)
    accepted, rejected = panel_ocr.validate(readout, profile)
    extra = [name for name, place in panel_ocr.allowed_fields(profile).items() if place == "extra"]
    return PanelPhotoResult(
        machine_id=machine.id,
        photo_path=stored,
        sharpness=quality.sharpness,
        brightness=quality.brightness,
        values=[v.model_dump() for v in accepted],
        rejected=[r.model_dump() for r in rejected],
        extra_fields=extra,
    )
