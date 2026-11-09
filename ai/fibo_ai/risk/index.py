"""Transparent Risk Index computation with exact additive decomposition."""

from pathlib import Path
from typing import Any

import numpy as np
import yaml

from fibo_ai.schemas.common import Confidence, RiskBand
from fibo_ai.schemas.risk import CoverageInfo, ExternalSignals, FactorContribution

DEFAULT_WEIGHTS = {
    "model": 0.40,
    "audio": 0.20,
    "pm_overdue": 0.15,
    "photo_wear": 0.10,
    "recent_failures": 0.10,
    "anomaly": 0.05,
}

DEFAULT_HALF_LIVES = {
    "audio": 3.0,
    "photo_wear": 7.0,
    "anomaly": 3.0,
    "model": 1.0,
}

DEFAULT_AUDIO_KNOTS = [
    [0.0, 0.0],
    [2.0, 0.15],
    [3.0, 0.60],
    [4.0, 1.0],
]

DEFAULT_PHOTO_WEAR_SCORES = {
    "none": 0.0,
    "slight": 0.25,
    "moderate": 0.60,
    "severe": 1.0,
}


def map_audio_z_to_signal(z: float, knots: list[list[float]] | None = None) -> float:
    """Piecewise-linear interpolation mapping audio z-score to [0, 1]."""
    if knots is None:
        knots = DEFAULT_AUDIO_KNOTS
    if z <= knots[0][0]:
        return float(knots[0][1])
    if z >= knots[-1][0]:
        return float(knots[-1][1])

    for i in range(len(knots) - 1):
        x0, y0 = knots[i]
        x1, y1 = knots[i + 1]
        if x0 <= z <= x1:
            t = (z - x0) / (x1 - x0)
            return float(y0 + t * (y1 - y0))
    return 1.0


