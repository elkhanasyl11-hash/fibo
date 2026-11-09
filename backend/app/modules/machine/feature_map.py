"""Fibo Machine: turn a workshop's readings into the 8 features of the AI4I-trained model.

The AI4I dataset comes from a lab simulation of a milling process. Our workshops report other
quantities, so some features are APPROXIMATIONS. Every approximation that was used for a score is
returned in `assumptions` (code + Russian text) and shown in the API response; all of them are
listed in docs/decisions.md and the README.

  spindle_rpm      -> rotational_speed_rpm                       (direct)
  load_pct         -> torque_nm = load_pct / 100 x profile.nominal_torque_nm   (approximation)
  temperature_c    -> process_temperature_k = temperature_c + 273.15
                      (missing: air temperature + 10 K, the typical AI4I gap; approximation)
  air temperature  -> profile.default_air_temperature_k          (approximation: not measured)
  tool wear        -> operating minutes since machines.tool_changed_at, from the operating-hours
                      counter in readings (fallback: wall-clock minutes), capped at the training max
  machine class    -> fixed to L, the most common AI4I product class (60% of rows). Criticality is
                      NOT used: in AI4I L/M/H is a product quality variant, and mapping criticality
                      to it changed the probability non-monotonically (audit, decisions D71).

The model is NOT applicable (result.features is None) when the profile says so (food, sewing), when
no model is loaded, or when required inputs are missing; `missing` then says what is lacking.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.profiles.loader import ProfileConfig

KELVIN = 273.15
AI4I_PROCESS_MINUS_AIR_K = 10.0
FRESHNESS = timedelta(days=14)  # an older reading says little about the machine today
FIXED_PRODUCT_CLASS = "L"  # most common class in AI4I; see module docstring


@dataclass
class ReadingValues:
    """Plain copy of one reading (what-if scenarios modify copies, never database rows)."""

    recorded_at: datetime
    spindle_rpm: float | None = None
    load_pct: float | None = None
    temperature_c: float | None = None
    operating_hours: float | None = None
    extra: dict | None = None


@dataclass
class FeatureMapResult:
    features: dict[str, float] | None
    assumptions: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def _note(code: str, text: str) -> dict:
    return {"code": code, "text": text}


def tool_wear_minutes(
    tool_changed_at: datetime | None, history: list[ReadingValues], now: datetime
) -> tuple[float | None, dict | None]:
    """Operating minutes since the last tool change, plus the assumption used (if any)."""
    if tool_changed_at is None:
        return None, None
    counters = [r for r in history if r.operating_hours is not None]
    if counters:
        before = [r for r in counters if r.recorded_at <= tool_changed_at]
        after = [r for r in counters if r.recorded_at > tool_changed_at]
        start = before[-1] if before else after[0]
        return max(0.0, (counters[-1].operating_hours - start.operating_hours) * 60), None
    minutes = max(0.0, (now - tool_changed_at).total_seconds() / 60)
    return minutes, _note(
        "tool_wear_wall_clock",
        "Наработка неизвестна: износ инструмента посчитан по календарному "
        "времени с замены инструмента (завышает износ)",
    )


def map_features(
    profile: ProfileConfig,
    tool_changed_at: datetime | None,
    history: list[ReadingValues],
    now: datetime,
    training_ranges: dict[str, list[float]],
    tool_wear_override: float | None = None,
) -> FeatureMapResult:
    """history: readings ordered oldest -> newest. The newest one with rpm and load is used."""
    if not profile.model_applicable:
        return FeatureMapResult(None, missing=["model_not_applicable_for_profile"])
    usable = [r for r in history if r.spindle_rpm is not None and r.load_pct is not None]
    if not usable or now - usable[-1].recorded_at > FRESHNESS:
        return FeatureMapResult(None, missing=["recent_reading_with_spindle_rpm_and_load_pct"])
    latest = usable[-1]

    wear, wear_note = tool_wear_minutes(tool_changed_at, history, now)
    if tool_wear_override is not None:
        wear, wear_note = tool_wear_override, None
    if wear is None:
        return FeatureMapResult(None, missing=["tool_changed_at"])

    air_k = profile.default_air_temperature_k
    assumptions = [
        _note(
            "torque_from_load",
            f"Момент = нагрузка% × {profile.nominal_torque_nm:g} Н·м (номинал профиля) — приближение",
        ),
        _note(
            "air_temperature_default", f"Температура воздуха не измеряется: принята {air_k - KELVIN:.0f} °C"
        ),
        _note("fixed_product_class", "Класс продукта AI4I принят L (самый частый) для всех станков"),
    ]
    if wear_note:
        assumptions.append(wear_note)
    if latest.temperature_c is not None:
        process_k = latest.temperature_c + KELVIN
    else:
        process_k = air_k + AI4I_PROCESS_MINUS_AIR_K
        assumptions.append(
            _note(
                "process_temperature_default", "Температура не указана: принята температура воздуха + 10 °C"
            )
        )

    wear_max = training_ranges["tool_wear_min"][1]
    if wear > wear_max:
        assumptions.append(
            _note(
                "tool_wear_capped",
                f"Износ {wear:.0f} мин ограничен максимумом обучающих данных ({wear_max:.0f} мин)",
            )
        )
        wear = wear_max

    features = {f"type_{letter}": float(letter == FIXED_PRODUCT_CLASS) for letter in ("L", "M", "H")}
    features.update(
        {
            "air_temperature_k": air_k,
            "process_temperature_k": process_k,
            "rotational_speed_rpm": latest.spindle_rpm,
            "torque_nm": latest.load_pct / 100 * profile.nominal_torque_nm,
            "tool_wear_min": wear,
        }
    )
    for name in ("rotational_speed_rpm", "torque_nm", "process_temperature_k"):
        low, high = training_ranges[name]
        if not low <= features[name] <= high:
            assumptions.append(
                _note(
                    f"{name}_out_of_range",
                    f"{name}={features[name]:.1f} вне диапазона обучающих "
                    f"данных [{low:g}; {high:g}] — оценка менее надёжна",
                )
            )
    return FeatureMapResult(features, assumptions)
