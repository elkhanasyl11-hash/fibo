"""Response schemas for machine manuals (PDF) and page excerpts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.db.base import IndexStatus


class ManualRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    machine_id: int
    original_filename: str
    index_status: IndexStatus = Field(description="pending -> indexing -> ready | failed")
    page_count: int | None
    error_message: str | None = Field(description="Failure reason, or a warning about scanned pages")
    created_at: datetime
    file_path: str = Field(exclude=True)

    @computed_field
    @property
    def url(self) -> str:
        """Where the dashboard opens the PDF (GET /media/{path}); add #page=N for a cited page."""
        return f"/api/v1/media/{self.file_path}"


class PageExcerpt(BaseModel):
    page: int
    text: str


class ManualExcerpts(BaseModel):
    incident_id: int
    excerpts: list[PageExcerpt] = Field(description="Text of the manual pages cited on the card")
