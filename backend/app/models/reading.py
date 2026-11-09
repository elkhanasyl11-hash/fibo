"""Readings table: one snapshot of a machine's parameters at a moment in time.

Values come from a web form, the bot, or a panel photo that a human confirmed (source).
Every numeric value is optional because small workshops rarely know all of them.
Profile-specific values (e.g. humidity_pct in a bakery) go into `extra`.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, ReadingSource, UTCDateTime, str_enum, utcnow

if TYPE_CHECKING:
    from app.models.machine import Machine


class Reading(Base):
    __tablename__ = "readings"
    # History queries are "readings of machine X ordered by time" -> composite index.
    __table_args__ = (Index("ix_readings_machine_id_recorded_at", "machine_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id", ondelete="CASCADE"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    source: Mapped[ReadingSource] = mapped_column(str_enum(ReadingSource))
    spindle_rpm: Mapped[float | None]
    load_pct: Mapped[float | None]
    temperature_c: Mapped[float | None]
    operating_hours: Mapped[float | None]
    extra: Mapped[dict | None] = mapped_column(JSON)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    is_demo: Mapped[bool] = mapped_column(default=False)

    machine: Mapped["Machine"] = relationship(back_populates="readings")
