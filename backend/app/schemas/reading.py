"""Request/response schemas for readings."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.base import ReadingSource
from app.schemas.common import UTCDatetime


class ReadingCreate(BaseModel):
    """One snapshot of machine parameters. Values are checked against the workshop profile's ranges."""

    machine_id: int
    recorded_at: UTCDatetime | None = Field(default=None, description="Defaults to now")
    source: ReadingSource = ReadingSource.FORM
    spindle_rpm: float | None = None
    load_pct: float | None = None
    temperature_c: float | None = None
    operating_hours: float | None = None
    extra: dict[str, float] | None = Field(default=None, examples=[{"humidity_pct": 78}])
    created_by_user_id: int | None = None


class ReadingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    machine_id: int
    recorded_at: datetime
    source: ReadingSource
    spindle_rpm: float | None
    load_pct: float | None
    temperature_c: float | None
    operating_hours: float | None
    extra: dict | None
    created_by_user_id: int | None
    is_demo: bool


class PanelValueRead(BaseModel):
    field: str
    value: float | None
    confidence: float
    raw_text: str | None


class PanelRejectedRead(PanelValueRead):
    reason: str


class PanelPhotoResult(BaseModel):
    """Values read from a display photo. A SUGGESTION ONLY: nothing has been saved."""

    machine_id: int
    photo_path: str
    sharpness: float
    brightness: float
    values: list[PanelValueRead] = Field(description="Readable and within the profile's valid ranges")
    rejected: list[PanelRejectedRead] = Field(description="Unknown field, unreadable or out of range")
    extra_fields: list[str] = Field(description="Fields that go into `extra` of POST /readings")
    saved: bool = Field(default=False, description="Always false: confirm with POST /readings, source=panel")
