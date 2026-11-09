"""Fibo Assistant: the tools the AI chat may call, always scoped to ONE workshop.

The model only sees the tool names and argument schemas below. The workshop id is never a tool
argument: run_tool() receives it from the request, so the model cannot read another workshop's data.
Every tool returns plain JSON-able data plus the machine / incident ids it talked about (the UI
uses them to link the answer). Bad arguments give {"error": ...} instead of an exception, so the
model can correct itself.
"""

from dataclasses import dataclass, field
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import IncidentStatus
from app.models.machine import Machine
from app.modules.assistant.analysis_tools import maintenance_plan, reading_trends
from app.modules.machine import service as risk_service
from app.modules.reports.summary import build_summary
from app.schemas.risk_score import RiskScoreRead, WhatIfOverrides
from app.services import incidents as incidents_service
from app.services import machines as machines_service


def _function(name: str, description: str, properties: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "additionalProperties": False},
        },
    }


_PERIOD = {
    "from": {"type": "string", "description": "ISO 8601 with timezone, optional"},
    "to": {"type": "string", "description": "ISO 8601 with timezone, optional"},
}
TOOL_DEFINITIONS = [
    _function(
        "get_risk_ranking",
        "Machines of the workshop ordered by maintenance priority (expected loss "
        "in KZT), with risk index, failure probability and main factors.",
        {},
    ),
    _function(
        "get_machine_summary",
        "One machine: latest risk score, open incidents, last reading.",
        {"machine_name_or_id": {"type": "string"}},
    ),
    _function(
        "get_incidents",
        "Incidents of the workshop, newest first, optionally by period, machine, status.",
        {
            **_PERIOD,
            "machine": {"type": "string"},
            "status": {"type": "string", "enum": [s.value for s in IncidentStatus]},
        },
    ),
    _function(
        "get_downtime_report",
        "Downtime hours, losses in KZT, MTBF and top causes for a period (default: last 30 days).",
        _PERIOD,
    ),
]
TOOL_DEFINITIONS += [
    _function(
        "get_reading_trends",
        "Compare first/latest, min/max measurements of ONE machine over 1–90 days. "
        "No diagnosis inferred from a trend alone.",
        {"machine_name_or_id": {"type": "string"}, "days": {"type": "integer", "minimum": 1, "maximum": 90}},
    ),
    _function(
        "get_maintenance_plan",
        "Maintenance schedule: overdue equipment first, then expected loss in KZT. "
        "Uses actual service dates and calendar-hour intervals.",
        {},
    ),
    _function(
        "compare_maintenance",
        "Calculate current risk vs hypothetical maintenance for one machine. "
        "Read-only: does NOT mark maintenance complete or save predictions.",
        {"machine_name_or_id": {"type": "string"}},
    ),
]


@dataclass
class ToolResult:
    data: dict
    machine_ids: list[int] = field(default_factory=list)
    incident_ids: list[int] = field(default_factory=list)


class PeriodArgs(BaseModel):
    """Optional period given by the model; datetimes must carry a timezone."""

    date_from: AwareDatetime | None = None
    date_to: AwareDatetime | None = None


def _period(arguments: dict) -> tuple[datetime | None, datetime | None]:
    args = PeriodArgs(date_from=arguments.get("from"), date_to=arguments.get("to"))
    return args.date_from, args.date_to


async def _find_machine(session: AsyncSession, workshop_id: int, name_or_id: str) -> Machine | None:
    machines = await machines_service.list_for_workshop(session, workshop_id)
    text = str(name_or_id).strip().lower()
    return next((m for m in machines if str(m.id) == text), None) or next(
        (m for m in machines if text and text in m.name.lower()), None
    )


def _risk(score) -> dict:
    read = RiskScoreRead.model_validate(score)
    return {
        "risk_index": read.risk_index,
        "priority_kzt": str(read.priority_kzt),
        "failure_probability": read.failure_probability,
        "is_anomaly": read.is_anomaly,
        "main_factors": [f"{f['title_ru']} ({f['contribution']:+.2f})" for f in read.shap_top3],
        "inputs_used": read.inputs_used,
        "computed_at": read.computed_at.isoformat(),
    }


async def get_risk_ranking(session: AsyncSession, workshop_id: int, arguments: dict) -> ToolResult:
    rows = await risk_service.ranking(session, workshop_id)
    items = [{"machine_id": m.id, "machine": m.name, **_risk(score)} for score, m in rows[:10]]
    return ToolResult({"ranking": items}, machine_ids=[i["machine_id"] for i in items[:3]])


