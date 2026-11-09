"""Building blocks shared by the branches of the incident pipeline (incident_pipeline.py).

Context       everything a stage needs, loaded once per run
log_stage     one JSON log line per finished stage, with its duration
check_safety  run the safety layer and SAVE a trigger at once, before any LLM call
flag_safety   the same for an already computed result (e.g. the AI service flagged danger)
save_card     copy a finalized card onto the incident
simple_card   a card without AI (missing baseline/reference, unusable photo); a safety header stays on top
record_failure  mark the incident FAILED in a FRESH session (the pipeline's session may be broken)
"""

import logging
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import IncidentLevel, IncidentStatus
from app.db.session import SessionLocal
from app.models.incident import Incident
from app.models.machine import Machine
from app.modules.assistant import card as card_module
from app.modules.assistant import safety
from app.modules.assistant.llm import LLMClient
from app.profiles.loader import ProfileConfig

logger = logging.getLogger("fibo.pipeline")

BASELINE_MISSING_TEXT = (
    "🎙 Запись звука получена, но для этого станка ещё нет эталонной записи.\n"
    "Запишите 3 эталонных звука исправного станка (⚙️ Мои станки → 🎚 Эталонный звук), "
    "тогда Fibo сможет сравнивать звук."
)
# Answers that are not incidents (nothing was diagnosed): notice_card, the incident is closed at once.
NOTICES = {
    "empty_recording": {
        "ru": (
            "Пустая запись",
            "🔇 Запись пустая: не слышно ни голоса, ни станка.\n"
            "Проверьте, что у Telegram есть доступ к микрофону (на компьютере — в настройках системы), "
            "и запишите ещё раз. Можно написать проблему текстом.",
        ),
        "kk": (
            "Бос жазба",
            "🔇 Жазба бос: дауыс та, станок та естілмейді.\n"
            "Telegram-ның микрофонға рұқсаты бар екенін тексеріп (компьютерде — жүйе баптауларында), "
            "қайта жазыңыз. Мәселені мәтінмен де жазуға болады.",
        ),
    },
    "no_speech": {
        "ru": (
            "Речь не распознана",
            "🎙 Не удалось разобрать слова в записи.\n"
            "Опишите проблему ещё раз, ближе к телефону, или напишите текстом.\n"
            "Если вы хотели проверить звук станка — нажмите «🔊 Записать звук станка».",
        ),
        "kk": (
            "Сөз танылмады",
            "🎙 Жазбадағы сөздерді түсіну мүмкін болмады.\n"
            "Мәселені телефонға жақынырақ қайта айтыңыз немесе мәтінмен жазыңыз.\n"
            "Станок дыбысын тексергіңіз келсе — «🔊 Станок дыбысын жазу» батырмасын басыңыз.",
        ),
    },
}
REFERENCE_MISSING_TEXT = (
    "📷 Фото получено, но для этого станка ещё нет эталонного фото.\n"
    "Мастер может добавить его: ⚙️ Мои станки → 📸 Эталонное фото (исправный инструмент/деталь)."
)


@dataclass
class Context:
    """Everything a stage needs, loaded once."""

    session: AsyncSession
    incident: Incident
    machine: Machine
    profile: ProfileConfig
    language: str
    client: LLMClient
    state: dict  # current stage name + safety result, read by the failure handler


def log_stage(incident_id: int, stage: str, started: float, **extra) -> None:
    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "pipeline stage done",
        extra={"incident_id": incident_id, "stage": stage, "duration_ms": duration_ms, **extra},
    )


async def check_safety(ctx: Context, texts: list[str | None]) -> None:
    """Run the safety layer and persist a trigger immediately, before any LLM call."""
    await flag_safety(ctx, safety.check_text(texts, ctx.profile.safety_keywords_extra))


async def flag_safety(ctx: Context, result: safety.SafetyResult) -> None:
    """Merge a safety result (backend keywords or the AI service's flag) and persist a trigger at once.
    Merging only ever adds: a triggered result is never switched back off."""
    found = safety.merge(ctx.state["safety"], result)
    ctx.state["safety"] = found
    if found.triggered:
        ctx.incident.safety_triggered = True
        ctx.incident.level = IncidentLevel.CRITICAL
        ctx.incident.card_text = card_module.safety_only_text(ctx.machine.name, found)
        await ctx.session.commit()


def save_card(ctx: Context, final: card_module.FinalCard, notes: list[str] | None = None) -> None:
    incident = ctx.incident
    incident.verdict = final.card.verdict
    incident.level = IncidentLevel(final.card.level)
    incident.confidence = final.card.confidence
    incident.causes = final.card.causes
    incident.manual_pages = final.card.manual_pages
    incident.card_text = card_module.render_text(ctx.machine.name, final, notes)


def notice_card(ctx: Context, key: str) -> None:
    """A reply that diagnoses nothing (empty recording, no words heard): no level, and the pipeline
    closes the incident at once so it does not count as open. A safety header still wins."""
    verdict, text = NOTICES[key].get(ctx.language, NOTICES[key]["ru"])
    simple_card(ctx, verdict, text)
    if not ctx.state["safety"].triggered:
        ctx.incident.level = None
        ctx.state["notice"] = True


def simple_card(ctx: Context, verdict: str, text: str) -> None:
    """Card without AI. If the safety layer triggered, its header stays on top and the level CRITICAL."""
    found = ctx.state["safety"]
    ctx.incident.verdict = verdict
    ctx.incident.level = IncidentLevel.CRITICAL if found.triggered else IncidentLevel.NORMAL
    ctx.incident.confidence, ctx.incident.causes, ctx.incident.manual_pages = None, [], []
    ctx.incident.card_text = (f"{found.header}\n\n" if found.triggered else "") + text


async def record_failure(incident_id: int, state: dict, exc: Exception, was_safety: bool) -> None:
    """Mark the incident FAILED, keeping any safety result. Uses its own session because the error may
    have broken the pipeline's one; if even this fails, it is logged (the startup sweep catches it)."""
    try:
        async with SessionLocal() as session:
            incident = await session.get(Incident, incident_id)
            if incident is None:
                logger.warning("failed incident no longer exists", extra={"incident_id": incident_id})
                return
            incident.status = IncidentStatus.FAILED
            incident.error_message = f"{state['stage']}: {type(exc).__name__}: {str(exc)[:200]}"
            if state["safety"].triggered or was_safety or incident.safety_triggered:
                incident.safety_triggered = True
                incident.level = IncidentLevel.CRITICAL
            await session.commit()
    except Exception:  # logged with traceback; the row is fixed by the startup sweep (pipelines/recovery.py)
        logger.exception("could not record incident failure", extra={"incident_id": incident_id})
