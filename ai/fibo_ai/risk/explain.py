"""Explainability module wrapping SHAP TreeExplainer and localized factor labels."""

from pathlib import Path
from typing import Any

import numpy as np
import shap
import yaml
from numpy.typing import NDArray

from fibo_ai.schemas.risk import FactorContribution


class RiskExplainer:
    def __init__(
        self,
        model: Any,
        feature_names: list[str],
        labels_config_path: Path | None = None,
    ) -> None:
        self.model = model
        self.feature_names = feature_names
        # TreeExplainer is cached at initialization
        self.explainer = shap.TreeExplainer(model)
        self.expected_value = (
            float(self.explainer.expected_value)
            if not isinstance(self.explainer.expected_value, np.ndarray)
            else float(self.explainer.expected_value[0])
        )

        if labels_config_path is None:
            labels_config_path = Path("configs/feature_labels.yaml")

        self.labels: dict[str, dict[str, str]] = {}
        if labels_config_path.exists():
            with open(labels_config_path, encoding="utf-8") as f:
                data: dict[str, Any] = yaml.safe_load(f) or {}
                self.labels = data.get("features", {})

    def explain(
        self,
        feature_vector: NDArray[np.float64],
        p_model_cal: float,
        p_base: float,
        model_weight: float,
    ) -> list[FactorContribution]:
        """Compute SHAP contributions and map them into additive risk index points."""
        # Reshape to (1, n_features)
        x_2d = feature_vector.reshape(1, -1)
        # TreeExplainer on LightGBM/XGBoost returns array of shape (1, n_features)
        shap_vals = self.explainer.shap_values(x_2d)
        if isinstance(shap_vals, list):
            # For some binary classifiers shap returns list of [class 0, class 1]
            raw_phi = np.array(shap_vals[1]).flatten()
        elif isinstance(shap_vals, np.ndarray) and len(shap_vals.shape) == 3:
            raw_phi = shap_vals[0, :, 1].flatten()
        else:
            raw_phi = np.array(shap_vals).flatten()

        sum_phi = float(np.sum(raw_phi))
        delta_p = p_model_cal - p_base
        total_model_contrib = model_weight * delta_p

        factors: list[FactorContribution] = []
        for i, feat_name in enumerate(self.feature_names):
            val = float(feature_vector[i])
            phi_i = float(raw_phi[i])

            # Decompose proportional to SHAP log-odds share
            if abs(sum_phi) > 1e-6:
                contrib_i = float(total_model_contrib * (phi_i / sum_phi))
            else:
                contrib_i = float(total_model_contrib / len(self.feature_names))

            lbl_dict = self.labels.get(feat_name, {})
            label_ru = lbl_dict.get("ru", feat_name)
            label_kk = lbl_dict.get("kk", feat_name)

            direction = "increases_risk" if contrib_i > 0 else ("decreases_risk" if contrib_i < 0 else "neutral")
            factors.append(
                FactorContribution(
                    name=feat_name,
                    label_ru=label_ru,
                    label_kk=label_kk,
                    value=round(val, 2) if not np.isnan(val) else None,
                    contribution=round(contrib_i, 5),
                    direction=direction,
                )
            )

        # Sort descending by contribution magnitude
        factors.sort(key=lambda f: abs(f.contribution), reverse=True)
        return factors
