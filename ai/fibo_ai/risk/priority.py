"""Ranking and priority calculation in tenge (KZT)."""

from pathlib import Path

import yaml

from fibo_ai.schemas.risk import MachineContext

CRITICALITY_WEIGHTS = {
    "low": 0.5,
    "medium": 1.0,
    "high": 1.5,
}

_config_path = Path("configs/risk_index.yaml")
if _config_path.exists():
    with _config_path.open(encoding="utf-8") as _config_file:
        _config = yaml.safe_load(_config_file) or {}
    CRITICALITY_WEIGHTS.update(_config.get("criticality_weights", {}))


def calculate_priority_kzt(
    risk_index: float,
    context: MachineContext,
    is_batch_profile: bool = False,
) -> int:
    """Calculate expected downtime and scrap loss ranking score in KZT."""
    crit_w = CRITICALITY_WEIGHTS.get(context.criticality.lower(), 1.0)
    repair_h = context.expected_repair_hours
    cost_h = context.cost_per_hour_kzt

    p_eff = risk_index
    loss = p_eff * crit_w * cost_h * repair_h

    if is_batch_profile and context.batch_value_kzt:
        loss += p_eff * context.batch_value_kzt

    return int(round(loss))
