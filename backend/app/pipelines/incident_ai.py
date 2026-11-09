"""Incident analysis by the AI service, with the builtin pipeline as automatic fallback (D76, D78, D81).

run(ctx, caption, builtin) is called after the caption's safety check:
  builtin provider        -> builtin() (the existing pipeline), ai_source "builtin"
  sidecar                 -> one POST /v1/incident/analyze (IncidentAnalyzeRequest): shared media
                             paths, ids ws-/m-, machine economics, the stored audio baseline artifact
    AI card               -> the backend's safety layer runs on everything the AI wrote (the answer
                             has no transcript), AI safety_triggers only add a stop header; then the
                             backend finalizes: safety floor, the AI's measured audio level / tool wear
                             as floor, pages only from the AI's citations (R5, R6), plain-text render
    input error           -> explanatory card (retake photo / record again), no fallback
    no AI audio baseline  -> builtin (it has its own baseline statistics), degraded "ai_baseline_missing"
    baseline mismatch     -> rebuild the artifact once, retry; otherwise fallback
    anything else         -> builtin(), degraded tag on the incident
"""

import logging

from sqlalchemy import select

from app.db.base import IncidentInput
from app.models.machine import Machine
from app.modules.ai_gateway import adapters, messages, provider
from app.modules.ai_gateway.client import FiboAIError
from app.modules.ai_gateway.ids import m_id, ws_id
from app.modules.ai_gateway.paths import shared_path
from app.modules.ai_gateway.requests import machine_context
from app.modules.assistant import card as card_module
from app.modules.assistant import safety
from app.modules.assistant.rag import ManualChunk, RagResult
from app.modules.machine.audio_baselines import audio_baselines
from app.modules.vision import compare
from app.pipelines import ai_sync
from app.pipelines import incident_steps as steps

log = logging.getLogger("fibo.pipeline")


async def build_request(ctx: steps.Context, caption: str | None, baseline_ref: dict | None) -> dict:
    machine, incident = ctx.machine, ctx.incident
    names = await ctx.session.scalars(select(Machine.name).where(Machine.workshop_id == machine.workshop_id))
    request = {
        "workshop_id": ws_id(machine.workshop_id),
        "machine_id": m_id(machine.id),
        "profile": ctx.profile.id.value,
        "lang": ctx.language,
        "text": caption,
        "context": machine_context(machine),
        "catalog_machines": list(names),
        "baseline_ref": baseline_ref,
    }
    if incident.input_type == IncidentInput.TEXT:  # typed message: the text is the whole input
        request["text"] = "\n".join(filter(None, [incident.transcript, caption]))
        return request
    media = shared_path(incident.attachments[0].file_path)
    if incident.input_type == IncidentInput.PHOTO:
        request["tool_photo_path"] = media
        reference = await compare.reference_photo(ctx.session, machine.id)
        request["tool_reference_photo_path"] = shared_path(reference.file_path) if reference else None
    elif incident.input_type == IncidentInput.AUDIO:
        request["audio_file_path"] = media
    else:
        request["voice_file_path"] = media
    return request


async def apply_ai_card(ctx: steps.Context, ai: adapters.AIIncident) -> None:
    await steps.check_safety(ctx, ai.texts())  # the AI's words may echo the operator's dangerous ones
    if ai.safety_triggers:
        triggered = safety.SafetyResult(
            True, "stop", [f"AI: {t}" for t in ai.safety_triggers], safety.STOP_HEADER
        )
        await steps.flag_safety(ctx, triggered)
    ctx.incident.audio_zscore = None  # the AI's z-score uses another embedder and scale: shown, not stored
    raw = card_module.IncidentCard(
        verdict=ai.verdict,
        level=ai.level,
        confidence=ai.confidence,
        causes=ai.causes[:5],
        actions=ai.actions[:6],
        manual_pages=sorted(ai.claimed_pages),
        clarifying_question=ai.clarifying_question,
    )
    allowed = RagResult(bool(ai.citation_pages), [ManualChunk(p, "", 1.0) for p in sorted(ai.citation_pages)])
    final = card_module.finalize(raw, ctx.state["safety"], allowed, min_level=ai.measured_level)
    notes = [f"🔊 Отклонение от эталона: {ai.audio_z:.1f}σ"] if ai.audio_z is not None else []
    notes += [f"• {finding}" for finding in ai.findings[:4]]
    steps.save_card(ctx, final, notes)
    ctx.incident.degraded = sorted({*ctx.incident.degraded, *ai.degraded})


async def _audio_baseline_ref(ctx: steps.Context) -> dict | None:
    artifact = ai_sync.latest_artifact(await audio_baselines(ctx.session, ctx.machine.id))
    if artifact is None and ctx.incident.input_type == IncidentInput.AUDIO:
        artifact = await ai_sync.sync_audio_baseline(ctx.session, ctx.machine.id)
    return artifact


async def _builtin_with(ctx: steps.Context, builtin, tag: str) -> None:
    ctx.incident.ai_source = "builtin"
    ctx.incident.degraded = sorted({*ctx.incident.degraded, tag})
    log.info("incident %s: builtin path (%s)", ctx.incident.id, tag)
    await builtin()


async def run(ctx: steps.Context, caption: str | None, builtin) -> None:
    ctx.incident.ai_source, ctx.incident.degraded = "builtin", []
    if not provider.sidecar_enabled():
        await builtin()
        return
    baseline_ref = await _audio_baseline_ref(ctx)
    if baseline_ref is None and ctx.incident.input_type == IncidentInput.AUDIO:
        await _builtin_with(ctx, builtin, "ai_baseline_missing")  # builtin has its own baseline statistics
        return
    request = await build_request(ctx, caption, baseline_ref)

    async def rebuild_and_retry(client):
        artifact = await ai_sync.sync_audio_baseline(ctx.session, ctx.machine.id)
        if artifact is None:
            raise FiboAIError(409, "BASELINE_VERSION_MISMATCH", "baseline rebuild failed", False, {})
        return await client.analyze_incident(**{**request, "baseline_ref": artifact})

    ctx.state["stage"] = "ai_analyze"
    outcome = await provider.analyze_incident(request, builtin, on_recoverable=rebuild_and_retry)
    ctx.incident.ai_source, ctx.incident.degraded = outcome.source, list(outcome.degraded)
    if outcome.source == "builtin":
        return
    if outcome.input_error is not None:
        if outcome.input_error.code == "BASELINE_MISSING":
            await _builtin_with(ctx, builtin, "ai_baseline_missing")
            return
        text = messages.input_error_text(outcome.input_error, ctx.language)
        steps.simple_card(ctx, text, text)
        return
    ctx.state["stage"] = "ai_card"
    await apply_ai_card(ctx, outcome.value)
