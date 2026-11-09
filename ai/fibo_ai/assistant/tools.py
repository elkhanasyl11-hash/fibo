"""Allow-listed, read-only tools over the backend DataRepository protocol."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

from fibo_ai.assistant.repository import DataRepository
from fibo_ai.schemas.assistant import (
    DowntimeRecord,
    IncidentRecord,
    MachineAggregate,
    MachineRecord,
    RiskRow,
)

ToolName = Literal["get_incidents", "get_downtime", "top_machines", "get_risk_ranking", "get_machine"]
BY_OPTIONS = ("incidents", "downtime_hours", "loss_kzt")
MONTHS: dict[str, int] = {
    "январь": 1,
    "февраль": 2,
    "март": 3,
    "апрель": 4,
    "май": 5,
    "июнь": 6,
    "июль": 7,
    "август": 8,
    "сентябрь": 9,
    "октябрь": 10,
    "октября": 10,
    "октябре": 10,
    "ноябрь": 11,
    "декабрь": 12,
    "қаңтар": 1,
    "ақпан": 2,
    "наурыз": 3,
    "сәуір": 4,
    "мамыр": 5,
    "маусым": 6,
    "шілде": 7,
    "тамыз": 8,
    "қыркүйек": 9,
    "қазан": 10,
    "қараша": 11,
    "желтоқсан": 12,
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "in october": 10,
    "november": 11,
    "december": 12,
}


@dataclass(frozen=True)
class ToolResult:
    tool_name: ToolName
    rows: Sequence[IncidentRecord | DowntimeRecord | MachineAggregate | RiskRow | MachineRecord]
    since: str | None = None
    until: str | None = None


def date_range(query: str) -> tuple[str, str]:
    folded = query.casefold()
    now = datetime.now(UTC)
    month = next((number for word, number in MONTHS.items() if word in folded), None)
    explicit_year = re.search(r"\b(20\d{2})\b", folded)
    if month:
        year = int(explicit_year.group(1)) if explicit_year else now.year
        start = datetime(year, month, 1, tzinfo=UTC)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(year, month + 1, 1, tzinfo=UTC)
        return start.isoformat(), end.isoformat()
    end = now
    start = end - timedelta(days=30)
    return start.isoformat(), end.isoformat()


def select_tool(query: str) -> tuple[ToolName, str]:
    folded = query.casefold()
    if any(word in folded for word in ("risk", "тәуекел", "риск", "priority", "рейтинг")):
        return "get_risk_ranking", "risk_index"
    if any(word in folded for word in ("often", "чаще", "част", "жиі", "stopped most")):
        return "top_machines", "incidents"
    if any(word in folded for word in ("machine", "станок", "станка", "станог", "станоктың")):
        machine = re.search(r"(?:чпу|cnc|пила|насос)[-\s]?\d+", folded, flags=re.IGNORECASE)
        if machine and any(word in folded for word in ("info", "about", "параметр", "инфо")):
            return "get_machine", machine.group(0).replace(" ", "-").upper()
    if any(word in folded for word in ("cost", "loss", "убыт", "ущерб", "обошл", "шығын")):
        return "top_machines", "loss_kzt"
    if any(word in folded for word in ("downtime", "просто", "тоқтап", "тоқтау")):
        return "top_machines", "downtime_hours"
    if any(word in folded for word in ("incident", "breakdown", "останов")):
        return "top_machines", "incidents"
    return "top_machines", "incidents"


class ReadOnlyTools:
    """Dispatches only explicitly supported DataRepository methods."""

    def __init__(self, repository: DataRepository) -> None:
        self.repository = repository

    async def execute(
        self,
        tool_name: ToolName,
        *,
        workshop_id: str,
        since: str,
        until: str,
        argument: str | None = None,
        limit: int = 5,
    ) -> ToolResult:
        bounded_limit = max(1, min(20, limit))
        rows: Sequence[IncidentRecord | DowntimeRecord | MachineAggregate | RiskRow | MachineRecord]
        if tool_name == "get_incidents":
            rows = await self.repository.get_incidents(
                workshop_id=workshop_id,
                since=since,
                until=until,
                machine_id=argument,
                limit=bounded_limit,
            )
        elif tool_name == "get_downtime":
            rows = await self.repository.get_downtime(
                workshop_id=workshop_id,
                since=since,
                until=until,
                machine_id=argument,
            )
        elif tool_name == "top_machines":
            by = cast(Literal["incidents", "downtime_hours", "loss_kzt"], argument)
            if by not in BY_OPTIONS:
                by = "incidents"
            rows = await self.repository.top_machines(
                workshop_id=workshop_id,
                since=since,
                until=until,
                by=by,
                limit=bounded_limit,
            )
        elif tool_name == "get_risk_ranking":
            rows = (await self.repository.get_risk_ranking(workshop_id=workshop_id))[:bounded_limit]
        elif tool_name == "get_machine":
            machine = await self.repository.get_machine(
                workshop_id=workshop_id,
                machine_id=argument or "",
            )
            rows = [machine] if machine else []
        else:  # pragma: no cover - Literal and closed dispatch guard this path.
            raise ValueError("Unsupported read-only tool")
        return ToolResult(tool_name, rows, since, until)


def number_tokens(value: str) -> set[str]:
    tokens = re.findall(r"(?<!\w)\d[\d,]*(?:\.\d+)?%?", value)
    return {token.replace(",", "") for token in tokens}


def numbers_in_tool_result(result: ToolResult) -> set[str]:
    import json

    return number_tokens(json.dumps([row.model_dump() for row in result.rows], ensure_ascii=False))


def numbers_are_verified(text: str, result: ToolResult) -> bool:
    allowed = numbers_in_tool_result(result)
    for token in number_tokens(text):
        normalized = token.rstrip("%")
        if normalized not in allowed and f"{normalized}.0" not in allowed:
            return False
    return True
