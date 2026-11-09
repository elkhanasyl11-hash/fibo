"""Fibo Assistant: transcript -> structured symptom description (SymptomExtraction).

The LLM normalises what the operator said into a short Russian description, the conditions, an
urgency estimate and, if the information is not enough, one clarifying question. The output is
validated by Pydantic (llm.chat_json). This step never decides safety: that is safety.py.
"""

import json
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.assistant.llm import LLMClient
from app.profiles.loader import ProfileConfig


class SymptomExtraction(BaseModel):
    machine_mentioned: str | None = None
    symptom: str = Field(max_length=300)  # short normalised description in Russian
    conditions: str | None = None  # e.g. "on high spindle speed", "under load"
    urgency: Literal["low", "medium", "high"]
    clarifying_question: str | None = None  # one question if information is insufficient


SYSTEM_PROMPT = (
    "Ты помощник механика небольшого цеха. Оператор описал проблему со станком голосом "
    "(русский или казахский). Извлеки суть: короткое описание симптома по-русски, условия, "
    "срочность (low/medium/high) и, если данных мало, один уточняющий вопрос. Не придумывай фактов."
)


async def extract_symptoms(
    client: LLMClient,
    transcript: str,
    *,
    machine_name: str,
    machine_type: str,
    profile: ProfileConfig,
    language: str,
) -> SymptomExtraction:
    payload = {
        "task": "extract_symptoms",
        "transcript": transcript,
        "machine": {"name": machine_name, "type": machine_type},
        "user_language": language,
    }
    messages = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n{profile.assistant_context_ru}"},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    return await client.chat_json(messages, SymptomExtraction)
