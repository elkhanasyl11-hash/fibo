"""Adapters mapping real-world workshop telemetry into AI4I model feature scale."""

from typing import Any

import numpy as np
from numpy.typing import NDArray

from fibo_ai.risk.features import FEATURE_COLUMNS, compute_engineered_features
from fibo_ai.schemas.common import Confidence
from fibo_ai.schemas.risk import MachineContext, MachineReadings

# Default training distribution ranges and percentiles (populated from training metadata)
DEFAULT_METADATA: dict[str, Any] = {
    "rpm_min": 1168.0,
    "rpm_max": 2886.0,
    "torque_p99": 65.0,
    "torque_min": 3.8,
    "torque_max": 76.6,
    "max_tool_wear": 253.0,
    "air_temp_mean": 300.0,
    "temp_diff_mean": 10.0,
    "feature_bounds": {
        "air_temp_k": (295.0, 305.0),
        "process_temp_k": (305.0, 315.0),
        "temp_diff_k": (7.0, 13.0),
        "rotational_speed_rpm": (1150.0, 2900.0),
        "torque_nm": (3.0, 80.0),
        "tool_wear_min": (0.0, 260.0),
        "power_w": (1000.0, 10000.0),
        "wear_torque": (0.0, 15000.0),
        "load_per_krpm": (1.0, 60.0),
        "type_code": (0, 2),
    },
}


class MachineAdapter:
    def __init__(self, metadata: dict[str, Any] | None = None) -> None:
        self.meta = metadata or DEFAULT_METADATA

    def adapt_readings(
        self,
        readings: MachineReadings,
        context: MachineContext,
        machine_type: str = "M",
    ) -> tuple[NDArray[np.float32], list[str], list[str], list[str], bool, Confidence]:
        """Convert observed machine readings and context into an AI4I feature vector."""
        assumptions: list[str] = []
        used_signals: list[str] = []
        missing_signals: list[str] = []
        clipped_features: set[str] = set()
        defaulted_features: set[str] = set()

        # 1. RPM normalization
        rated_rpm = context.rated_rpm or 4000.0
        if readings.spindle_rpm is not None:
            # Map the machine's rated operating fraction into the training range.
            raw_rpm_ratio = readings.spindle_rpm / rated_rpm
            if not 0.0 <= raw_rpm_ratio <= 1.0:
                clipped_features.add("rotational_speed_rpm")
            rpm_ratio = np.clip(raw_rpm_ratio, 0.0, 1.0)
            target_rpm = float(self.meta["rpm_min"] + rpm_ratio * (self.meta["rpm_max"] - self.meta["rpm_min"]))
            used_signals.append("spindle_rpm")
        else:
            target_rpm = np.nan
            missing_signals.append("spindle_rpm")
        if context.rated_rpm is None:
            assumptions.append("rated spindle speed defaulted to 4000 rpm")
            defaulted_features.add("rotational_speed_rpm")

        # 2. Spindle load % as torque proxy
        rated_torque = context.rated_torque_nm or float(self.meta["torque_p99"])
        assumptions.append("spindle load % as torque proxy")
        if context.rated_torque_nm is None:
            assumptions.append("rated torque defaulted to AI4I training 99th percentile")
        if readings.spindle_load_pct is not None:
            load_fraction = readings.spindle_load_pct / 100.0
            raw_torque = load_fraction * rated_torque
            if raw_torque < self.meta["torque_min"] or raw_torque > self.meta["torque_max"]:
                clipped_features.add("torque_nm")
            target_torque = float(np.clip(raw_torque, self.meta["torque_min"], self.meta["torque_max"]))
            used_signals.append("spindle_load_pct")
        else:
            target_torque = np.nan
            missing_signals.append("spindle_load_pct")

        # 3. Tool wear mapping
        rated_tool_life_h = context.rated_tool_life_h or 60.0
        if readings.tool_hours is not None:
            raw_wear_fraction = readings.tool_hours / rated_tool_life_h
            if not 0.0 <= raw_wear_fraction <= 1.2:
                clipped_features.add("tool_wear_min")
            wear_fraction = float(np.clip(raw_wear_fraction, 0.0, 1.2))
            target_wear = wear_fraction * float(self.meta["max_tool_wear"])
            used_signals.append("tool_hours")
        else:
            target_wear = np.nan
            missing_signals.append("tool_hours")
        if context.rated_tool_life_h is None:
            assumptions.append("rated tool life defaulted to 60 hours")
            defaulted_features.add("tool_wear_min")

        # 4. Temperature mapping
        if readings.ambient_temp_c is not None:
            air_temp_k = readings.ambient_temp_c + 273.15
            used_signals.append("ambient_temp_c")
        else:
            air_temp_k = float(self.meta["air_temp_mean"])
            assumptions.append("ambient temperature defaulted from AI4I training mean")
            defaulted_features.add("air_temp_k")

        if readings.temp_c is not None:
            process_temp_k = readings.temp_c + 273.15
            used_signals.append("temp_c")
        else:
            process_temp_k = air_temp_k + float(self.meta["temp_diff_mean"]) if not np.isnan(air_temp_k) else np.nan
            if readings.ambient_temp_c is not None:
                missing_signals.append("temp_c")
            defaulted_features.update({"process_temp_k", "temp_diff_k"})
        if readings.ambient_temp_c is None:
            defaulted_features.add("air_temp_k")
        if readings.temp_c is None and readings.ambient_temp_c is None:
            defaulted_features.add("process_temp_k")
            defaulted_features.add("temp_diff_k")

        # Compute engineered features
        engineered = compute_engineered_features(
            air_temp_k=air_temp_k,
            process_temp_k=process_temp_k,
            rpm=target_rpm,
            torque_nm=target_torque,
            tool_wear_min=target_wear,
            machine_type=machine_type,
        )

        # Assemble and check bounds / clipping
        bounds = self.meta.get("feature_bounds", {})
        row: list[float] = []
        used_feature_count = 0
        for col in FEATURE_COLUMNS:
            val = float(engineered[col])
            if not np.isnan(val):
                used_feature_count += 1
            if not np.isnan(val) and col in bounds:
                low, high = bounds[col]
                if val < low or val > high:
                    clipped_features.add(col)
                    val = float(np.clip(val, low, high))
            row.append(val)

        feature_vector = np.array(row, dtype=np.float32)

        # OOD assessment counts clipped and defaulted model features.
        ood_warning = False
        confidence = Confidence.high
        if used_feature_count > 0:
            degraded_fraction = len(clipped_features | defaulted_features) / len(FEATURE_COLUMNS)
            if degraded_fraction > 0.40 or len(used_signals) < 2:
                ood_warning = True
                confidence = Confidence.low
            elif degraded_fraction > 0.20:
                confidence = Confidence.medium

        return feature_vector, used_signals, missing_signals, assumptions, ood_warning, confidence
