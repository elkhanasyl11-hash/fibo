"""Baselines table: reference recordings/photos of a machine in its normal, healthy state.

Audio baselines store per-feature mean/std in `stats`, used to compute z-scores of new recordings.
Photo baselines are the reference image a new tool/part photo is compared against.
"""

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaselineKind, TimestampMixin, str_enum

if TYPE_CHECKING:
    from app.models.machine import Machine


class Baseline(TimestampMixin, Base):
    __tablename__ = "baselines"
    __table_args__ = (Index("ix_baselines_machine_id_kind", "machine_id", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id", ondelete="CASCADE"), index=True)
    kind: Mapped[BaselineKind] = mapped_column(str_enum(BaselineKind))
    file_path: Mapped[str] = mapped_column(String(500))  # relative to media_dir
    embedding: Mapped[list | None] = mapped_column(JSON)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)

    machine: Mapped["Machine"] = relationship(back_populates="baselines")
