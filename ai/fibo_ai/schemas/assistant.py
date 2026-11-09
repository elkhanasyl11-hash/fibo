from typing import Any

from pydantic import ConfigDict, Field

from fibo_ai.schemas.common import BaseResponse, FiboBaseModel, Lang


class OperatorChatRequest(FiboBaseModel):
    machine_id: str = Field(..., description="Target machine ID")
    question: str = Field(..., description="Operator follow-up question")
    lang: Lang = Field(Lang.ru, description="Operator language")
    incident_context: dict[str, Any] | None = Field(
        None, description="Previous incident context if in follow-up thread"
    )


class OperatorChatResponse(BaseResponse):
    reply: str = Field(..., description="Concise operator instruction")
    manual_pages: list[int] = Field(default_factory=list, description="Verified manual pages cited")
    safety_applied: bool = Field(False, description="Whether safety rule forced stop/warning")


# Repository records returned by backend DataRepository protocol
class IncidentRecord(FiboBaseModel):
    id: str
    workshop_id: str
    machine_id: str
    created_at: str
    level: str
    status: str
    loss_kzt: int
    downtime_hours: float


class DowntimeRecord(FiboBaseModel):
    id: str
    machine_id: str
    start_time: str
    end_time: str | None
    hours: float
    reason: str


class MachineAggregate(FiboBaseModel):
    machine_id: str
    machine_name: str
    incidents_count: int
    downtime_hours: float
    loss_kzt: int


class RiskRow(FiboBaseModel):
    machine_id: str
    machine_name: str
    risk_index: float
    priority_kzt: int
    risk_band: str


class MachineRecord(FiboBaseModel):
    id: str
    name: str
    profile: str
    rated_rpm: float
    rated_torque_nm: float


class DashboardChatRequest(FiboBaseModel):
    workshop_id: str = Field(..., description="Workshop identifier")
    query: str = Field(..., description="Natural language question from chief mechanic/owner")
    lang: Lang = Field(Lang.ru, description="Output language")

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "workshop_id": "ws-shymkent-01",
                "query": "Какой станок простаивал чаще всего в октябре и во сколько это обошлось?",
                "lang": "ru",
            }
        },
    )


class DashboardChatResponse(BaseResponse):
    answer_markdown: str = Field(..., description="Synthesized response strictly quoting verified data")
    table_markdown: str | None = Field(None, description="Structured markdown table of results")
    data_refs: list[str] = Field(default_factory=list, description="Identifiers of rows/machines backing the answer")
    tools_called: list[str] = Field(default_factory=list, description="Tool audit log")
