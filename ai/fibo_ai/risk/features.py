"""Feature engineering and augmentation for the risk failure model."""

import numpy as np
import pandas as pd
from numpy.typing import NDArray

TYPE_MAPPING = {"L": 0, "M": 1, "H": 2}

FEATURE_COLUMNS = [
    "air_temp_k",
    "process_temp_k",
    "temp_diff_k",
    "rotational_speed_rpm",
    "torque_nm",
    "tool_wear_min",
    "power_w",
    "wear_torque",
    "load_per_krpm",
    "type_code",
]


def compute_engineered_features(
    air_temp_k: float | NDArray[np.float64],
    process_temp_k: float | NDArray[np.float64],
    rpm: float | NDArray[np.float64],
    torque_nm: float | NDArray[np.float64],
    tool_wear_min: float | NDArray[np.float64],
    machine_type: str | NDArray[np.str_] = "M",
) -> dict[str, float | int | NDArray[np.float64] | NDArray[np.int64]]:
    """Compute deterministic physics features used in training and inference."""
    temp_diff_k = process_temp_k - air_temp_k
    power_w = torque_nm * rpm * (2.0 * np.pi / 60.0)
    wear_torque = tool_wear_min * torque_nm
    # Avoid zero division
    rpm_safe = np.where(rpm > 0, rpm, 1.0) if isinstance(rpm, np.ndarray) else (rpm if rpm > 0 else 1.0)
    load_per_krpm = torque_nm / (rpm_safe / 1000.0)

    type_code: int | NDArray[np.int64]
    if isinstance(machine_type, np.ndarray) or isinstance(machine_type, pd.Series):
        type_code = np.array([TYPE_MAPPING.get(t, 1) for t in machine_type])
    else:
        type_code = TYPE_MAPPING.get(str(machine_type), 1)

    return {
        "air_temp_k": air_temp_k,
        "process_temp_k": process_temp_k,
        "temp_diff_k": temp_diff_k,
        "rotational_speed_rpm": rpm,
        "torque_nm": torque_nm,
        "tool_wear_min": tool_wear_min,
        "power_w": power_w,
        "wear_torque": wear_torque,
        "load_per_krpm": load_per_krpm,
        "type_code": type_code,
    }


def prepare_ai4i_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Extract features, target, and failure modes from AI4I raw dataframe without data leakage."""
    air_temp = df["Air temperature [K]"].values
    process_temp = df["Process temperature [K]"].values
    rpm = df["Rotational speed [rpm]"].values
    torque = df["Torque [Nm]"].values
    wear = df["Tool wear [min]"].values
    m_type = df["Type"].values

    features_dict = compute_engineered_features(air_temp, process_temp, rpm, torque, wear, m_type)
    X = pd.DataFrame(features_dict)[FEATURE_COLUMNS]
    y = df["Machine failure"].copy()

    # Evaluation breakdown columns (never used as features)
    mode_cols = [c for c in ["TWF", "HDF", "PWF", "OSF", "RNF"] if c in df.columns]
    failure_modes = df[mode_cols].copy()

    return X, y, failure_modes


def apply_feature_masking(
    X: NDArray[np.float64],
    mask_prob_range: tuple[float, float] = (0.1, 0.4),
    seed: int | None = 42,
) -> NDArray[np.float64]:
    """Randomly mask feature subsets with NaN to train missing-data robustness."""
    rng = np.random.default_rng(seed)
    X_masked = X.copy()
    n_samples, n_features = X_masked.shape

    # For each sample, draw random missing probability p in mask_prob_range
    probs = rng.uniform(mask_prob_range[0], mask_prob_range[1], size=n_samples)
    for i in range(n_samples):
        mask = rng.random(size=n_features) < probs[i]
        # Never mask all features
        if np.all(mask):
            mask[rng.integers(0, n_features)] = False
        X_masked[i, mask] = np.nan

    return X_masked
