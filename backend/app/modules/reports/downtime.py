"""Fibo Reports: downtime, losses and MTBF per machine for a period (pure calculations).

Inputs are plain values (incidents and readings already loaded), so every rule is unit-testable:
  downtime_hours / loss_kzt   resolved incidents: the values stored when "Resolved" was pressed
  ongoing_hours / ongoing_loss_kzt   incidents not resolved yet: from reporting time until `now`
                              (shown separately: they are still growing)
  failures                    incidents with level warning or critical
  operating_hours             from the machine's operating-hours counter (last - first reading in the
                              period); if there is no counter, the calendar length of the period is
                              used and operating_hours_source says "calendar"
  mtbf_hours                  operating_hours / failures; None if there were no failures
  top causes                  most frequent incident causes, compared case-insensitively
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from app.db.base import IncidentLevel, IncidentStatus

FAILURE_LEVELS = {IncidentLevel.WARNING, IncidentLevel.CRITICAL}
CENT = Decimal("0.01")


@dataclass
class IncidentFacts:
    status: IncidentStatus
    level: IncidentLevel | None
    created_at: datetime
    downtime_hours: float | None
    loss_kzt: Decimal | None
    causes: list[str]


@dataclass
class MachineDowntime:
    incidents: int
    failures: int
    downtime_hours: float
    loss_kzt: Decimal
    ongoing_hours: float
    ongoing_loss_kzt: Decimal
    operating_hours: float
    operating_hours_source: str  # "counter" | "calendar"
    mtbf_hours: float | None


def operating_hours(counter_values: list[float], period_hours: float) -> tuple[float, str]:
    """Hours the machine ran in the period: counter difference, else the calendar period."""
    if len(counter_values) >= 2 and max(counter_values) > min(counter_values):
        return max(counter_values) - min(counter_values), "counter"
    return period_hours, "calendar"


def machine_downtime(
    incidents: list[IncidentFacts],
    cost_per_hour: Decimal,
    counter_values: list[float],
    period_hours: float,
    now: datetime,
) -> MachineDowntime:
    resolved = [i for i in incidents if i.status == IncidentStatus.RESOLVED]
    still_open = [i for i in incidents if i.status != IncidentStatus.RESOLVED]
    downtime = sum(i.downtime_hours or 0.0 for i in resolved)
    loss = sum((i.loss_kzt or Decimal(0) for i in resolved), Decimal(0))
    ongoing = sum(max(0.0, (now - i.created_at).total_seconds() / 3600) for i in still_open)
    ongoing_loss = (Decimal(str(ongoing)) * Decimal(cost_per_hour)).quantize(CENT, rounding=ROUND_HALF_UP)
    failures = sum(1 for i in incidents if i.level in FAILURE_LEVELS)
    hours, source = operating_hours(counter_values, period_hours)
    return MachineDowntime(
        incidents=len(incidents),
        failures=failures,
        downtime_hours=round(downtime, 2),
        loss_kzt=Decimal(loss).quantize(CENT),
        ongoing_hours=round(ongoing, 2),
        ongoing_loss_kzt=ongoing_loss,
        operating_hours=round(hours, 1),
        operating_hours_source=source,
        mtbf_hours=round(hours / failures, 1) if failures else None,
    )


def normalise_cause(cause: str) -> str:
    return " ".join(cause.lower().replace("ё", "е").split()).strip(" .")


def top_causes(incidents: list[IncidentFacts], limit: int = 5) -> list[tuple[str, int]]:
    counter = Counter(normalise_cause(c) for i in incidents for c in i.causes if c and c.strip())
    return counter.most_common(limit)
