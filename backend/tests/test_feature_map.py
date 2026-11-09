"""Readings -> AI4I features, with every approximation reported."""

from datetime import UTC, datetime, timedelta

from app.db.base import Profile
from app.modules.machine.feature_map import ReadingValues, map_features, tool_wear_minutes
from app.profiles.loader import load_profiles

PROFILES = load_profiles()
METAL = PROFILES[Profile.METALWORKING]
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
RANGES = {
    "tool_wear_min": [0, 253],
    "rotational_speed_rpm": [1168, 2886],
    "torque_nm": [3.8, 76.6],
    "process_temperature_k": [305.7, 313.8],
}


def reading(hours_ago: float, **values) -> ReadingValues:
    return ReadingValues(recorded_at=NOW - timedelta(hours=hours_ago), **values)


def test_direct_and_approximated_features():
    history = [reading(1, spindle_rpm=1500, load_pct=50, temperature_c=36, operating_hours=100)]
    result = map_features(METAL, NOW - timedelta(hours=2), history, NOW, RANGES)
    f = result.features
    assert f["rotational_speed_rpm"] == 1500
    assert f["torque_nm"] == 30.0  # 50% x 60 Nm nominal
    assert abs(f["process_temperature_k"] - 309.15) < 1e-9
    assert f["air_temperature_k"] == 298
    assert (f["type_L"], f["type_M"], f["type_H"]) == (1, 0, 0)  # fixed class L, criticality not used
    codes = {a["code"] for a in result.assumptions}
    assert {"torque_from_load", "air_temperature_default", "fixed_product_class"} <= codes


def test_missing_temperature_uses_air_plus_10k():
    result = map_features(METAL, NOW, [reading(1, spindle_rpm=1500, load_pct=50)], NOW, RANGES)
    assert result.features["process_temperature_k"] == 308
    assert "process_temperature_default" in {a["code"] for a in result.assumptions}


def test_tool_wear_from_operating_hours_counter():
    history = [
        reading(10, operating_hours=100),
        reading(5, operating_hours=101),
        reading(1, operating_hours=103),
    ]
    minutes, note = tool_wear_minutes(NOW - timedelta(hours=7), history, NOW)
    assert minutes == 180 and note is None  # 103 - 100 h = 3 h of operation


def test_tool_wear_wall_clock_fallback_and_cap():
    history = [reading(1, spindle_rpm=1500, load_pct=50)]
    minutes, note = tool_wear_minutes(NOW - timedelta(hours=2), history, NOW)
    assert minutes == 120 and note["code"] == "tool_wear_wall_clock"
    result = map_features(METAL, NOW - timedelta(days=2), history, NOW, RANGES)
    assert result.features["tool_wear_min"] == 253
    assert "tool_wear_capped" in {a["code"] for a in result.assumptions}


def test_out_of_training_range_is_flagged():
    history = [reading(1, spindle_rpm=12000, load_pct=50, temperature_c=36)]
    result = map_features(METAL, NOW, history, NOW, RANGES)
    assert "rotational_speed_rpm_out_of_range" in {a["code"] for a in result.assumptions}


def test_model_not_applicable_cases():
    fresh = [reading(1, spindle_rpm=1500, load_pct=50)]
    assert map_features(PROFILES[Profile.BAKERY], NOW, fresh, NOW, RANGES).missing == [
        "model_not_applicable_for_profile"
    ]
    assert map_features(METAL, None, fresh, NOW, RANGES).missing == ["tool_changed_at"]
    stale = [reading(24 * 20, spindle_rpm=1500, load_pct=50)]
    assert map_features(METAL, NOW, stale, NOW, RANGES).features is None
    no_load = [reading(1, spindle_rpm=1500)]
    assert map_features(METAL, NOW, no_load, NOW, RANGES).features is None
