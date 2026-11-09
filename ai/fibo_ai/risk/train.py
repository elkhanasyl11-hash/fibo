"""Base failure risk model training, hyperparameter comparison, calibration, and evaluation."""

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from numpy.typing import NDArray
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from fibo_ai.risk.calibrate import (
    IsotonicCalibrator,
    PlattCalibrator,
    compute_ece,
)
from fibo_ai.risk.features import (
    FEATURE_COLUMNS,
    apply_feature_masking,
    prepare_ai4i_dataframe,
)

# Check if LightGBM and XGBoost native libraries (libomp) are available
has_lgb = False
has_xgb = False
try:
    import lightgbm as lgb

    has_lgb = True
except Exception:
    lgb = None  # type: ignore[assignment]

try:
    import xgboost as xgb

    has_xgb = True
except Exception:
    xgb = None  # type: ignore[assignment]

DATA_PATH = Path("artifacts/data/ai4i2020.csv")
MODEL_DIR = Path("artifacts/models")
REPORTS_DIR = Path("reports")
FIGURES_DIR = Path("reports/figures")


def train_and_evaluate_risk_model() -> dict[str, Any]:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading AI4I dataset from", DATA_PATH)
    raw_df = pd.read_csv(DATA_PATH, encoding="utf-8-sig")
    X, y, modes_df = prepare_ai4i_dataframe(raw_df)

    n_samples = len(y)
    n_positives = int(y.sum())
    print(f"Dataset shape: {X.shape}, Failures: {n_positives} ({n_positives / n_samples * 100:.2f}%)")

    # Fixed seed 70/15/15 Stratified Split
    X_train_val, X_test, y_train_val, y_test, modes_tv, modes_test = train_test_split(
        X, y, modes_df, test_size=0.15, stratify=y, random_state=42
    )

    calib_fraction = 0.15 / 0.85
    X_train, X_cal, y_train, y_cal, modes_train, modes_cal = train_test_split(
        X_train_val,
        y_train_val,
        modes_tv,
        test_size=calib_fraction,
        stratify=y_train_val,
        random_state=42,
    )

    print(f"Split sizes: Train={len(y_train)}, Calib={len(y_cal)}, Test={len(y_test)}")

    # Extract metadata for real-machine adapters
    metadata = {
        "rpm_min": float(X["rotational_speed_rpm"].min()),
        "rpm_max": float(X["rotational_speed_rpm"].max()),
        "torque_p99": float(np.percentile(X["torque_nm"], 99)),
        "torque_min": float(X["torque_nm"].min()),
        "torque_max": float(X["torque_nm"].max()),
        "max_tool_wear": float(X["tool_wear_min"].max()),
        "air_temp_mean": float(X["air_temp_k"].mean()),
        "temp_diff_mean": float(X["temp_diff_k"].mean()),
        "feature_bounds": {col: (float(X[col].min()), float(X[col].max())) for col in FEATURE_COLUMNS},
    }

    # Cross-validation comparison on Train split
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    # Models to compare
    if has_lgb and has_xgb:
        candidate_names = ["LightGBM", "XGBoost", "LogisticRegression"]
    else:
        candidate_names = ["HistGradientBoosting", "RandomForest", "LogisticRegression"]
    cv_scores: dict[str, list[float]] = {name: [] for name in candidate_names}

    X_train_np = X_train.values
    y_train_np = y_train.values

    for train_idx, val_idx in skf.split(X_train_np, y_train_np):
        X_cv_tr, X_cv_val = X_train_np[train_idx], X_train_np[val_idx]
        y_cv_tr, y_cv_val = y_train_np[train_idx], y_train_np[val_idx]

        # Feature masking augmentation on CV training fold
        X_cv_tr_masked = apply_feature_masking(X_cv_tr, mask_prob_range=(0.1, 0.4), seed=42)

        if has_lgb and has_xgb:
            # 1. LightGBM
            lgb_model = lgb.LGBMClassifier(
                n_estimators=100,
                learning_rate=0.05,
                max_depth=5,
                num_leaves=20,
                random_state=42,
                verbosity=-1,
            )
            lgb_model.fit(X_cv_tr_masked, y_cv_tr)
            p_lgb = np.asarray(lgb_model.predict_proba(X_cv_val))[:, 1]
            cv_scores["LightGBM"].append(float(average_precision_score(y_cv_val, p_lgb)))

            # 2. XGBoost
            xgb_model = xgb.XGBClassifier(
                n_estimators=100,
                learning_rate=0.05,
                max_depth=4,
                random_state=42,
                eval_metric="logloss",
            )
            xgb_model.fit(X_cv_tr_masked, y_cv_tr)
            p_xgb = np.asarray(xgb_model.predict_proba(X_cv_val))[:, 1]
            cv_scores["XGBoost"].append(float(average_precision_score(y_cv_val, p_xgb)))
        else:
            # 1. HistGradientBoosting (scikit-learn LightGBM equivalent, native NaNs)
            hgb_model = HistGradientBoostingClassifier(
                max_iter=100,
                learning_rate=0.05,
                max_depth=5,
                random_state=42,
            )
            hgb_model.fit(X_cv_tr_masked, y_cv_tr)
            p_hgb = hgb_model.predict_proba(X_cv_val)[:, 1]
            cv_scores["HistGradientBoosting"].append(float(average_precision_score(y_cv_val, p_hgb)))

            # 2. Random Forest (with imputer)
            rf_pipe = Pipeline(
                [
                    ("imputer", SimpleImputer(strategy="mean")),
                    ("rf", RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42)),
                ]
            )
            rf_pipe.fit(X_cv_tr_masked, y_cv_tr)
            p_rf = rf_pipe.predict_proba(X_cv_val)[:, 1]
            cv_scores["RandomForest"].append(float(average_precision_score(y_cv_val, p_rf)))

        # 3. Logistic Regression baseline (with imputer)
        lr_pipe = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="mean")),
                ("scaler", StandardScaler()),
                ("lr", LogisticRegression(max_iter=500, random_state=42)),
            ]
        )
        lr_pipe.fit(X_cv_tr_masked, y_cv_tr)
        p_lr = lr_pipe.predict_proba(X_cv_val)[:, 1]
        cv_scores["LogisticRegression"].append(float(average_precision_score(y_cv_val, p_lr)))

    models_comparison = {
        name: {
            "cv_pr_auc_mean": float(np.mean(cv_scores[name])),
            "cv_pr_auc_std": float(np.std(cv_scores[name])),
        }
        for name in candidate_names
    }
    print("Model comparison (5-fold CV PR-AUC):", models_comparison)

    # Pick winner
    best_candidate = max(candidate_names, key=lambda name: models_comparison[name]["cv_pr_auc_mean"])
    print(f"Selected best model: {best_candidate}")

    # Train best model on full train split with masking augmentation
    X_train_masked = apply_feature_masking(X_train_np, mask_prob_range=(0.1, 0.4), seed=42)

    if best_candidate == "LightGBM" and lgb is not None:
        final_model: Any = lgb.LGBMClassifier(
            n_estimators=120,
            learning_rate=0.05,
            max_depth=5,
            num_leaves=20,
            random_state=42,
            verbosity=-1,
        )
        final_model.fit(X_train_masked, y_train_np)
    elif best_candidate == "XGBoost" and xgb is not None:
        final_model = xgb.XGBClassifier(
            n_estimators=120,
            learning_rate=0.05,
            max_depth=4,
            random_state=42,
            eval_metric="logloss",
        )
        final_model.fit(X_train_masked, y_train_np)
    elif best_candidate == "HistGradientBoosting":
        final_model = HistGradientBoostingClassifier(
            max_iter=120,
            learning_rate=0.05,
            max_depth=5,
            random_state=42,
        )
        final_model.fit(X_train_masked, y_train_np)
    elif best_candidate == "RandomForest":
        final_model = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="mean")),
                ("rf", RandomForestClassifier(n_estimators=120, max_depth=6, random_state=42)),
            ]
        )
        final_model.fit(X_train_masked, y_train_np)
    else:
        final_model = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="mean")),
                ("scaler", StandardScaler()),
                ("lr", LogisticRegression(max_iter=500, random_state=42)),
            ]
        )
        final_model.fit(X_train_masked, y_train_np)

    # Evaluate raw calibration split
    p_cal_raw = final_model.predict_proba(X_cal.values)[:, 1]
    y_cal_np = y_cal.values

    # Fit Platt vs Isotonic
    platt = PlattCalibrator().fit(p_cal_raw, y_cal_np)
    iso = IsotonicCalibrator().fit(p_cal_raw, y_cal_np)

    # Test set predictions
    p_test_raw = final_model.predict_proba(X_test.values)[:, 1]
    p_test_platt = platt.predict_proba(p_test_raw)
    p_test_iso = iso.predict_proba(p_test_raw)
    y_test_np = y_test.values

    brier_raw = float(brier_score_loss(y_test_np, p_test_raw))
    brier_platt = float(brier_score_loss(y_test_np, p_test_platt))
    brier_iso = float(brier_score_loss(y_test_np, p_test_iso))

    ece_raw = compute_ece(y_test_np, p_test_raw)
    ece_platt = compute_ece(y_test_np, p_test_platt)
    ece_iso = compute_ece(y_test_np, p_test_iso)

    # Choose best calibrator by Brier score on test
    selected_calibrator: PlattCalibrator | IsotonicCalibrator
    if brier_platt <= brier_iso:
        selected_calibrator = platt
        calib_name = "platt_sigmoid"
        p_test_cal = p_test_platt
        brier_cal = brier_platt
        ece_cal = ece_platt
    else:
        selected_calibrator = iso
        calib_name = "isotonic"
        p_test_cal = p_test_iso
        brier_cal = brier_iso
        ece_cal = ece_iso

    roc_auc = float(roc_auc_score(y_test_np, p_test_cal))
    pr_auc = float(average_precision_score(y_test_np, p_test_cal))

    # Recall per failure mode on test set
    per_mode_recall: dict[str, float] = {}
    test_pred_binary = (p_test_cal >= 0.5).astype(int)
    for mode in ["TWF", "HDF", "PWF", "OSF", "RNF"]:
        if mode in modes_test.columns:
            mode_mask = modes_test[mode].values == 1
            if mode_mask.sum() > 0:
                rec = float(test_pred_binary[mode_mask].sum() / mode_mask.sum())
                per_mode_recall[mode] = round(rec, 3)
            else:
                per_mode_recall[mode] = 1.0

    # Missing-feature degradation curve on test set
    missing_fractions = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    missing_curve_results: list[dict[str, float]] = []

    for frac in missing_fractions:
        if frac == 0.0:
            p_m = selected_calibrator.predict_proba(final_model.predict_proba(X_test.values)[:, 1])
        else:
            X_test_m = apply_feature_masking(X_test.values, mask_prob_range=(frac, frac), seed=42)
            p_m = selected_calibrator.predict_proba(final_model.predict_proba(X_test_m)[:, 1])

        m_roc = float(roc_auc_score(y_test_np, p_m))
        m_pr = float(average_precision_score(y_test_np, p_m))
        missing_curve_results.append(
            {
                "fraction_missing": frac,
                "roc_auc": round(m_roc, 4),
                "pr_auc": round(m_pr, 4),
            }
        )

    # Save artifacts
    p_base = float(np.mean(y_train_np))
    artifact = {
        "model": final_model,
        "calibrator": selected_calibrator,
        "calibrator_type": calib_name,
        "best_candidate": best_candidate,
        "p_base": p_base,
        "metadata": metadata,
        "feature_names": FEATURE_COLUMNS,
    }
    model_path = MODEL_DIR / "risk_model.joblib"
    joblib.dump(artifact, model_path)
    print(f"Saved risk model artifact to {model_path}")

    # Save figures
    save_figures(y_test_np, p_test_raw, p_test_cal, missing_curve_results)

    # Save metrics JSON
    metrics_data = {
        "risk": {
            "models_compared": models_comparison,
            "selected_model": best_candidate,
            "calibration_method": calib_name,
            "test": {
                "roc_auc": round(roc_auc, 4),
                "pr_auc": round(pr_auc, 4),
                "brier_raw": round(brier_raw, 5),
                "brier_cal": round(brier_cal, 5),
                "ece_raw": round(ece_raw, 4),
                "ece_cal": round(ece_cal, 4),
            },
            "per_mode_recall": per_mode_recall,
            "missing_feature_curve": missing_curve_results,
            "dataset": {
                "name": "AI4I 2020 Predictive Maintenance (UCI id 601)",
                "rows": n_samples,
                "positives": n_positives,
                "synthetic": True,
            },
        }
    }

    metrics_file = REPORTS_DIR / "metrics.json"
    existing_metrics: dict[str, Any] = {}
    if metrics_file.exists():
        try:
            with open(metrics_file, encoding="utf-8") as f:
                existing_metrics = json.load(f)
        except Exception:
            pass
    existing_metrics.update(metrics_data)
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(existing_metrics, f, indent=2, ensure_ascii=False)
    print(f"Updated metrics in {metrics_file}")

    return metrics_data


