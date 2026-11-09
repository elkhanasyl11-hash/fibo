"""Request/response schemas for workshops."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.base import Profile


class WorkshopCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150, examples=["Цех «Металл-Сервис»"])
    city: str = Field(default="Шымкент", min_length=1, max_length=100)
    profile: Profile


class WorkshopRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    city: str
    profile: Profile
    invite_code: str = Field(description="Code operators type in the Telegram bot to join")
    is_demo: bool = Field(description="True = synthetic demo data, not a real workshop")
    survey: dict | None = Field(default=None, description="Onboarding answers from the web sign-up")
    created_at: datetime
