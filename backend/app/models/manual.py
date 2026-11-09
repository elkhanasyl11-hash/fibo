"""Manuals table: PDF manuals/passports uploaded for a machine, indexed for RAG in the background.

index_status tracks the background indexing. error_message holds a failure reason or a warning
(e.g. "pages 3-7 look scanned, no text extracted").
"""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IndexStatus, TimestampMixin, str_enum

if TYPE_CHECKING:
    from app.models.machine import Machine


class Manual(TimestampMixin, Base):
    __tablename__ = "manuals"

    id: Mapped[int] = mapped_column(primary_key=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(String(500))  # relative to media_dir
    original_filename: Mapped[str] = mapped_column(String(255))  # shown in UI only, never used in paths
    index_status: Mapped[IndexStatus] = mapped_column(
        str_enum(IndexStatus), default=IndexStatus.PENDING, index=True
    )
    page_count: Mapped[int | None]
    error_message: Mapped[str | None] = mapped_column(Text)

    machine: Mapped["Machine"] = relationship(back_populates="manuals")
