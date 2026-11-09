"""Fibo Assistant: the incident card the operator receives in Telegram.

generate_card  asks the LLM for an IncidentCard (JSON) from the symptom extraction, the audio
               result and the manual chunks.
finalize       applies the rules the LLM is not trusted with:
                 - pages: keep only pages that were really retrieved (the model must not invent pages);
                 - safety: if the safety layer triggered, level = CRITICAL, whatever the model said.
render_text    turns the result into the message text (plain text; the bot escapes it for HTML).
Buttons are fixed: "Resolved", "Call mechanic", and "Manual page" when pages are cited
(button_spec); the bot builds them from the incident id.
"""

import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.assistant.extraction import SymptomExtraction
from app.modules.assistant.llm import LLMClient
from app.modules.assistant.rag import RagResult
from app.modules.assistant.safety import SafetyResult
from app.profiles.loader import ProfileConfig

LEVEL_EMOJI = {"normal": "🟢", "warning": "🟡", "critical": "🔴"}
LEVEL_RU = {"normal": "норма", "warning": "внимание", "critical": "критично"}
GENERAL_SAFETY_ADVICE = (
    "В паспорте станка ответ не найден. Работайте по общим правилам безопасности и позовите механика."
)

SYSTEM_PROMPT = (
    "Ты помощник механика. По описанию симптома, данным анализа звука или фото и фрагментам паспорта станка "
    "составь карточку инцидента: вывод, уровень (normal/warning/critical), уверенность 0..1, до 5 причин, "
    "до 6 коротких действий для оператора. Ссылайся ТОЛЬКО на номера страниц из переданных фрагментов; "
    "если фрагментов нет — manual_pages пустой. Не указывай износ в процентах."
)


class IncidentCard(BaseModel):
    verdict: str = Field(max_length=300)
    level: Literal["normal", "warning", "critical"]
    confidence: float = Field(ge=0, le=1)
    causes: list[str] = Field(default_factory=list, max_length=5)
    actions: list[str] = Field(default_factory=list, max_length=6)
    manual_pages: list[int] = Field(default_factory=list)
    clarifying_question: str | None = None


@dataclass
class FinalCard:
    card: IncidentCard
    safety: SafetyResult
    manual_found: bool
    dropped_pages: list[int]


async def generate_card(
    client: LLMClient,
    *,
    extraction: SymptomExtraction | None,
    audio: dict | None,
    rag: RagResult,
    machine_name: str,
    profile: ProfileConfig,
    language: str,
    vision: dict | None = None,
) -> IncidentCard:
    payload = {
        "task": "incident_card",
        "machine": machine_name,
        "extraction": extraction.model_dump() if extraction else None,
        "audio": audio,
        "vision": vision,
        "manual_chunks": [{"page": c.page, "text": c.text} for c in rag.chunks],
        "knowledge_notes": rag.notes,  # profile notes: useful context, but never cited as pages
        "reply_language": language,
    }
    messages = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n{profile.assistant_context_ru}"},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    return await client.chat_json(messages, IncidentCard)


LEVEL_ORDER = ["normal", "warning", "critical"]


def finalize(
    card: IncidentCard, safety: SafetyResult, rag: RagResult, min_level: str | None = None
) -> FinalCard:
    """min_level: a measured level (e.g. the audio z-score) the model may raise but never lower."""
    allowed = rag.pages
    kept = sorted({p for p in card.manual_pages if p in allowed})
    dropped = sorted({p for p in card.manual_pages if p not in allowed})
    level = max(card.level, min_level or "normal", key=LEVEL_ORDER.index)
    if safety.triggered:
        level = "critical"
    final = card.model_copy(update={"manual_pages": kept, "level": level})
    return FinalCard(final, safety, rag.found, dropped)


def safety_only_text(machine_name: str, safety: SafetyResult) -> str:
    """Shown right away (and kept if later stages fail)."""
    return f"{safety.header}\n\nСтанок: {machine_name}\nПричина: {', '.join(safety.matched)}"


def render_text(machine_name: str, final: FinalCard, notes: list[str] | None = None) -> str:
    """notes: extra facts shown under the verdict (e.g. the audio measurement)."""
    card = final.card
    lines = []
    if final.safety.triggered:
        lines += [final.safety.header, ""]
    lines.append(f"{LEVEL_EMOJI[card.level]} {machine_name}: {LEVEL_RU[card.level]}")
    lines.append(card.verdict)
    lines += notes or []
    if card.causes:
        lines += ["", "Возможные причины:", *(f"• {c}" for c in card.causes)]
    if card.actions:
        lines += ["", "Что сделать:", *(f"{i}. {a}" for i, a in enumerate(card.actions, 1))]
    if card.manual_pages:
        lines += ["", "Паспорт: стр. " + ", ".join(str(p) for p in card.manual_pages)]
    elif not final.manual_found:
        lines += ["", GENERAL_SAFETY_ADVICE]
    if card.clarifying_question:
        lines += ["", f"❓ {card.clarifying_question}"]
    lines += ["", f"Уверенность: {round(card.confidence * 100)}%"]
    return "\n".join(lines)


def button_spec(incident_id: int, has_pages: bool) -> list[dict]:
    """Inline buttons for the bot. callback_data stays far below Telegram's 64-byte limit."""
    buttons = [
        {"text": "✅ Решено", "callback_data": f"res:{incident_id}"},
        {"text": "🧰 Вызвать механика", "callback_data": f"esc:{incident_id}"},
    ]
    if has_pages:
        buttons.append({"text": "📖 Страница паспорта", "callback_data": f"pg:{incident_id}"})
    return buttons
