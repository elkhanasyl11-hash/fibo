"""Probability calibration and reliability evaluation."""

from typing import cast

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import brier_score_loss


def compute_ece(y_true: NDArray[np.float64], y_prob: NDArray[np.float64], n_bins: int = 10) -> float:
    """Compute Expected Calibration Error (ECE)."""
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(y_true)

    for i in range(n_bins):
        low, high = bin_edges[i], bin_edges[i + 1]
        # Include right edge in last bin
        if i == n_bins - 1:
            in_bin = (y_prob >= low) & (y_prob <= high)
        else:
            in_bin = (y_prob >= low) & (y_prob < high)

        bin_count = np.sum(in_bin)
        if bin_count > 0:
            bin_acc = np.mean(y_true[in_bin])
            bin_conf = np.mean(y_prob[in_bin])
            ece += (bin_count / n) * np.abs(bin_acc - bin_conf)

    return float(ece)


class PlattCalibrator:
    """Explicit Platt (logistic sigmoid) scaler fit on held-out validation predictions."""

    def __init__(self) -> None:
        self.a: float = 1.0
        self.b: float = 0.0

    def fit(self, y_prob_raw: NDArray[np.float64], y_true: NDArray[np.int64]) -> "PlattCalibrator":
        # Convert probs to logits with epsilon clipping
        eps = 1e-7
        p_clipped = np.clip(y_prob_raw, eps, 1.0 - eps)
        logits = np.log(p_clipped / (1.0 - p_clipped)).reshape(-1, 1)

        from sklearn.linear_model import LogisticRegression

        lr = LogisticRegression(C=1.0, solver="lbfgs")
        lr.fit(logits, y_true)
        self.a = float(lr.coef_[0][0])
        self.b = float(lr.intercept_[0])
        return self

    def predict_proba(self, y_prob_raw: NDArray[np.float64]) -> NDArray[np.float64]:
        eps = 1e-7
        p_clipped = np.clip(y_prob_raw, eps, 1.0 - eps)
        logits = np.log(p_clipped / (1.0 - p_clipped))
        calibrated_logits = self.a * logits + self.b
        return cast(NDArray[np.float64], 1.0 / (1.0 + np.exp(-calibrated_logits)))


class IsotonicCalibrator:
    """Isotonic regression calibrator fit on held-out validation predictions."""

    def __init__(self) -> None:
        from sklearn.isotonic import IsotonicRegression

        self.iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)

    def fit(self, y_prob_raw: NDArray[np.float64], y_true: NDArray[np.int64]) -> "IsotonicCalibrator":
        self.iso.fit(y_prob_raw, y_true)
        return self

    def predict_proba(self, y_prob_raw: NDArray[np.float64]) -> NDArray[np.float64]:
        return cast(NDArray[np.float64], np.asarray(self.iso.predict(y_prob_raw), dtype=np.float64))


def evaluate_calibration(
    y_true: NDArray[np.float64],
    y_prob_raw: NDArray[np.float64],
    y_prob_cal: NDArray[np.float64],
) -> dict[str, float]:
    """Compare raw vs calibrated predictions on Brier score and ECE."""
    return {
        "brier_raw": float(brier_score_loss(y_true, y_prob_raw)),
        "brier_cal": float(brier_score_loss(y_true, y_prob_cal)),
        "ece_raw": compute_ece(y_true, y_prob_raw),
        "ece_cal": compute_ece(y_true, y_prob_cal),
    }
