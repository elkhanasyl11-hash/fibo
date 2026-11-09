"""Fibo Machine: maintenance priority in tenge (expected loss if we do nothing).

    priority_kzt = risk_index x criticality_weight x downtime_cost_per_hour_kzt x avg_repair_hours
                   (+ risk_index x batch_value_kzt for food profiles: a failure also spoils the batch)
    criticality_weight = {1: 0.5, 2: 1.0, 3: 1.5}

The original formula multiplies by P(failure). We use risk_index instead because P is not
available for machines where the AI4I model does not apply (see docs/decisions.md).
"""

from decimal import ROUND_HALF_UP, Decimal

from app.db.base import Profile

CRITICALITY_WEIGHT = {1: Decimal("0.5"), 2: Decimal("1.0"), 3: Decimal("1.5")}
FOOD_PROFILES = {Profile.BAKERY, Profile.CONFECTIONERY, Profile.DAIRY}
CENT = Decimal("0.01")


def priority_kzt(
    risk_index: float,
    criticality: int,
    downtime_cost_per_hour_kzt: Decimal,
    avg_repair_hours: float,
    batch_value_kzt: Decimal | None,
    profile: Profile,
) -> Decimal:
    risk = Decimal(str(risk_index))
    value = (
        risk
        * CRITICALITY_WEIGHT[criticality]
        * Decimal(downtime_cost_per_hour_kzt)
        * Decimal(str(avg_repair_hours))
    )
    if profile in FOOD_PROFILES and batch_value_kzt is not None:
        value += risk * Decimal(batch_value_kzt)
    return value.quantize(CENT, rounding=ROUND_HALF_UP)