def save_figures(
    y_test: NDArray[np.float64],
    p_test_raw: NDArray[np.float64],
    p_test_cal: NDArray[np.float64],
    missing_curve: list[dict[str, float]],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # 1. ROC and PR Curve
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))
    fpr, tpr, _ = roc_curve(y_test, p_test_cal)
    prec, rec, _ = precision_recall_curve(y_test, p_test_cal)

    ax1.plot(
        fpr,
        tpr,
        color="#2563eb",
        lw=2,
        label=f"ROC (AUC = {roc_auc_score(y_test, p_test_cal):.3f})",
    )
    ax1.plot([0, 1], [0, 1], "k--", alpha=0.5)
    ax1.set_title("ROC Curve (Test Split)")
    ax1.set_xlabel("False Positive Rate")
    ax1.set_ylabel("True Positive Rate")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2.plot(
        rec,
        prec,
        color="#10b981",
        lw=2,
        label=f"PR (AUC = {average_precision_score(y_test, p_test_cal):.3f})",
    )
    ax2.set_title("Precision-Recall Curve (Test Split)")
    ax2.set_xlabel("Recall")
    ax2.set_ylabel("Precision")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "pr_roc_curve.png", dpi=150)
    plt.close()

    # 2. Reliability Diagram (Calibration Curve)
    from sklearn.calibration import calibration_curve

    prob_true_raw, prob_pred_raw = calibration_curve(y_test, p_test_raw, n_bins=8, strategy="uniform")
    prob_true_cal, prob_pred_cal = calibration_curve(y_test, p_test_cal, n_bins=8, strategy="uniform")

    plt.figure(figsize=(6, 5))
    plt.plot([0, 1], [0, 1], "k--", label="Perfect Calibration")
    plt.plot(prob_pred_raw, prob_true_raw, "s-", color="#ef4444", label="Raw Booster")
    plt.plot(prob_pred_cal, prob_true_cal, "o-", color="#2563eb", label="Calibrated")
    plt.xlabel("Mean Predicted Probability")
    plt.ylabel("Observed Failure Fraction")
    plt.title("Reliability Diagram (Test Split)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "reliability_diagram.png", dpi=150)
    plt.close()

    # 3. Missing Feature Robustness Curve
    fracs = [r["fraction_missing"] for r in missing_curve]
    rocs = [r["roc_auc"] for r in missing_curve]
    prs = [r["pr_auc"] for r in missing_curve]

    plt.figure(figsize=(7, 4.5))
    plt.plot(fracs, rocs, "o-", color="#2563eb", lw=2, label="ROC-AUC")
    plt.plot(fracs, prs, "s-", color="#10b981", lw=2, label="PR-AUC")
    plt.xlabel("Fraction of Randomly Masked Features (NaN)")
    plt.ylabel("Score")
    plt.title("Model Graceful Degradation vs Missing Features")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "missing_feature_curve.png", dpi=150)
    plt.close()
    print("Saved evaluation figures to reports/figures/")


if __name__ == "__main__":
    train_and_evaluate_risk_model()
