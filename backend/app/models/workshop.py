"""Workshops table. One row per workshop (tenant). Everything else belongs to a workshop.

profile picks the industry configuration (app/profiles/<profile>.yaml).
invite_code is what an operator types in the Telegram bot to join this workshop.
survey holds the onboarding answers from the web sign-up (what the workshop makes, shifts, the
industry questions); free-form JSON, only shown back to the owner and used as AI context.
"""

from typing import TYPE_CHECKING

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Profile, TimestampMixin, str_enum

if TYPE_CHECKING:
    from app.models.machine import Machine
    from app.models.user import User


class Workshop(TimestampMixin, Base):
    __tablename__ = "workshops"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    city: Mapped[str] = mapped_column(String(100), default="Шымкент")
    profile: Mapped[Profile] = mapped_column(str_enum(Profile), index=True)
    invite_code: Mapped[str] = mapped_column(String(16), unique=True)
    is_demo: Mapped[bool] = mapped_column(default=False)
    survey: Mapped[dict | None] = mapped_column(JSON)

    # passive_deletes: the database deletes children via ON DELETE CASCADE; SQLAlchemy does not
    # need to load them first.
    users: Mapped[list["User"]] = relationship(
        back_populates="workshop", cascade="all, delete-orphan", passive_deletes=True
    )
    machines: Mapped[list["Machine"]] = relationship(
        back_populates="workshop", cascade="all, delete-orphan", passive_deletes=True
    )
