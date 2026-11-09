"""Train the failure-probability model on the AI4I 2020 Predictive Maintenance dataset.

Usage (from backend/):
    python -m ml.train_risk_model --data path/to/ai4i2020.csv [--out ml/artifacts]

Steps:
  1. Load the CSV, build the 8 model features (Type one-hot + 5 physical values).
     UDI, Product ID and the failure-mode flags TWF/HDF/PWF/OSF/RNF are NOT used: the flags say
     which kind of failure happened, so they would leak the target.
  2. Stratified split 60/20/20 (train/validation/test), fixed seed, so every run is identical.
  3. XGBoost with scale_pos_weight = negatives/positives (failures are only ~3% of rows).
  4. Isotonic calibration fitted on the validation split (the model is not refitted).
  5. Threshold: the one with the best F1 on the validation split.
  6. Report on the untouched test split: ROC-AUC, PR-AUC, Brier (raw vs calibrated), confusion
     matrix at the threshold. Accuracy is deliberately not the headline metric: predicting
     "never fails" would already be ~97% accurate.
"""

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from app.modules.machine.risk_model import (
    CALIBRATOR_FILE,
    CSV_COLUMNS,
    FEATURES_FILE,
    LEAKAGE_COLUMNS,
    METRICS_FILE,
    MODEL_FEATURES,
    MODEL_FILE,
    TARGET_COLUMN,
)

SEED = 42
XGB_PARAMS = {
    "n_estimators": 300,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "eval_metric": "aucpr",
    "random_state": SEED,
    "n_jobs": 1,  # deterministic results
}


def build_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """AI4I rows -> exactly MODEL_FEATURES, in that order. Leakage columns are dropped explicitly."""
    features = df.rename(columns=CSV_COLUMNS)
    for letter in ("L", "M", "H"):
        features[f"type_{letter}"] = (df["Type"] == letter).astype(int)
    features = features[MODEL_FEATURES].astype(float)
    leaked = set(features.columns) & set(LEAKAGE_COLUMNS)
    if leaked:
        raise ValueError(f"leakage columns in features: {sorted(leaked)}")
    return features


def split(x: pd.DataFrame, y: pd.Series):
    """60% train, 20% validation, 20% test, stratified by the target."""
    x_train, x_rest, y_train, y_rest = train_test_split(x, y, test_size=0.4, stratify=y, random_state=SEED)
    x_val, x_test, y_val, y_test = train_test_split(
        x_rest, y_rest, test_size=0.5, stratify=y_rest, random_state=SEED
    )
    return x_train, x_val, x_test, y_train, y_val, y_test


def best_f1_threshold(y_true: np.ndarray, probabilities: np.ndarray) -> float:
    precision, recall, thresholds = precision_recall_curve(y_true, probabilities)
    f1 = 2 * precision * recall / np.maximum(precision + recall, 1e-12)
    return float(thresholds[int(np.argmax(f1[:-1]))])


def evaluate(y_test, raw, calibrated, threshold: float) -> dict:
    predicted = (calibrated >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, predicted, labels=[0, 1]).ravel()
    return {
        "roc_auc": round(float(roc_auc_score(y_test, calibrated)), 4),
        "pr_auc": round(float(average_precision_score(y_test, calibrated)), 4),
        "brier_raw": round(float(brier_score_loss(y_test, raw)), 5),
        "brier_calibrated": round(float(brier_score_loss(y_test, calibrated)), 5),
        "threshold": round(threshold, 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "precision_at_threshold": round(float(tp / max(tp + fp, 1)), 4),
        "recall_at_threshold": round(float(tp / max(tp + fn, 1)), 4),
    }


def train(data_path: Path, out_dir: Path) -> dict:
    raw_bytes = data_path.read_bytes()
    df = pd.read_csv(data_path, encoding="utf-8-sig")  # the UCI file starts with a BOM
    x, y = build_feature_frame(df), df[TARGET_COLUMN].astype(int)
    x_train, x_val, x_test, y_train, y_val, y_test = split(x, y)

    positives = int(y_train.sum())
    scale_pos_weight = (len(y_train) - positives) / positives
    model = XGBClassifier(**XGB_PARAMS, scale_pos_weight=scale_pos_weight)
    model.fit(x_train.to_numpy(), y_train.to_numpy())

    raw_val = model.predict_proba(x_val.to_numpy())[:, 1]
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(raw_val, y_val)
    threshold = best_f1_threshold(y_val.to_numpy(), calibrator.predict(raw_val))

    raw_test = model.predict_proba(x_test.to_numpy())[:, 1]
    test_metrics = evaluate(y_test.to_numpy(), raw_test, calibrator.predict(raw_test), threshold)

    model_version = f"xgb-ai4i-{hashlib.sha256(raw_bytes).hexdigest()[:8]}"
    manifest = {
        "model_version": model_version,
        "features": MODEL_FEATURES,
        "training_ranges": {name: [float(x[name].min()), float(x[name].max())] for name in MODEL_FEATURES},
    }
    metrics = {
        "model_version": model_version,
        "dataset": {
            "rows": len(df),
            "failure_rate": round(float(y.mean()), 4),
            "sha256_prefix": model_version[-8:],
        },
        "split": {"train": len(y_train), "validation": len(y_val), "test": len(y_test), "seed": SEED},
        "params": {**XGB_PARAMS, "scale_pos_weight": round(scale_pos_weight, 3)},
        "features": MODEL_FEATURES,
        "excluded_columns": list(LEAKAGE_COLUMNS),
        "test": test_metrics,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_model(out_dir / MODEL_FILE)
    joblib.dump(calibrator, out_dir / CALIBRATOR_FILE)
    (out_dir / FEATURES_FILE).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out_dir / METRICS_FILE).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the Fibo risk model on AI4I 2020.")
    parser.add_argument("--data", type=Path, required=True, help="path to ai4i2020.csv")
    parser.add_argument("--out", type=Path, default=Path("ml/artifacts"), help="output folder")
    args = parser.parse_args()
    metrics = train(args.data, args.out)
    print(json.dumps(metrics["test"], indent=2))
    print(f"Artifacts written to {args.out} (model_version={metrics['model_version']})")


if __name__ == "__main__":
    main()