async def get_machine_summary(session: AsyncSession, workshop_id: int, arguments: dict) -> ToolResult:
    machine = await _find_machine(session, workshop_id, arguments.get("machine_name_or_id", ""))
    if machine is None:
        names = [m.name for m in await machines_service.list_for_workshop(session, workshop_id)]
        return ToolResult({"error": "machine not found in this workshop", "machines": names})
    summary = await machines_service.build_summary(session, machine.id)
    latest = summary.recent_readings[0] if summary.recent_readings else None
    incidents = [
        {
            "id": i.id,
            "level": i.level,
            "status": i.status,
            "verdict": i.verdict,
            "created_at": i.created_at.isoformat(),
        }
        for i in summary.open_incidents
    ]
    data = {
        "machine": machine.name,
        "type": machine.type,
        "criticality": machine.criticality,
        "latest_risk": _risk(summary.latest_risk) if summary.latest_risk else None,
        "open_incidents": incidents,
        "last_reading": latest.model_dump(mode="json", exclude={"id", "machine_id"}) if latest else None,
    }
    return ToolResult(data, machine_ids=[machine.id], incident_ids=[i["id"] for i in incidents])


async def get_incidents(session: AsyncSession, workshop_id: int, arguments: dict) -> ToolResult:
    date_from, date_to = _period(arguments)
    machine_id = None
    if arguments.get("machine"):
        machine = await _find_machine(session, workshop_id, arguments["machine"])
        if machine is None:
            return ToolResult({"error": "machine not found in this workshop"})
        machine_id = machine.id
    status = IncidentStatus(arguments["status"]) if arguments.get("status") else None
    filters = incidents_service.IncidentFilters(workshop_id, machine_id, status, None, date_from, date_to)
    incidents = await incidents_service.list_incidents(session, filters, limit=20, offset=0)
    names = {
        m.id: m.name
        for m in (await session.scalars(select(Machine).where(Machine.workshop_id == workshop_id))).all()
    }
    items = [
        {
            "id": i.id,
            "machine": names.get(i.machine_id),
            "level": i.level,
            "status": i.status,
            "verdict": i.verdict,
            "created_at": i.created_at.isoformat(),
            "downtime_hours": i.downtime_hours,
            "loss_kzt": str(i.loss_kzt) if i.loss_kzt is not None else None,
        }
        for i in incidents
    ]
    return ToolResult(
        {"count": len(items), "incidents": items},
        incident_ids=[i["id"] for i in items],
        machine_ids=sorted({i.machine_id for i in incidents}),
    )


async def get_downtime_report(session: AsyncSession, workshop_id: int, arguments: dict) -> ToolResult:
    date_from, date_to = _period(arguments)
    report = await build_summary(session, workshop_id, date_from, date_to)
    machines = [
        {k: (str(v) if k.endswith("_kzt") else v) for k, v in row.items()}
        for row in report["machines"]
        if row["incidents"]
    ]
    totals = {k: (str(v) if k.endswith("_kzt") else v) for k, v in report["totals"].items()}
    data = {
        "period_from": report["period_from"].isoformat(),
        "period_to": report["period_to"].isoformat(),
        "totals": totals,
        "machines": machines,
        "top_causes": report["top_causes"],
    }
    return ToolResult(data, machine_ids=[m["machine_id"] for m in machines])


async def get_reading_trends(session: AsyncSession, workshop_id: int, arguments: dict) -> ToolResult:
    machine = await _find_machine(session, workshop_id, arguments.get("machine_name_or_id", ""))
    if machine is None:
        return ToolResult({"error": "Specify a machine in this workshop"})
    days = arguments.get("days", 7)
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 90:
        return ToolResult({"error": "days must be an integer from 1 to 90"})
    return ToolResult(await reading_trends(session, machine, days), machine_ids=[machine.id])


async def get_maintenance_plan(session: AsyncSession, workshop_id: int, arguments: dict) -> ToolResult:
    data = await maintenance_plan(session, workshop_id)
    return ToolResult(data, machine_ids=[item["machine_id"] for item in data["machines"][:5]])


async def compare_maintenance(session: AsyncSession, workshop_id: int, arguments: dict) -> ToolResult:
    machine = await _find_machine(session, workshop_id, arguments.get("machine_name_or_id", ""))
    if machine is None:
        return ToolResult({"error": "Specify a machine in this workshop"})
    current, scenario = await risk_service.what_if(
        session, machine.id, WhatIfOverrides(maintenance_done=True)
    )
    return ToolResult(
        {
            "machine": machine.name,
            "current_risk": current.risk_index,
            "scenario_risk": scenario.risk_index,
            "current_priority_kzt": str(current.priority_kzt),
            "scenario_priority_kzt": str(scenario.priority_kzt),
            "saved": False,
            "note": "A hypothetical model scenario, not a guaranteed saving.",
        },
        machine_ids=[machine.id],
    )


TOOLS = {
    "get_reading_trends": get_reading_trends,
    "get_maintenance_plan": get_maintenance_plan,
    "compare_maintenance": compare_maintenance,
    "get_risk_ranking": get_risk_ranking,
    "get_machine_summary": get_machine_summary,
    "get_incidents": get_incidents,
    "get_downtime_report": get_downtime_report,
}


async def run_tool(session: AsyncSession, workshop_id: int, name: str, arguments: dict) -> ToolResult:
    if name not in TOOLS:
        return ToolResult({"error": f"unknown tool {name}"})
    try:
        return await TOOLS[name](session, workshop_id, arguments)
    except (ValidationError, ValueError) as exc:  # bad arguments from the model: tell it, do not crash
        return ToolResult({"error": f"invalid arguments: {str(exc)[:200]}"})
