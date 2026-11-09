"""Risk index signals and weighted combination; priority formula; Isolation Forest."""

import random
from decimal import Decimal

import pytest

from app.db.base import Profile
from app.modules.machine import risk_index as ri
from app.modules.machine.anomaly import detect_anomaly
from app.modules.machine.priority import priority_kzt
from app.profiles.loader import RiskWeights


def test_signal_normalisation():
    assert ri.audio_signal(None) is None
    assert ri.audio_signal(1.0) == 0 and ri.audio_signal(2.5) == 0.5 and ri.audio_signal(9) == 1
    assert ri.visual_signal("warning") == 0.5 and ri.visual_signal(None) is None
    assert ri.overdue_signal(400, 500) == 0  # not yet due
    assert ri.overdue_signal(750, 500) == 0.5
    assert ri.overdue_signal(5000, 500) == 1
    assert ri.overdue_signal(100, None) is None and ri.overdue_signal(None, 500) is None
    assert ri.history_signal(0) == 0 and ri.history_signal(6) == 1


def test_combine_uses_only_available_signals():
    weights = RiskWeights(p_model=0.4, s_audio=0.2, s_visual=0.15, s_overdue=0.15, s_history=0.1)
    index, used = ri.combine(ri.Signals(p_model=0.5, s_history=0.0), weights)
    assert used == ["p_model", "s_history"]
    assert index == pytest.approx(0.4 * 0.5 / 0.5)  # renormalised over 0.4 + 0.1


def test_combine_ignores_zero_weight_and_handles_nothing():
    weights = RiskWeights(p_model=0, s_audio=0.5, s_history=0.5)
    assert ri.combine(ri.Signals(p_model=1.0, s_history=1.0), weights) == (1.0, ["s_history"])
    assert ri.combine(ri.Signals(), weights) == (0.0, [])


def test_priority_formula():
    # 0.5 x 1.5 (criticality 3) x 20 000 KZT/h x 6 h = 90 000
    assert priority_kzt(0.5, 3, Decimal("20000"), 6.0, None, Profile.METALWORKING) == Decimal("90000.00")
    assert priority_kzt(0.5, 1, Decimal("20000"), 6.0, None, Profile.METALWORKING) == Decimal("30000.00")
    # food profile adds risk x batch value; non-food ignores it
    assert priority_kzt(0.5, 2, Decimal("1000"), 2.0, Decimal("40000"), Profile.BAKERY) == Decimal("21000.00")
    assert priority_kzt(0.5, 2, Decimal("1000"), 2.0, Decimal("40000"), Profile.SEWING) == Decimal("1000.00")
    assert priority_kzt(0.0, 3, Decimal("50000"), 8.0, None, Profile.METALWORKING) == Decimal("0.00")


def _rows(n: int, last: dict | None = None) -> list[dict]:
    rng = random.Random(1)
    rows = [
        {
            "spindle_rpm": rng.gauss(2800, 50),
            "load_pct": rng.gauss(55, 3),
            "temperature_c": rng.gauss(36, 1),
            "operating_hours": 1000 + i,
            "extra": None,
        }
        for i in range(n)
    ]
    if last:
        rows.append({**rows[-1], **last, "operating_hours": 5000})
    return rows


def test_isolation_forest():
    assert detect_anomaly(_rows(10)).reason == "insufficient history"
    assert detect_anomaly(_rows(40, last={"load_pct": 140, "temperature_c": 80})).is_anomaly is True
    typical = detect_anomaly(_rows(40, last={"load_pct": 55, "temperature_c": 36}))
    assert typical.is_anomaly is False and "operating_hours" not in typical.columns
