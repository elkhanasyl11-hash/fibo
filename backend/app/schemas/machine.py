"""Request/response schemas for machines."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import Money, UTCDatetime, reject_explicit_nulls
from app.schemas.incident import IncidentRead
from app.schemas.reading import ReadingRead
from app.schemas.risk_score import RiskScoreRead


class MachineBase(BaseModel):
    name: str = Field(min_length=1, max_length=100, examples=["ЧПУ-1 Haas VF-2"])
    type: str = Field(min_length=1, max_length=50, examples=["cnc_mill"])
    model: str | None = Field(default=None, max_length=100)
    criticality: int = Field(default=2, ge=1, le=3, description="1 = low, 3 = line stops without it")
    downtime_cost_per_hour_kzt: Money = Field(default=Decimal("0"))
    avg_repair_hours: float = Field(default=4.0, gt=0, le=720)
    last_maintenance_at: UTCDatetime | None = None
    maintenance_interval_hours: float | None = Field(default=None, gt=0)
    batch_value_kzt: Money | None = Field(default=None, description="Food profiles: value of one batch")
    tool_changed_at: UTCDatetime | None = Field(default=None, description="Last tool change (tool wear)")


class MachineCreate(MachineBase):
    workshop_id: int


class MachineUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    criticality: int | None = Field(default=None, ge=1, le=3)
    downtime_cost_per_hour_kzt: Money | None = None
    avg_repair_hours: float | None = Field(default=None, gt=0, le=720)
    last_maintenance_at: UTCDatetime | None = None
    maintenance_interval_hours: float | None = Field(default=None, gt=0)
    batch_value_kzt: Money | None = None
    tool_changed_at: UTCDatetime | None = None

    @model_validator(mode="after")
    def no_null_for_required_columns(self) -> "MachineUpdate":
        reject_explicit_nulls(self, {"name", "criticality", "downtime_cost_per_hour_kzt", "avg_repair_hours"})
        return self


class MachineRead(MachineBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workshop_id: int
    is_demo: bool
    created_at: datetime


class MachineSummary(BaseModel):
    """One machine's page on the dashboard."""

    machine: MachineRead
    latest_risk: RiskScoreRead | None = Field(description="None until the first risk computation")
    open_incidents: list[IncidentRead] = Field(description="Status received / processing / open")
    recent_readings: list[ReadingRead] = Field(description="Latest 10 readings, newest first")