class RiskIndexEngine:
    def __init__(self, config_path: Path | None = None) -> None:
        if config_path is None:
            config_path = Path("configs/risk_index.yaml")

        self.weights = DEFAULT_WEIGHTS.copy()
        self.half_lives = DEFAULT_HALF_LIVES.copy()
        self.audio_knots = DEFAULT_AUDIO_KNOTS.copy()
        self.photo_scores = DEFAULT_PHOTO_WEAR_SCORES.copy()

        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                data: dict[str, Any] = yaml.safe_load(f) or {}
                self.weights.update(data.get("weights", {}))
                self.half_lives.update(data.get("half_lives_days", {}))
                self.audio_knots = data.get("audio_knots", self.audio_knots)
                self.photo_scores.update(data.get("photo_wear_scores", {}))

    def compute_risk_index(
        self,
        p_model_cal: float,
        p_base: float,
        model_factors: list[FactorContribution],
        signals: ExternalSignals,
        pm_overdue_h: float = 0.0,
        pm_interval_h: float = 250.0,
        failures_30d: int = 0,
        anomaly_score: float | None = None,
        base_coverage: CoverageInfo | None = None,
        base_confidence: Confidence = Confidence.high,
        ood_warning: bool = False,
        model_available: bool = True,
    ) -> tuple[float, float, list[FactorContribution], CoverageInfo, Confidence, RiskBand]:
        """Compute composite risk index with exact additive decomposition: index = base_value + sum(contributions)."""
        active_signals: dict[str, float] = {}
        decayed_weights: dict[str, float] = {}
        stale_signals: list[str] = []
        used_signals: list[str] = list(base_coverage.used) if base_coverage else (["model"] if model_available else [])

        # 1. Trained model component (omitted for config-only industry profiles).
        if model_available:
            active_signals["model"] = p_model_cal
            decayed_weights["model"] = self.weights.get("model", 0.40)

        # 2. Audio component
        if signals.audio_z is not None:
            s_audio = map_audio_z_to_signal(signals.audio_z, self.audio_knots)
            active_signals["audio"] = s_audio
            decay = 2.0 ** (-max(0.0, signals.audio_age_days) / self.half_lives.get("audio", 3.0))
            if decay < 0.5:
                stale_signals.append("audio")
            decayed_weights["audio"] = self.weights.get("audio", 0.20) * decay
            used_signals.append("audio")

        # 3. PM overdue
        if pm_overdue_h > 0:
            interval = max(pm_interval_h, 1.0)
            s_pm = float(np.clip(pm_overdue_h / interval, 0.0, 1.0))
            active_signals["pm_overdue"] = s_pm
            decayed_weights["pm_overdue"] = self.weights.get("pm_overdue", 0.15)
            used_signals.append("pm_overdue")

        # 4. Photo wear
        if signals.photo_wear is not None:
            raw_photo = self.photo_scores.get(signals.photo_wear.lower(), 0.0)
            conf_scale = (
                1.0
                if signals.photo_wear_confidence == "high"
                else (0.75 if signals.photo_wear_confidence == "medium" else 0.5)
            )
            s_photo = raw_photo * conf_scale
            active_signals["photo_wear"] = s_photo
            decay = 2.0 ** (-max(0.0, signals.photo_age_days) / self.half_lives.get("photo_wear", 7.0))
            if decay < 0.5:
                stale_signals.append("photo_wear")
            decayed_weights["photo_wear"] = self.weights.get("photo_wear", 0.10) * decay
            used_signals.append("photo_wear")

        # 5. Recent failures in 30 days
        if failures_30d > 0:
            s_fail = float(np.clip(failures_30d / 3.0, 0.0, 1.0))
            active_signals["recent_failures"] = s_fail
            decayed_weights["recent_failures"] = self.weights.get("recent_failures", 0.10)
            used_signals.append("recent_failures")

        # 6. Isolation Forest Anomaly
        if anomaly_score is not None:
            active_signals["anomaly"] = float(np.clip(anomaly_score, 0.0, 1.0))
            decayed_weights["anomaly"] = self.weights.get("anomaly", 0.05)
            used_signals.append("anomaly")

        # Renormalize weights over present signals
        sum_weights = sum(decayed_weights.values())
        w_norm = {k: v / sum_weights for k, v in decayed_weights.items()} if sum_weights else {}

        # Exact additive decomposition:
        # base_value = w_model * p_base
        w_model = w_norm.get("model", 0.0)
        base_value = float(w_model * p_base)

        all_factors: list[FactorContribution] = []

        # Scale model factors to w_model
        # sum(model_factors) == w_model * (p_model_cal - p_base)
        delta_p = p_model_cal - p_base if model_available else 0.0
        if model_available and model_factors:
            total_current_model_factors = sum(f.contribution for f in model_factors)
            scale = (
                (w_model * delta_p) / total_current_model_factors if abs(total_current_model_factors) > 1e-9 else 1.0
            )
            for mf in model_factors:
                all_factors.append(
                    FactorContribution(
                        name=mf.name,
                        label_ru=mf.label_ru,
                        label_kk=mf.label_kk,
                        value=mf.value,
                        contribution=round(float(mf.contribution * scale), 6),
                        direction=mf.direction,
                    )
                )
        elif model_available and abs(delta_p) > 1e-9:
            all_factors.append(
                FactorContribution(
                    name="model",
                    label_ru="Базовая модель риска поломки",
                    label_kk="Істен шығу қаупінің базалық моделі",
                    value=round(p_model_cal, 4),
                    contribution=round(float(w_model * delta_p), 6),
                    direction="increases_risk" if delta_p > 0 else "decreases_risk",
                )
            )

        # External signal contributions
        labels_map = {
            "audio": ("Отклонение звука от нормы станка", "Дыбыстың станок нормасынан ауытқуы"),
            "pm_overdue": ("Просрочка планового ТО", "Жоспарлы ТҚК мерзімінің өтуі"),
            "photo_wear": ("Износ инструмента по фото", "Фото бойынша құралдың тозуы"),
            "recent_failures": ("Частые инциденты за 30 дней", "Соңғы 30 күндегі жиі ақаулар"),
            "anomaly": (
                "Аномалия показаний (Isolation Forest)",
                "Көрсеткіштер аномалиясы (Isolation Forest)",
            ),
        }

        for sig_name, sig_val in active_signals.items():
            if sig_name == "model":
                continue
            contrib = float(w_norm[sig_name] * sig_val)
            lbl_ru, lbl_kk = labels_map.get(sig_name, (sig_name, sig_name))
            val_repr: float | str = sig_val
            if sig_name == "audio" and signals.audio_z is not None:
                val_repr = f"+{signals.audio_z:.1f}σ"
            elif sig_name == "pm_overdue":
                val_repr = f"{pm_overdue_h:.0f} ч"

            all_factors.append(
                FactorContribution(
                    name=sig_name,
                    label_ru=lbl_ru,
                    label_kk=lbl_kk,
                    value=val_repr,
                    contribution=round(contrib, 6),
                    direction="increases_risk" if contrib > 0.01 else "neutral",
                )
            )

        # Sum up raw index from base_value + sum(contributions)
        raw_index = base_value + sum(f.contribution for f in all_factors)

        # Hard rules floor check
        rule_floor_contribution = 0.0
        if signals.audio_z is not None and signals.audio_z >= 3.0:
            # Critical audio floor: index must be at least 0.70
            floor = 0.70
            if raw_index < floor:
                rule_floor_contribution = float(floor - raw_index)
                raw_index = floor
                all_factors.append(
                    FactorContribution(
                        name="rule_floor",
                        label_ru="Обязательное правило: критическое отклонение звука",
                        label_kk="Міндетті ереже: дыбыстың сыни ауытқуы",
                        value=f"+{signals.audio_z:.1f}σ >= 3.0σ",
                        contribution=round(rule_floor_contribution, 6),
                        direction="increases_risk",
                    )
                )

        index = float(np.clip(raw_index, 0.0, 1.0))
        band = RiskBand.high if index >= 0.70 else (RiskBand.medium if index >= 0.40 else RiskBand.low)

        coverage = CoverageInfo(
            used=used_signals,
            missing=base_coverage.missing if base_coverage else [],
            stale=stale_signals,
            assumptions_used=base_coverage.assumptions_used if base_coverage else [],
        )

        confidence = base_confidence
        if len(stale_signals) > 0 or ood_warning:
            if confidence == Confidence.high:
                confidence = Confidence.medium
            elif confidence == Confidence.medium:
                confidence = Confidence.low

        all_factors.sort(key=lambda f: abs(f.contribution), reverse=True)
        return index, base_value, all_factors, coverage, confidence, band
