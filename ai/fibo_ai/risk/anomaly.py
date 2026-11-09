"""Isolation Forest anomaly detection on machine readings history with robust z-score attribution."""

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from numpy.typing import NDArray
from sklearn.ensemble import IsolationForest

from fibo_ai.schemas.risk import MachineReadings

FEATURE_NAMES = ["rpm_norm", "load_pct", "temp_rise", "load_per_krpm"]


def extract_anomaly_features(readings: MachineReadings, rated_rpm: float = 4000.0) -> NDArray[np.float64]:
    """Extract standard 4-variable vector for anomaly detection."""
    rpm = readings.spindle_rpm if readings.spindle_rpm is not None else 1500.0
    rpm_norm = rpm / rated_rpm
    load = readings.spindle_load_pct if readings.spindle_load_pct is not None else 50.0

    temp = readings.temp_c if readings.temp_c is not None else 40.0
    ambient = readings.ambient_temp_c if readings.ambient_temp_c is not None else 25.0
    temp_rise = max(0.0, temp - ambient)

    rpm_safe = max(rpm, 100.0)
    load_per_krpm = load / (rpm_safe / 1000.0)

    return np.array([rpm_norm, load, temp_rise, load_per_krpm], dtype=np.float64)


class ReadingAnomalyDetector:
    def __init__(self, min_history: int = 30) -> None:
        self.min_history = min_history
        config_path = Path("configs/risk_index.yaml")
        self.threshold = 0.95
        if config_path.exists():
            with config_path.open(encoding="utf-8") as config_file:
                config = yaml.safe_load(config_file) or {}
            self.threshold = float(config.get("anomaly_threshold", self.threshold))
        self._cache: dict[
            str,
            tuple[IsolationForest, NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]],
        ] = {}

        # Global fallback is fit to the available AI4I training distribution.
        data_path = Path("artifacts/data/ai4i2020.csv")
        if data_path.exists():
            data = pd.read_csv(data_path, encoding="utf-8-sig")
            rpm = data["Rotational speed [rpm]"].to_numpy(dtype=np.float64)
            torque = data["Torque [Nm]"].to_numpy(dtype=np.float64)
            torque_p99 = float(np.percentile(torque, 99))
            temp_rise = data["Process temperature [K]"].to_numpy(dtype=np.float64) - data[
                "Air temperature [K]"
            ].to_numpy(dtype=np.float64)
            global_X = np.column_stack([rpm / 4000.0, torque / torque_p99 * 100.0, temp_rise, torque / (rpm / 1000.0)])
        else:
            rng = np.random.default_rng(42)
            n_synth = 500
            synth_rpm = rng.normal(1500, 150, size=n_synth).clip(1000, 2500) / 4000.0
            synth_load = rng.normal(55, 12, size=n_synth).clip(10, 95)
            synth_temp = rng.normal(15, 3, size=n_synth).clip(5, 30)
            synth_ratio = synth_load / (synth_rpm * 4.0)
            global_X = np.column_stack([synth_rpm, synth_load, synth_temp, synth_ratio])

        self.global_model = IsolationForest(contamination=0.05, random_state=42)
        self.global_model.fit(global_X)
        self.global_scores = -self.global_model.score_samples(global_X)
        self.global_medians = np.median(global_X, axis=0)
        self.global_mads = np.median(np.abs(global_X - self.global_medians), axis=0)
        self.global_mads = np.where(self.global_mads > 1e-6, self.global_mads, 1.0)

    def assess_reading(
        self,
        machine_id: str,
        latest: MachineReadings,
        history: list[MachineReadings] | None = None,
        rated_rpm: float = 4000.0,
    ) -> tuple[bool, float, str, list[dict[str, Any]]]:
        """Assess latest reading against history (or global baseline) and return score + attribution."""
        latest_vec = extract_anomaly_features(latest, rated_rpm)

        scope = "global"
        model = self.global_model
        baseline_scores = self.global_scores
        medians = self.global_medians
        mads = self.global_mads

        if history and len(history) >= self.min_history:
            hist_bytes = b"".join(str(r.model_dump()).encode("utf-8") for r in history)
            hist_hash = f"{machine_id}:{hashlib.md5(hist_bytes).hexdigest()}"

            if hist_hash in self._cache:
                model, baseline_scores, medians, mads = self._cache[hist_hash]
                scope = "machine"
            else:
                X_hist = np.array([extract_anomaly_features(r, rated_rpm) for r in history])
                local_model = IsolationForest(contamination=0.05, random_state=42)
                local_model.fit(X_hist)
                local_scores = -local_model.score_samples(X_hist)
                local_medians = np.median(X_hist, axis=0)
                local_mads = np.median(np.abs(X_hist - local_medians), axis=0)
                local_mads = np.where(local_mads > 1e-6, local_mads, 1.0)

                self._cache[hist_hash] = (local_model, local_scores, local_medians, local_mads)
                model, baseline_scores, medians, mads = (
                    local_model,
                    local_scores,
                    local_medians,
                    local_mads,
                )
                scope = "machine"

        # Raw anomaly score: higher = more anomalous
        raw_score = float(-model.score_samples(latest_vec.reshape(1, -1))[0])

        # Map to [0, 1] through empirical CDF of baseline scores
        score_cdf = float(np.mean(baseline_scores <= raw_score))
        is_anomaly = score_cdf >= self.threshold

        # Robust z-scores (median/MAD) for feature attribution
        robust_z = (latest_vec - medians) / (1.4826 * mads)
        top_features: list[dict[str, Any]] = []
        for name, z_val in zip(FEATURE_NAMES, robust_z, strict=False):
            top_features.append(
                {
                    "feature": name,
                    "robust_z": round(float(z_val), 2),
                    "deviation_direction": "high" if z_val > 0 else "low",
                }
            )
        top_features.sort(key=lambda x: abs(x["robust_z"]), reverse=True)

        return is_anomaly, round(score_cdf, 4), scope, top_features
