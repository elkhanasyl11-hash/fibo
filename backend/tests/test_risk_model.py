"""Risk model: leakage guard, training pipeline, loading and prediction from the committed artifacts."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.modules.machine.risk_model import LEAKAGE_COLUMNS, MODEL_FEATURES, RiskModel
from ml.train_risk_model import build_feature_frame, train

ARTIFACTS = Path(__file__).resolve().parents[1] / "ml" / "artifacts"


def synthetic_ai4i(rows: int = 3000, seed: int = 0) -> pd.DataFrame:
    """A small AI4I-shaped table (same columns) where failures depend on torque x tool wear."""
    rng = np.random.default_rng(seed)
    torque = rng.normal(40, 10, rows).clip(3, 77)
    wear = rng.integers(0, 254, rows)
    air = rng.normal(300, 2, rows)
    fail = ((torque * wear > 11000) | (rng.random(rows) < 0.005)).astype(int)
    return pd.DataFrame(
        {
            "UDI": range(1, rows + 1),
            "Product ID": [f"M{i}" for i in range(rows)],
            "Type": rng.choice(["L", "M", "H"], rows, p=[0.6, 0.3, 0.1]),
            "Air temperature [K]": air,
            "Process temperature [K]": air + 10,
            "Rotational speed [rpm]": rng.normal(1500, 150, rows),
            "Torque [Nm]": torque,
            "Tool wear [min]": wear,
            "Machine failure": fail,
            "TWF": 0,
            "HDF": 0,
            "PWF": fail,
            "OSF": 0,
            "RNF": 0,
        }
    )


def test_no_leakage_column_is_a_feature():
    assert not set(MODEL_FEATURES) & set(LEAKAGE_COLUMNS)
    assert "Machine failure" not in MODEL_FEATURES


def test_feature_frame_drops_ids_and_failure_modes():
    frame = build_feature_frame(synthetic_ai4i(50))
    assert list(frame.columns) == MODEL_FEATURES
    assert (frame[["type_L", "type_M", "type_H"]].sum(axis=1) == 1).all()


def test_committed_artifacts_have_no_leakage_and_honest_metrics():
    manifest = json.loads((ARTIFACTS / "feature_list.json").read_text())
    metrics = json.loads((ARTIFACTS / "metrics.json").read_text())
    assert manifest["features"] == MODEL_FEATURES
    assert set(metrics["excluded_columns"]) == set(LEAKAGE_COLUMNS)
    assert {"roc_auc", "pr_auc", "brier_raw", "brier_calibrated", "confusion_matrix"} <= set(metrics["test"])
    assert "accuracy" not in metrics["test"]  # not a headline metric with ~3% failures
    assert metrics["test"]["roc_auc"] > 0.9


def test_training_pipeline_writes_artifacts(tmp_path):
    csv = tmp_path / "ai4i.csv"
    synthetic_ai4i().to_csv(csv, index=False, encoding="utf-8-sig")  # with BOM, like the UCI file
    metrics = train(csv, tmp_path / "out")
    for name in ("risk_model.json", "calibrator.joblib", "feature_list.json", "metrics.json"):
        assert (tmp_path / "out" / name).exists()
    assert metrics["split"] == {"train": 1800, "validation": 600, "test": 600, "seed": 42}
    assert metrics["test"]["roc_auc"] > 0.8
    assert RiskModel.load(tmp_path / "out").version == metrics["model_version"]


@pytest.fixture(scope="module")
def model() -> RiskModel:
    return RiskModel.load(ARTIFACTS)


def _features(torque: float, wear: float, machine_class: str = "M") -> dict:
    features = {f"type_{c}": float(c == machine_class) for c in "LMH"}
    features.update(
        air_temperature_k=298.0,
        process_temperature_k=309.0,
        rotational_speed_rpm=1500.0,
        torque_nm=torque,
        tool_wear_min=wear,
    )
    return features


def test_prediction_is_calibrated_probability_with_shap(model):
    worn = model.predict(_features(torque=65, wear=240))
    fresh = model.predict(_features(torque=30, wear=5))
    assert 0 <= fresh.probability < worn.probability <= 1
    names = [f["feature"] for f in worn.shap_factors]
    assert len(names) == 5 and "machine_class" not in names and "type_L" not in names  # class is fixed
    assert all(f["title_ru"] for f in worn.shap_factors)
    contributions = [abs(f["contribution"]) for f in worn.shap_factors]
    assert contributions == sorted(contributions, reverse=True)


def test_missing_artifacts_mean_index_only_mode(tmp_path):
    assert RiskModel.load_or_none(tmp_path) is None
