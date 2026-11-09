"""Processing of one incident (voice, typed text, machine-sound recording or photo), run in the background.

process_incident(incident_id) opens its OWN database session (never the request's) and runs:
  1. status PROCESSING; caption safety check; FIBO_AI_PROVIDER=sidecar: the AI service first (incident_ai.py)
  2. typed text (TEXT) -> straight to the speech branch. Recordings: convert to 16 kHz WAV; digital
     silence -> "empty recording, check the microphone" (closed at once); VAD decides: speech ->
     speech branch, else audio branch (a voice message without words and no baseline -> "say it again")
     (input_type AUDIO = "record machine sound" -> always the audio branch)
  3. speech branch: transcribe -> SAFETY on the transcript (saved at once) -> symptom extraction
     -> manual retrieval (RAG) -> LLM card -> finalize (only real pages, safety forces CRITICAL)
     audio branch:  z-score vs. the machine's baseline + spectrogram -> LLM card -> finalize (the
     measured level is a floor); no baseline -> ask the operator to record one
     photo:         quality check (blurry/dark -> "retake", level NORMAL) -> compare with the reference
                    photo (multimodal LLM) -> card; no reference photo -> ask for one
  4. save verdict, level, causes, pages, card_text; status OPEN
  5. CRITICAL or safety: Telegram alert to the workshop's owner and masters (app/modules/notify.py)
  6. recompute the machine's risk score (the incident changes s_history / s_audio)
Any failure: status FAILED with a short error_message; a safety card that was already saved stays
(the operator must still see the stop instruction). Safe to re-run on a FAILED incident (retry):
every field is rewritten, and safety_triggered is never switched back off.
"""

import asyncio
import logging
import time
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import IncidentInput, IncidentStatus, utcnow
from app.db.session import SessionLocal
from app.models.incident import Incident
from app.models.machine import Machine
from app.models.user import User
from app.models.workshop import Workshop
from app.modules import notify
from app.modules.assistant import card as card_module
from app.modules.assistant import rag, safety, speech
from app.modules.assistant.extraction import extract_symptoms
from app.modules.assistant.llm import get_llm_client
from app.modules.machine import audio_baselines
from app.modules.machine import service as risk_service
from app.modules.vision import compare
from app.modules.vision.quality import check_quality
from app.pipelines import incident_ai
from app.pipelines import incident_steps as steps
from app.profiles.loader import get_profiles
from app.services import incidents as incidents_service
from app.storage.files import resolve_media_path

logger = logging.getLogger("fibo.pipeline")


async def _audio_branch(ctx: steps.Context, wav: Path) -> None:
    ctx.state["stage"] = "audio"
    started = time.perf_counter()
    result = await audio_baselines.analyze(ctx.session, ctx.machine.id, wav, ctx.incident.id)
    steps.log_stage(ctx.incident.id, "audio", started, audio_z=result.audio_z, level=result.level)
    found = ctx.state["safety"]
    if result.baseline_missing and ctx.incident.input_type == IncidentInput.VOICE:
        steps.notice_card(ctx, "no_speech")  # a voice message without words: no baseline to compare
        return
    if result.baseline_missing:
        steps.simple_card(ctx, "Нет эталонной записи звука", steps.BASELINE_MISSING_TEXT)
        return
    ctx.incident.audio_zscore = result.audio_z
    audio_info = {
        "audio_z": result.audio_z,
        "level": result.level,
        "description": result.description,
        "n_recordings": result.n_recordings,
    }
    ctx.state["stage"] = "rag"
    chunks = await rag.retrieve(
        ctx.session, ctx.machine.id, f"{result.description} {ctx.machine.type}", ctx.profile.id.value
    )
    ctx.state["stage"] = "card"
    raw = await card_module.generate_card(
        ctx.client,
        extraction=None,
        audio=audio_info,
        rag=chunks,
        machine_name=ctx.machine.name,
        profile=ctx.profile,
        language=ctx.language,
    )
    final = card_module.finalize(raw, found, chunks, min_level=result.level)
    notes = [f"🔊 Отклонение от эталона: {result.audio_z:.1f}σ ({result.description})"]
    if result.n_recordings < audio_baselines.RECOMMENDED_RECORDINGS:
        notes.append(
            f"Эталон: {result.n_recordings} из {audio_baselines.RECOMMENDED_RECORDINGS} записей — "
            "оценка менее надёжна"
        )
    steps.save_card(ctx, final, notes)


