"""Incidents table: one report about a machine (voice message, machine sound or photo).

Lifecycle (status): RECEIVED -> PROCESSING -> OPEN -> RESOLVED, or FAILED on a pipeline error.
The pipeline fills transcript, verdict, level, confidence, causes, manual_pages and card_text.
safety_triggered is set by the deterministic safety layer and can never be undone by the LLM.
ai_source = who analysed it ("ai" = the AI service, "builtin" = the backend's own modules, NULL =
before the AI gateway); degraded = tags for what was missing (e.g. ai_sidecar_unavailable, D76).
When resolved, downtime_hours = resolved_at - created_at and loss_kzt = downtime x hourly cost.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    IncidentInput,
    IncidentLevel,
    IncidentStatus,
    TimestampMixin,
    UTCDateTime,
    str_enum,
)

if TYPE_CHECKING:
    from app.models.attachment import Attachment
    from app.models.machine import Machine
    from app.models.user import User


class Incident(TimestampMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    input_type: Mapped[IncidentInput] = mapped_column(str_enum(IncidentInput))
    transcript: Mapped[str | None] = mapped_column(Text)
    verdict: Mapped[str | None] = mapped_column(Text)
    level: Mapped[IncidentLevel | None] = mapped_column(str_enum(IncidentLevel), index=True)
    confidence: Mapped[float | None]
    causes: Mapped[list] = mapped_column(JSON, default=list)
    manual_pages: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[IncidentStatus] = mapped_column(
        str_enum(IncidentStatus), default=IncidentStatus.RECEIVED, index=True
    )
    card_text: Mapped[str | None] = mapped_column(Text)
    safety_triggered: Mapped[bool] = mapped_column(default=False)
    audio_zscore: Mapped[float | None]
    error_message: Mapped[str | None] = mapped_column(Text)
    downtime_hours: Mapped[float | None]
    loss_kzt: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)
    is_demo: Mapped[bool] = mapped_column(default=False)
    ai_source: Mapped[str | None] = mapped_column(String(16))
    degraded: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")

    machine: Mapped["Machine"] = relationship(back_populates="incidents")
    user: Mapped["User | None"] = relationship()
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", passive_deletes=True
    )
