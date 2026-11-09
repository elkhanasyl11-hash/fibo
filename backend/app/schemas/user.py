"""Request/response schemas for users (web users and bot registration)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.base import Role
from app.schemas.common import reject_explicit_nulls
from app.schemas.machine import MachineRead
from app.schemas.workshop import WorkshopRead

Language = Literal["ru", "kk"]


class UserCreate(BaseModel):
    """Web user (dashboard). telegram_id is optional; bot users register via /bot/register."""

    full_name: str = Field(min_length=1, max_length=150)
    role: Role
    workshop_id: int
    telegram_id: int | None = Field(default=None, gt=0)
    language: Language = "ru"


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    role: Role | None = None
    language: Language | None = None

    @model_validator(mode="after")
    def no_null_for_required_columns(self) -> "UserUpdate":
        reject_explicit_nulls(self, {"full_name", "role", "language"})
        return self


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int | None
    full_name: str
    role: Role
    workshop_id: int
    language: str
    email: str | None = None
    created_at: datetime


class BotRegister(BaseModel):
    """Sent by the bot after /start. Owners are created from the dashboard, not via the bot."""

    telegram_id: int = Field(gt=0)
    full_name: str = Field(min_length=1, max_length=150)
    invite_code: str = Field(min_length=4, max_length=16, examples=["DEMO01"])
    role: Literal["operator", "master"]
    language: Language = "ru"


class BotUserRead(BaseModel):
    """Everything the bot needs about a user: who they are, their workshop, its machines."""

    user: UserRead
    workshop: WorkshopRead
    machines: list[MachineRead]
