"""Response schemas for Fibo Reports."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import Money


class MachineReport(BaseModel):
    machine_id: int
    machine: str
    incidents: int
    failures: int = Field(description="Incidents with level warning or critical")
    downtime_hours: float = Field(description="Resolved incidents only")
    loss_kzt: Money
    ongoing_hours: float = Field(description="Unresolved incidents, counted until now")
    ongoing_loss_kzt: Money
    operating_hours: float
    operating_hours_source: str = Field(description="counter = operating-hours readings; calendar = period")
    mtbf_hours: float | None = Field(description="operating_hours / failures; null without failures")


class ReportTotals(BaseModel):
    incidents: int
    failures: int
    downtime_hours: float
    loss_kzt: Money
    ongoing_hours: float
    ongoing_loss_kzt: Money


class TopCause(BaseModel):
    cause: str
    count: int


class ReportSummary(BaseModel):
    workshop_id: int
    workshop: str
    is_demo: bool = Field(description="True = synthetic demo data")
    period_from: datetime
    period_to: datetime
    totals: ReportTotals
    machines: list[MachineReport]
    top_causes: list[TopCause]