async def _photo_branch(ctx: steps.Context, caption: str | None) -> None:
    ctx.state["stage"] = "photo_quality"
    photo = resolve_media_path(ctx.incident.attachments[0].file_path)
    quality = await asyncio.to_thread(check_quality, photo)
    if not quality.ok:
        verdict = (
            f"Фото не подходит: {quality.text_ru}. Переснимите при хорошем свете, держа телефон неподвижно."
        )
        steps.simple_card(ctx, verdict, f"📷 {verdict}")
        return
    reference = await compare.reference_photo(ctx.session, ctx.machine.id)
    if reference is None:
        steps.simple_card(ctx, "Нет эталонного фото", steps.REFERENCE_MISSING_TEXT)
        return
    ctx.state["stage"] = "vision"
    started = time.perf_counter()
    vision = await compare.inspect(
        ctx.client,
        resolve_media_path(reference.file_path),
        photo,
        machine_name=ctx.machine.name,
        machine_type=ctx.machine.type,
        caption=caption,
    )
    steps.log_stage(ctx.incident.id, "vision", started, level=vision.level, defect=vision.defect_type)
    ctx.state["stage"] = "rag"
    chunks = await rag.retrieve(
        ctx.session, ctx.machine.id, f"{vision.explanation} {ctx.machine.type}", ctx.profile.id.value
    )
    ctx.state["stage"] = "card"
    raw = await card_module.generate_card(
        ctx.client,
        extraction=None,
        audio=None,
        rag=chunks,
        machine_name=ctx.machine.name,
        profile=ctx.profile,
        language=ctx.language,
        vision=vision.model_dump(),
    )
    final = card_module.finalize(raw, ctx.state["safety"], chunks, min_level=vision.level)
    steps.save_card(ctx, final, [f"📷 {vision.explanation}"])


async def _speech_branch(ctx: steps.Context) -> None:
    await steps.check_safety(ctx, [ctx.incident.transcript])
    ctx.state["stage"] = "extraction"
    started = time.perf_counter()
    extraction = await extract_symptoms(
        ctx.client,
        ctx.incident.transcript,
        machine_name=ctx.machine.name,
        machine_type=ctx.machine.type,
        profile=ctx.profile,
        language=ctx.language,
    )
    steps.log_stage(ctx.incident.id, "extraction", started, urgency=extraction.urgency)
    ctx.state["stage"] = "rag"
    query = f"{extraction.symptom} {ctx.machine.type} {ctx.machine.model or ''}".strip()
    chunks = await rag.retrieve(ctx.session, ctx.machine.id, query, ctx.profile.id.value)
    ctx.state["stage"] = "card"
    started = time.perf_counter()
    raw = await card_module.generate_card(
        ctx.client,
        extraction=extraction,
        audio=None,
        rag=chunks,
        machine_name=ctx.machine.name,
        profile=ctx.profile,
        language=ctx.language,
    )
    final = card_module.finalize(raw, ctx.state["safety"], chunks)
    steps.log_stage(
        ctx.incident.id, "card", started, level=final.card.level, dropped_pages=final.dropped_pages
    )
    steps.save_card(ctx, final)


async def _run(ctx: steps.Context, caption: str | None) -> None:
    ctx.state["stage"] = "safety_caption"
    await steps.check_safety(ctx, [caption])
    await incident_ai.run(ctx, caption, lambda: _run_builtin(ctx, caption))


