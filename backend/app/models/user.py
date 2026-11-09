"""Users table: operators, masters (mechanics) and owners of a workshop.

Bot users have a telegram_id; web-only users may not. Web owners sign in with email + password
(password_hash is scrypt, see app/core/passwords.py); bot-only users have neither.
language ("ru" / "kk") selects the language of bot messages and assistant answers.
"""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Role, TimestampMixin, str_enum

if TYPE_CHECKING:
    from app.models.workshop import Workshop


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("language IN ('ru', 'kk')", name="language"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    full_name: Mapped[str] = mapped_column(String(150))
    role: Mapped[Role] = mapped_column(str_enum(Role), index=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id", ondelete="CASCADE"), index=True)
    language: Mapped[str] = mapped_column(String(2), default="ru")
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))

    workshop: Mapped["Workshop"] = relationship(back_populates="users")
