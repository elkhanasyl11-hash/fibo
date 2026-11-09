"""Production inference wrapper for failure risk model, SHAP explanations, and risk index."""

import uuid
from pathlib import Path
from typing import Any

import joblib

from fibo_ai.risk.adapters import MachineAdapter
from fibo_ai.risk.explain import RiskExplainer
from fibo_ai.risk.index import RiskIndexEngine
from fibo_ai.risk.priority import calculate_priority_kzt
from fibo_ai.schemas.common import Confidence, Profile, Usage
from fibo_ai.schemas.risk import AnomalySummary, CoverageInfo, RiskRequest, RiskResult
from fibo_ai.settings import Settings

MODEL_ARTIFACT_NAME = Path("models/risk_model.joblib")


class RiskPredictor:
    def __init__(self, settings: Settings, artifact_path: Path | None = None) -> None:
        self.settings = settings
        self.path = artifact_path or (Path(settings.fibo_data_dir) / MODEL_ARTIFACT_NAME)
        self.artifact: dict[str, Any] | None = None
        self.explainer: RiskExplainer | None = None
        self.adapter: MachineAdapter | None = None
        self.index_engine = RiskIndexEngine()
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self.artifact = joblib.load(self.path)
                if self.artifact:
                    model = self.artifact["model"]
                    feature_names = self.artifact["feature_names"]
                    self.explainer = RiskExplainer(model, feature_names)
                    self.adapter = MachineAdapter(self.artifact.get("metadata"))
                    return
            except Exception as e:
                print(f"Failed loading {self.path}: {e}")

        # Fallback adapter if model not yet trained
        self.adapter = MachineAdapter()

    def predict(self, req: RiskRequest, anomaly_summary: AnomalySummary | None = None) -> RiskResult:
        req_id = f"risk-{uuid.uuid4().hex[:8]}"

        # If not metalworking or model not loaded, use rule-based risk index
        is_metal = req.profile == Profile.metalworking
        is_batch = req.profile in [Profile.bakery, Profile.confectionery, Profile.dairy]

        if not self.artifact or not is_metal or not self.explainer or not self.adapter:
            # Config-based risk calculation without trained failure model
            p_model_raw = None
            p_model_cal = 0.0
            p_base = 0.0
            model_factors: list[Any] = []
            used: list[str] = []
            missing = ["model_metalworking"]
            assumptions = ["industry profile has no trained failure model; computed from maintenance signals"]
            ood_warning = False
            confidence = Confidence.medium
        else:
            feat_vec, used, missing, assumptions, ood_warning, confidence = self.adapter.adapt_readings(
                req.readings, req.context, machine_type="M"
            )
            model = self.artifact["model"]
            calibrator = self.artifact["calibrator"]
            p_base = float(self.artifact.get("p_base", 0.034))

            # Predict raw probability (LightGBM/XGBoost handles NaNs natively)
            p_raw_arr = model.predict_proba(feat_vec.reshape(1, -1))[:, 1]
            p_model_raw = float(p_raw_arr[0])
            p_cal_arr = calibrator.predict_proba(p_raw_arr)
            p_model_cal = float(p_cal_arr[0])

            # SHAP TreeExplainer
            model_factors = self.explainer.explain(
                feat_vec.astype("float64"),
                p_model_cal=p_model_cal,
                p_base=p_base,
                model_weight=0.40,
            )

        # PM overdue hours
        pm_overdue = 0.0
        if req.context.hours_since_last_pm and req.context.pm_interval_h:
            pm_overdue = max(0.0, req.context.hours_since_last_pm - req.context.pm_interval_h)

        anom_score = anomaly_summary.score if anomaly_summary else req.signals.recent_anomaly_score

        # Composite risk index with exact additive decomposition
        (
            risk_index,
            base_val,
            factors,
            coverage,
            final_conf,
            risk_band,
        ) = self.index_engine.compute_risk_index(
            p_model_cal=p_model_cal,
            p_base=p_base,
            model_factors=model_factors,
            signals=req.signals,
            pm_overdue_h=pm_overdue,
            pm_interval_h=req.context.pm_interval_h or 250.0,
            failures_30d=req.context.failures_30d,
            anomaly_score=anom_score,
            base_coverage=CoverageInfo(used=used, missing=missing, assumptions_used=assumptions),
            base_confidence=confidence,
            ood_warning=ood_warning,
            model_available=bool(self.artifact and is_metal),
        )

        # Append adapters assumptions
        if is_metal:
            coverage.assumptions_used.extend(assumptions)
            coverage.assumptions_used = list(set(coverage.assumptions_used))

        # Expected priority loss in KZT
        priority_kzt = calculate_priority_kzt(
            risk_index=risk_index,
            context=req.context,
            is_batch_profile=is_batch,
        )

        return RiskResult(
            request_id=req_id,
            model_version=self.settings.model_version,
            config_version=self.settings.config_version,
            machine_id=req.machine_id,
            risk_index=round(risk_index, 4),
            risk_band=risk_band,
            priority_kzt=priority_kzt,
            p_model_raw=round(p_model_raw, 4) if p_model_raw is not None else None,
            p_model_cal=round(p_model_cal, 4) if p_model_cal is not None else None,
            p_fail_next_cycle=round(p_model_cal, 4) if p_model_cal is not None else None,
            factors=factors,
            base_value=round(base_val, 6),
            anomaly=anomaly_summary,
            coverage=coverage,
            confidence=final_conf,
            ood_warning=ood_warning,
            usage=Usage(est_cost_usd=0.00005),
        )
