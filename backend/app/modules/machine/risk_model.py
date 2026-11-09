"""Fibo Machine: the trained failure-probability model (XGBoost + isotonic calibration + SHAP).

What is in ml/artifacts/ (written by ml/train_risk_model.py):
  risk_model.json     XGBoost model, native JSON format
  calibrator.joblib   isotonic regression: raw XGBoost score -> calibrated probability
  feature_list.json   feature order, model_version, training value ranges
  metrics.json        test-set metrics (shown in the README)

Why calibration: XGBoost trained with scale_pos_weight (failures are ~3% of rows) outputs scores
that rank machines well but are too high to read as probabilities. Isotonic regression, fitted on
the validation split, maps them back to observed failure frequencies.

Why SHAP on the raw model: TreeExplainer explains the XGBoost output (log-odds), not the calibrated
probability. The calibrator is monotonic, so the direction of every factor is the same.

The model is loaded once at startup. If the files are missing the app runs in "index-only mode"
(risk index from the other signals). get_active_model() gives the loaded model to any code,
including background tasks that only receive IDs.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import shap
from xgboost import XGBClassifier

logger = logging.getLogger("fibo.machine.risk_model")

MODEL_FILE = "risk_model.json"
CALIBRATOR_FILE = "calibrator.joblib"
FEATURES_FILE = "feature_list.json"
METRICS_FILE = "metrics.json"

# AI4I 2020 CSV columns -> our feature names (XGBoost forbids "[" and "]" in feature names).
CSV_COLUMNS = {
    "Air temperature [K]": "air_temperature_k",
    "Process temperature [K]": "process_temperature_k",
    "Rotational speed [rpm]": "rotational_speed_rpm",
    "Torque [Nm]": "torque_nm",
    "Tool wear [min]": "tool_wear_min",
}
TYPE_COLUMNS = ["type_L", "type_M", "type_H"]  # one-hot of the product quality class L/M/H
MODEL_FEATURES = TYPE_COLUMNS + list(CSV_COLUMNS.values())
TARGET_COLUMN = "Machine failure"
# Never features: row ids, and the failure-mode flags that are just parts of the target.
LEAKAGE_COLUMNS = ("UDI", "Product ID", "TWF", "HDF", "PWF", "OSF", "RNF")

FEATURE_TITLES_RU = {
    "air_temperature_k": "Температура воздуха",
    "process_temperature_k": "Температура процесса",
    "rotational_speed_rpm": "Обороты шпинделя",
    "torque_nm": "Нагрузка шпинделя (момент)",
    "tool_wear_min": "Износ инструмента",
}


@dataclass
class ModelPrediction:
    probability: float  # calibrated
    raw_probability: float  # XGBoost output before calibration
    shap_factors: list[dict]  # every factor, sorted by |contribution|, largest first


class RiskModel:
    def __init__(self, model: XGBClassifier, calibrator, manifest: dict) -> None:
        self.model = model
        self.calibrator = calibrator
        self.features: list[str] = manifest["features"]
        self.version: str = manifest["model_version"]
        self.training_ranges: dict[str, list[float]] = manifest["training_ranges"]
        self.explainer = shap.TreeExplainer(model)

    @classmethod
    def load(cls, model_dir: Path) -> "RiskModel":
        manifest = json.loads((model_dir / FEATURES_FILE).read_text(encoding="utf-8"))
        if manifest["features"] != MODEL_FEATURES:
            raise ValueError(f"feature list in {FEATURES_FILE} does not match the code")
        model = XGBClassifier()
        model.load_model(model_dir / MODEL_FILE)
        calibrator = joblib.load(model_dir / CALIBRATOR_FILE)
        return cls(model, calibrator, manifest)

    @classmethod
    def load_or_none(cls, model_dir: Path) -> "RiskModel | None":
        """Return the loaded model, or None (index-only mode) if it cannot be loaded."""
        if not (model_dir / MODEL_FILE).exists():
            logger.warning(
                "risk model artifacts not found, running in index-only mode",
                extra={"model_dir": str(model_dir)},
            )
            return None
        try:
            model = cls.load(model_dir)
        except (OSError, ValueError, KeyError) as exc:
            logger.error("risk model could not be loaded, running in index-only mode", exc_info=exc)
            return None
        logger.info("risk model loaded", extra={"model_version": model.version})
        return model

    def predict(self, features: dict[str, float]) -> ModelPrediction:
        """Calibrated failure probability + SHAP factors for one machine. CPU work: call via to_thread."""
        row = np.array([[features[name] for name in self.features]], dtype=float)
        raw = float(self.model.predict_proba(row)[0, 1])
        calibrated = float(np.clip(self.calibrator.predict([raw])[0], 0.0, 1.0))
        contributions = self.explainer.shap_values(row)[0]
        return ModelPrediction(calibrated, raw, self._factors(features, contributions))

    def _factors(self, features: dict[str, float], contributions) -> list[dict]:
        by_name = dict(zip(self.features, (float(c) for c in contributions), strict=True))
        # The product class is the same fixed value for every machine (feature_map.FIXED_PRODUCT_CLASS),
        # so its contribution says nothing about this machine and is not shown.
        for col in TYPE_COLUMNS:
            by_name.pop(col)
        factors = []
        for name, contribution in by_name.items():
            factors.append({"feature": name, "value": round(features[name], 2), "contribution": contribution})
        for factor in factors:
            factor["title_ru"] = FEATURE_TITLES_RU[factor["feature"]]
            factor["contribution"] = round(factor["contribution"], 4)
        return sorted(factors, key=lambda f: abs(f["contribution"]), reverse=True)


_active_model: RiskModel | None = None


def set_active_model(model: RiskModel | None) -> None:
    """Called once at startup (app lifespan, demo seed)."""
    global _active_model
    _active_model = model


def get_active_model() -> RiskModel | None:
    """The model loaded at startup, or None in index-only mode."""
    return _active_model
