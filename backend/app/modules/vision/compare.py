"""Fibo Vision: compare a photo of a tool / part with the machine's reference photo.

The multimodal LLM gets both images (reference first) and must answer in the VisualInspection
JSON schema below. Rules for the answer: a level (normal / warning / critical) and a confidence —
never a wear percentage (a phone photo cannot measure wear precisely, so we do not pretend).
The payload also carries a rough pixel difference (quality.pixel_difference) as context; the mock
uses it to answer deterministically.
"""

import asyncio
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import BaselineKind
from app.models.baseline import Baseline
from app.modules.assistant.llm import LLMClient
from app.modules.vision.quality import pixel_difference

SYSTEM_PROMPT = (
    "Ты инспектор инструмента в цеху. Первое изображение — эталон (исправный инструмент/деталь), второе — "
    "текущее фото. Найди видимые дефекты: скол, износ кромки, нарост, трещина, царапина, загрязнение. "
    "Ответь уровнем normal/warning/critical и уверенностью 0..1. НЕ указывай износ в процентах. "
    "Если фото не позволяет судить — уровень normal и низкая уверенность."
)


class VisualInspection(BaseModel):
    defect_found: bool
    defect_type: Literal[
        "chip", "edge_wear", "built_up_edge", "crack", "scratch", "contamination", "none", "other"
    ]
    zone: str | None = None
    level: Literal["normal", "warning", "critical"]
    confidence: float = Field(ge=0, le=1)
    explanation: str = Field(max_length=500)


async def inspect(
    client: LLMClient,
    reference: Path,
    photo: Path,
    *,
    machine_name: str,
    machine_type: str,
    caption: str | None,
) -> VisualInspection:
    payload = {
        "task": "visual_inspection",
        "machine": {"name": machine_name, "type": machine_type},
        "operator_caption": caption,
        "pixel_difference": await asyncio.to_thread(pixel_difference, reference, photo),  # OpenCV: CPU work
    }
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    return await client.chat_json(messages, VisualInspection, images=[reference, photo])


async def reference_photo(session: AsyncSession, machine_id: int) -> Baseline | None:
    """The newest reference photo of the machine, or None."""
    stmt = (
        select(Baseline)
        .where(Baseline.machine_id == machine_id, Baseline.kind == BaselineKind.PHOTO)
        .order_by(Baseline.created_at.desc(), Baseline.id.desc())
        .limit(1)
    )
    return await session.scalar(stmt)
