"""Fibo Vision: read the numbers on a CNC / controller display from a photo.

The multimodal LLM returns, for every value it can see, the field name, the number, its confidence
and the raw text it read. Then plain code decides what is acceptable:
  - only fields the workshop profile knows (core reading fields with a range + profile extra fields);
  - the number must be inside the profile's valid range;
  - anything else goes to `rejected` with the reason, so the person sees it.
The result is ONLY A SUGGESTION: nothing is written to the database here. The human checks the
values (bot: ✅ / ✏️, dashboard form) and saves them with POST /readings (source=panel).
"""

import json
from pathlib import Path

from pydantic import BaseModel, Field

from app.modules.assistant.llm import LLMClient
from app.profiles.loader import ProfileConfig
from app.services.readings import CORE_FIELDS

SYSTEM_PROMPT = (
    "На фото — дисплей станка с ЧПУ или контроллера. Прочитай видимые числовые параметры и сопоставь их с "
    "полями из списка. Для каждого: поле, число (или null, если не уверен), уверенность 0..1 и точный текст, "
    "который ты видишь. Не придумывай значения, которых нет на экране."
)


class PanelValue(BaseModel):
    field: str
    value: float | None
    confidence: float = Field(ge=0, le=1)
    raw_text: str | None = None


class PanelReadout(BaseModel):
    values: list[PanelValue]


class RejectedValue(PanelValue):
    reason: str


def allowed_fields(profile: ProfileConfig) -> dict[str, str]:
    """field name -> where it goes in POST /readings: "core" column or "extra"."""
    fields = {name: "core" for name in CORE_FIELDS if name in profile.reading_ranges}
    fields.update({extra.name: "extra" for extra in profile.extra_fields})
    return fields


def validate(readout: PanelReadout, profile: ProfileConfig) -> tuple[list[PanelValue], list[RejectedValue]]:
    allowed = allowed_fields(profile)
    accepted, rejected = [], []
    for item in readout.values:
        if item.field not in allowed:
            rejected.append(RejectedValue(**item.model_dump(), reason="field not used by this profile"))
        elif item.value is None:
            rejected.append(RejectedValue(**item.model_dump(), reason="not readable"))
        elif not profile.reading_ranges[item.field][0] <= item.value <= profile.reading_ranges[item.field][1]:
            low, high = profile.reading_ranges[item.field]
            rejected.append(
                RejectedValue(**item.model_dump(), reason=f"outside valid range {low:g}..{high:g}")
            )
        else:
            accepted.append(item)
    return accepted, rejected


async def read_panel(
    client: LLMClient, photo: Path, profile: ProfileConfig, machine_type: str
) -> PanelReadout:
    payload = {
        "task": "panel_ocr",
        "profile": profile.id.value,
        "machine_type": machine_type,
        "fields": sorted(allowed_fields(profile)),
    }
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    return await client.chat_json(messages, PanelReadout, images=[photo])