async def _run_builtin(ctx: steps.Context, caption: str | None) -> None:
    """The backend's own modules (also the fallback when the AI service fails, D76)."""
    if ctx.incident.input_type == IncidentInput.PHOTO:
        await _photo_branch(ctx, caption)
        return
    if ctx.incident.input_type == IncidentInput.TEXT:  # typed: the text is already the transcript
        ctx.state["stage"] = "safety_transcript"
        await _speech_branch(ctx)
        return

    ctx.state["stage"] = "convert"
    started = time.perf_counter()
    wav = await speech.prepare_wav(resolve_media_path(ctx.incident.attachments[0].file_path))
    try:
        if await asyncio.to_thread(speech.is_silent, wav):
            steps.log_stage(ctx.incident.id, "convert_vad", started, silent=True)
            steps.notice_card(ctx, "empty_recording")
            return
        speaks = ctx.incident.input_type == IncidentInput.VOICE and await asyncio.to_thread(
            speech.has_speech, wav
        )
        steps.log_stage(ctx.incident.id, "convert_vad", started, speech=speaks)
        if not speaks:
            await _audio_branch(ctx, wav)
            return
        ctx.state["stage"] = "transcribe"
        started = time.perf_counter()
        ctx.incident.transcript = await speech.transcribe(ctx.client, wav, ctx.language)
        await ctx.session.commit()
        steps.log_stage(ctx.incident.id, "transcribe", started)
    finally:
        wav.unlink(missing_ok=True)
    ctx.state["stage"] = "safety_transcript"
    await _speech_branch(ctx)


async def _load_context(session: AsyncSession, incident: Incident, state: dict) -> steps.Context:
    machine = await session.get(Machine, incident.machine_id)
    workshop = await session.get(Workshop, machine.workshop_id)
    user = await session.get(User, incident.user_id) if incident.user_id else None
    return steps.Context(
        session,
        incident,
        machine,
        get_profiles()[workshop.profile],
        user.language if user else "ru",
        get_llm_client(),
        state,
    )


async def process_incident(incident_id: int, caption: str | None = None) -> None:
    """Background task: receives only the id (and the optional caption text)."""
    state: dict = {"stage": "load", "safety": safety.SafetyResult()}
    was_safety = False
    async with SessionLocal() as session:
        try:
            incident = await session.get(Incident, incident_id)
            if incident is None:  # machine/incident deleted before the task ran: nothing to do
                logger.warning("incident to process no longer exists", extra={"incident_id": incident_id})
                return
            incident = await incidents_service.get_detail_or_404(session, incident_id)
            machine_id, was_safety = incident.machine_id, incident.safety_triggered
            incident.status, incident.error_message = IncidentStatus.PROCESSING, None
            await session.commit()
            await _run(await _load_context(session, incident, state), caption)
            incident.status = IncidentStatus.OPEN
            if state.get("notice"):  # nothing diagnosed (empty recording, no words): not an open incident
                incident.status, incident.resolved_at = IncidentStatus.RESOLVED, utcnow()
                incident.downtime_hours, incident.loss_kzt = 0.0, Decimal("0")
            incident.safety_triggered = incident.safety_triggered or was_safety
            await session.commit()
            logger.info("incident processed", extra={"incident_id": incident_id, "level": incident.level})
        except Exception as exc:  # recorded on the incident (in a fresh session), never swallowed
            logger.exception(
                "incident pipeline failed", extra={"incident_id": incident_id, "stage": state["stage"]}
            )
            try:  # release the SQLite write lock before recording the failure in a fresh session
                await session.rollback()
            except Exception:  # logged; record_failure below still runs
                logger.exception("rollback after pipeline failure failed", extra={"incident_id": incident_id})
            await steps.record_failure(incident_id, state, exc, was_safety)
            return
    await notify.notify_incident(incident_id)  # owner/masters about CRITICAL / "stop the machine"
    try:
        await risk_service.recompute_risk(machine_id)
    except Exception:  # the incident itself is done; recompute_risk already logged the traceback
        logger.warning("risk recompute after incident failed", extra={"incident_id": incident_id})
