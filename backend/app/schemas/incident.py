"""Response schemas for incidents and their attachments."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.db.base import IncidentInput, IncidentLevel, IncidentStatus
from app.schemas.common import Money


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    file_path: str
    created_at: datetime

    @computed_field
    @property
    def url(self) -> str:
        """Where the dashboard downloads the file (GET /media/{path})."""
        return f"/api/v1/media/{self.file_path}"


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    machine_id: int
    user_id: int | None
    input_type: IncidentInput
    status: IncidentStatus
    level: IncidentLevel | None = Field(description="None until the pipeline has processed it")
    confidence: float | None
    transcript: str | None
    verdict: str | None
    causes: list
    manual_pages: list
    card_text: str | None
    safety_triggered: bool
    audio_zscore: float | None
    error_message: str | None
    downtime_hours: float | None
    loss_kzt: Money | None
    created_at: datetime
    resolved_at: datetime | None
    is_demo: bool
    ai_source: str | None = Field(None, description='"ai" = AI service, "builtin" = backend modules')
    degraded: list[str] = Field(
        default_factory=list, description="what was missing, e.g. ai_sidecar_unavailable"
    )


class IncidentDetail(IncidentRead):
    attachments: list[AttachmentRead]
