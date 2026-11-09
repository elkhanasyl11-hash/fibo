"""Response schemas for machine baselines (reference sound recordings and photos)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.db.base import BaselineKind


class BaselineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    machine_id: int
    kind: BaselineKind
    file_path: str
    created_at: datetime
    stats: dict = Field(exclude=True)

    @computed_field
    @property
    def url(self) -> str:
        return f"/api/v1/media/{self.file_path}"

    @computed_field
    @property
    def recordings_in_baseline(self) -> int | None:
        """Audio only: how many recordings the combined statistics of this row are based on."""
        return self.stats.get("n_recordings") if self.kind == BaselineKind.AUDIO else None


class AudioBaselineCreated(BaseModel):
    baseline: BaselineRead
    recordings: int = Field(description="Audio baselines of this machine, including this one")
    recommended: int
    ready: bool = Field(description="True once the recommended number of recordings is reached")
