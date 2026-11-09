"""Fibo Assistant: bot -> backend entry point for recordings (bot token only).

  POST /ingest/voice  operator's voice message. mode=auto: VAD decides speech vs. machine sound;
                      mode=machine_sound ("🔊 Записать звук станка"): stored as input_type AUDIO.
  POST /ingest/audio  an audio file of the machine's sound (always input_type AUDIO).
  POST /ingest/photo  photo of a tool / part (Fibo Vision compares it with the reference photo).
  POST /ingest/text   a typed problem description (or an answer to a card's clarifying question):
                      no file, the text goes straight to the speech branch as the transcript.
All save the file, create the incident in status RECEIVED, schedule the pipeline in the
background and answer 202 at once. The bot then polls GET /incidents/{id}.
"""

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_bot_token
from app.core.errors import DomainValidationError
from app.db.base import IncidentInput
from app.pipelines import incident_pipeline
from app.schemas.ingest import IngestAccepted
from app.services import incidents as incidents_service
from app.services import machines as machines_service
from app.services import users as users_service
from app.storage import files

router = APIRouter(prefix="/ingest", tags=["Fibo Assistant"], dependencies=[Depends(require_bot_token)])
# Same prefix and auth; a separate router only so the photo endpoint is listed under "Fibo Vision".
vision_router = APIRouter(prefix="/ingest", tags=["Fibo Vision"], dependencies=[Depends(require_bot_token)])


async def _ingest(
    session: AsyncSession,
    background: BackgroundTasks,
    *,
    telegram_id: int,
    machine_id: int,
    upload: UploadFile,
    input_type: IncidentInput,
    caption: str | None,
) -> IngestAccepted:
    user = await users_service.get_by_telegram_id_or_404(session, telegram_id)
    machine = await machines_service.get_in_workshop_or_404(session, machine_id, user.workshop_id)
    stored = await files.save_upload(upload, kind=input_type.value)  # validates size/type, relative path
    incident = await incidents_service.create_received(
        session, machine=machine, user=user, input_type=input_type, attachment_path=stored
    )
    background.add_task(incident_pipeline.process_incident, incident.id, caption)  # id, never the session
    return IngestAccepted(incident_id=incident.id)


@router.post(
    "/voice", status_code=status.HTTP_202_ACCEPTED, response_model=IngestAccepted, summary="Voice message"
)
async def ingest_voice(
    background: BackgroundTasks,
    telegram_id: int = Form(...),
    machine_id: int = Form(...),
    mode: Literal["auto", "machine_sound"] = Form("auto"),
    caption: str | None = Form(None, max_length=1000),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> IngestAccepted:
    input_type = IncidentInput.AUDIO if mode == "machine_sound" else IncidentInput.VOICE
    return await _ingest(
        session,
        background,
        telegram_id=telegram_id,
        machine_id=machine_id,
        upload=file,
        input_type=input_type,
        caption=caption,
    )


@router.post(
    "/audio", status_code=status.HTTP_202_ACCEPTED, response_model=IngestAccepted, summary="Machine sound"
)
async def ingest_audio(
    background: BackgroundTasks,
    telegram_id: int = Form(...),
    machine_id: int = Form(...),
    caption: str | None = Form(None, max_length=1000),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> IngestAccepted:
    return await _ingest(
        session,
        background,
        telegram_id=telegram_id,
        machine_id=machine_id,
        upload=file,
        input_type=IncidentInput.AUDIO,
        caption=caption,
    )


@vision_router.post(
    "/photo", status_code=status.HTTP_202_ACCEPTED, response_model=IngestAccepted, summary="Tool/part photo"
)
async def ingest_photo(
    background: BackgroundTasks,
    telegram_id: int = Form(...),
    machine_id: int = Form(...),
    caption: str | None = Form(None, max_length=1000),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> IngestAccepted:
    return await _ingest(
        session,
        background,
        telegram_id=telegram_id,
        machine_id=machine_id,
        upload=file,
        input_type=IncidentInput.PHOTO,
        caption=caption,
    )


class IngestText(BaseModel):
    telegram_id: int = Field(gt=0)
    machine_id: int
    text: str = Field(min_length=1, max_length=2000)


@router.post(
    "/text", status_code=status.HTTP_202_ACCEPTED, response_model=IngestAccepted, summary="Typed message"
)
async def ingest_text(
    payload: IngestText, background: BackgroundTasks, session: AsyncSession = Depends(get_session)
) -> IngestAccepted:
    text = payload.text.strip()
    if not text:
        raise DomainValidationError("Empty message", details={"field": "text"})
    user = await users_service.get_by_telegram_id_or_404(session, payload.telegram_id)
    machine = await machines_service.get_in_workshop_or_404(session, payload.machine_id, user.workshop_id)
    incident = await incidents_service.create_received(
        session,
        machine=machine,
        user=user,
        input_type=IncidentInput.TEXT,
        attachment_path=None,
        transcript=text,
    )
    background.add_task(incident_pipeline.process_incident, incident.id, None)
    return IngestAccepted(incident_id=incident.id)
