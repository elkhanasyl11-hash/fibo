from typing import Any

from pydantic import ConfigDict, Field

from fibo_ai.schemas.common import (
    BaseResponse,
    Confidence,
    FiboBaseModel,
    Profile,
    RiskBand,
)


class MachineContext(FiboBaseModel):
    rated_rpm: float | None = Field(None, description="Nominal spindle RPM rating")
    rated_torque_nm: float | None = Field(None, description="Nominal torque rating in Nm")
    rated_tool_life_h: float | None = Field(None, description="Expected cutter life in hours")
    criticality: str = Field("medium", description="Machine criticality: low, medium, high")
    expected_repair_hours: float = Field(4.0, description="Estimated repair duration in hours")
    cost_per_hour_kzt: int = Field(15000, description="Downtime cost per hour in KZT")
    batch_value_kzt: int | None = Field(None, description="Value of spoiled product batch in KZT")
    hours_since_last_pm: float | None = Field(None, description="Hours run since previous PM")
    pm_interval_h: float | None = Field(None, description="Recommended PM interval in hours")
    failures_30d: int = Field(0, description="Number of breakdown incidents in past 30 days")


class MachineReadings(FiboBaseModel):
    spindle_rpm: float | None = Field(None, description="Observed rotational speed in RPM")
    spindle_load_pct: float | None = Field(None, description="Spindle load percentage (0-150%)")
    temp_c: float | None = Field(None, description="Bearing/process temperature in Celsius")
    ambient_temp_c: float | None = Field(None, description="Ambient air temperature in Celsius")
    tool_hours: float | None = Field(None, description="Current tool cutting hours")
    runtime_h: float | None = Field(None, description="Total machine runtime hours")


class ExternalSignals(FiboBaseModel):
    audio_z: float | None = Field(None, description="Audio anomaly z-score")
    audio_age_days: float = Field(0.0, description="Days elapsed since audio recording")
    photo_wear: str | None = Field(None, description="Tool wear level: none, slight, moderate, severe")
    photo_wear_confidence: str = Field("medium", description="Confidence in photo wear verdict")
    photo_age_days: float = Field(0.0, description="Days elapsed since tool photo")
    voice_urgency: str | None = Field(None, description="Extracted voice urgency: low, medium, high")
    recent_anomaly_score: float | None = Field(None, description="Isolation forest score (0-1)")


class RiskRequest(FiboBaseModel):
    machine_id: str = Field(..., description="Unique machine identifier, e.g. 'cnc_lathe_02'")
    profile: Profile = Field(Profile.metalworking, description="Industry domain profile")
    readings: MachineReadings = Field(default_factory=lambda: MachineReadings())
    context: MachineContext = Field(default_factory=lambda: MachineContext())
    signals: ExternalSignals = Field(default_factory=lambda: ExternalSignals())

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "machine_id": "ЧПУ-2",
                "profile": "metalworking",
                "readings": {
                    "spindle_rpm": 3200.0,
                    "spindle_load_pct": 82.0,
                    "temp_c": 54.0,
                    "ambient_temp_c": 22.0,
                    "tool_hours": 58.0,
                },
                "context": {
                    "rated_rpm": 4000.0,
                    "rated_torque_nm": 60.0,
                    "rated_tool_life_h": 60.0,
                    "criticality": "high",
                    "expected_repair_hours": 5.0,
                    "cost_per_hour_kzt": 25000,
                    "hours_since_last_pm": 320.0,
                    "pm_interval_h": 250.0,
                    "failures_30d": 1,
                },
                "signals": {
                    "audio_z": 3.1,
                    "audio_age_days": 0.1,
                    "photo_wear": "moderate",
                    "photo_wear_confidence": "high",
                },
            }
        },
    )


class FactorContribution(FiboBaseModel):
    name: str = Field(..., description="Feature or signal identifier")
    label_ru: str = Field(..., description="Human-readable description in Russian")
    label_kk: str = Field(..., description="Human-readable description in Kazakh")
    value: float | str | None = Field(None, description="Actual observed feature value")
    contribution: float = Field(..., description="Contribution to risk index in index points")
    direction: str = Field("increases_risk", description="Direction: increases_risk or decreases_risk")


class CoverageInfo(FiboBaseModel):
    used: list[str] = Field(default_factory=list, description="Signals incorporated in calculation")
    missing: list[str] = Field(default_factory=list, description="Expected signals that were absent")
    stale: list[str] = Field(default_factory=list, description="Signals discounted due to age decay")
    assumptions_used: list[str] = Field(default_factory=list, description="Engineering proxies and defaults applied")


class AnomalySummary(FiboBaseModel):
    is_anomaly: bool = Field(False, description="Whether reading vector deviates from history")
    score: float = Field(0.0, description="Normalized anomaly score in [0, 1]")
    scope: str = Field("global", description="Fit scope: 'machine' (local history) or 'global'")
    top_features: list[dict[str, Any]] = Field(default_factory=list)


class RiskResult(BaseResponse):
    machine_id: str = Field(..., description="Machine identifier")
    risk_index: float = Field(..., description="Normalized composite risk score in [0, 1]")
    risk_band: RiskBand = Field(..., description="Risk tier: low, medium, high")
    priority_kzt: int = Field(..., description="Expected loss ranking score in KZT")
    p_model_raw: float | None = Field(None, description="Raw uncalibrated failure probability")
    p_model_cal: float | None = Field(None, description="Calibrated failure probability")
    p_fail_next_cycle: float | None = Field(None, description="Nominal probability of failure in next operating cycle")
    factors: list[FactorContribution] = Field(
        default_factory=list, description="Decomposed factors explaining the risk score"
    )
    base_value: float = Field(..., description="Base risk index value before factor contributions")
    anomaly: AnomalySummary | None = Field(None, description="Sensor readings anomaly assessment")
    coverage: CoverageInfo = Field(..., description="Signal coverage and proxies applied")
    confidence: Confidence = Field(..., description="Deterministic confidence rating")
    ood_warning: bool = Field(False, description="True if >40% of features were clipped or out-of-distribution")


class RiskRankItem(FiboBaseModel):
    machine_id: str
    priority_kzt: int
    risk_index: float
    risk_band: RiskBand
    criticality: str
    expected_repair_hours: float
    top_factors: list[FactorContribution]


class RiskRankRequest(FiboBaseModel):
    machines: list[RiskRequest] = Field(..., description="List of machines to rank")


class RiskRankResponse(BaseResponse):
    ranked_machines: list[RiskRankItem] = Field(..., description="Machines sorted descending by priority_kzt")


class WhatIfRequest(FiboBaseModel):
    machine_id: str
    current: RiskRequest
    overrides: dict[str, Any] = Field(
        ...,
        description="Overrides to simulate, e.g. {'tool_hours': 0, 'hours_since_last_pm': 0}",
    )


class WhatIfResult(BaseResponse):
    machine_id: str
    before: RiskResult
    after: RiskResult
    delta_index: float = Field(..., description="Change in risk index (after - before)")
    delta_priority_kzt: int = Field(..., description="Cost savings in KZT (before - after)")
    changed_factors: list[str] = Field(default_factory=list)


class AnomalyRequest(FiboBaseModel):
    machine_id: str
    history: list[MachineReadings] = Field(default_factory=list)
    latest: MachineReadings


class AnomalyResponse(BaseResponse):
    machine_id: str
    is_anomaly: bool
    score: float
    scope: str
    top_features: list[dict[str, Any]]
