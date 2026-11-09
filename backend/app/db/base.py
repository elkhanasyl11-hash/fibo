"""Shared database building blocks: enums, the UTC clock, the declarative Base and column helpers.

Design choices (also in docs/decisions.md):
  - Enums are Python StrEnum, stored in the DB as their *value* strings ("operator", not "OPERATOR")
    in a plain VARCHAR column (native_enum=False). Moving to PostgreSQL needs no enum migrations.
  - All timestamps are timezone-aware UTC. SQLite has no timezone type and returns naive datetimes,
    so UTCDateTime re-attaches UTC when reading. PostgreSQL behaves the same through this type.
  - A naming convention for constraints gives every index/constraint a predictable name, which
    Alembic needs to alter or drop them later.
"""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class Role(StrEnum):
    OPERATOR = "operator"
    MASTER = "master"
    OWNER = "owner"


class Profile(StrEnum):
    METALWORKING = "metalworking"
    BAKERY = "bakery"
    CONFECTIONERY = "confectionery"
    SEWING = "sewing"
    DAIRY = "dairy"


class ReadingSource(StrEnum):
    PANEL = "panel"  # photo of a CNC/controller display, values confirmed by a human
    FORM = "form"  # web form
    BOT = "bot"  # typed/voiced in the bot


class BaselineKind(StrEnum):
    AUDIO = "audio"
    PHOTO = "photo"


class IncidentInput(StrEnum):
    VOICE = "voice"
    AUDIO = "audio"
    PHOTO = "photo"
    TEXT = "text"  # typed in the bot (also answers to a card's clarifying question); no attachment


class IncidentLevel(StrEnum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


class IncidentStatus(StrEnum):
    RECEIVED = "received"  # file saved, processing queued
    PROCESSING = "processing"
    OPEN = "open"  # processed, card ready, problem not fixed
    RESOLVED = "resolved"  # operator/master pressed "Resolved"
    FAILED = "failed"  # pipeline error; error_message is set


class IndexStatus(StrEnum):
    PENDING = "pending"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


def utcnow() -> datetime:
    """The single source of "now" for the whole backend: timezone-aware UTC."""
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """DateTime(timezone=True) that always gives back timezone-aware UTC datetimes.

    Writing: aware datetimes are converted to UTC; naive ones are rejected (they are ambiguous).
    Reading: SQLite returns naive values, so UTC is attached; PostgreSQL values are converted to UTC.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime given; use timezone-aware UTC (app.db.base.utcnow)")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def str_enum(enum_class: type[StrEnum]) -> Enum:
    """Column type for a StrEnum: stores the enum *values* in a VARCHAR(20)."""
    return Enum(
        enum_class,
        native_enum=False,
        length=20,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
