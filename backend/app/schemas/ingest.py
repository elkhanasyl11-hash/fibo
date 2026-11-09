"""Response schemas of the bot-facing ingest endpoints and incident actions."""

from pydantic import BaseModel, Field


class IngestAccepted(BaseModel):
    incident_id: int
    status: str = Field(default="received", description="Poll GET /incidents/{id} until open or failed")


class EscalateResponse(BaseModel):
    """ "Call mechanic": the bot forwards card_text to every master's Telegram."""

    incident_id: int
    machine_id: int
    machine_name: str
    master_telegram_ids: list[int]
    card_text: str | None
