"""Response/request schemas for risk scores, ranking and what-if.

The `shap_factors` column stores a list of explanation entries, each with a `kind`:
  shap    a SHAP factor of the model: feature, title_ru, value, contribution (log-odds)
  signal  one risk-index signal: name, title_ru, value (0..1 or null), weight
  note    topic "assumption" (feature approximations), "anomaly" (Isolation Forest result) or
          "model_not_used" (why there is no failure probability)
The API does not return that raw list; it returns the parts below, ready for the dashboard.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.schemas.common import Money


def _strip_kind(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if k not in {"kind", "topic"}}


class RiskScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, description="None for what-if results (not saved)")
    machine_id: int
    computed_at: datetime
    failure_probability: float | None = Field(description="Calibrated; None if the model does not apply")
    risk_index: float = Field(ge=0, le=1)
    priority_kzt: Money
    is_anomaly: bool
    inputs_used: list[str] = Field(description="Signals included in risk_index")
    model_version: str
    is_demo: bool = Field(description="True = computed for a synthetic demo machine")
    shap_factors: list[dict] = Field(exclude=True)

    @computed_field
    @property
    def shap_top3(self) -> list[dict]:
        """Top-3 model factors. Positive contribution = pushes the failure risk up."""
        return [_strip_kind(e) for e in self.shap_factors if e.get("kind") == "shap"][:3]

    @computed_field
    @property
    def signals(self) -> list[dict]:
        return [_strip_kind(e) for e in self.shap_factors if e.get("kind") == "signal"]

    @computed_field
    @property
    def assumptions(self) -> list[dict]:
        """Approximations used to map workshop readings to the AI4I model features."""
        return [_strip_kind(e) for e in self.shap_factors if e.get("topic") == "assumption"]

    @computed_field
    @property
    def model_not_used_reasons(self) -> list[str]:
        return [e["code"] for e in self.shap_factors if e.get("topic") == "model_not_used"]

    @computed_field
    @property
    def anomaly_reason(self) -> str | None:
        return next((e["code"] for e in self.shap_factors if e.get("topic") == "anomaly"), None)


class WhatIfOverrides(BaseModel):
    """Hypothetical changes for POST /risk-scores/what-if. Unset fields keep the current value."""

    load_pct: float | None = None
    spindle_rpm: float | None = None
    temperature_c: float | None = None
    tool_wear_min: float | None = Field(default=None, ge=0, description="e.g. 0 = tool replaced")
    maintenance_done: bool = Field(default=False, description="True = maintenance just done")


class RankingItem(BaseModel):
    machine_id: int
    machine_name: str
    machine_type: str
    criticality: int
    is_demo: bool
    score: RiskScoreRead


class RankingResponse(BaseModel):
    workshop_id: int
    items: list[RankingItem] = Field(description="Sorted by priority_kzt, highest first")
    unscored_machine_ids: list[int] = Field(description="Machines without any risk score yet")


class RecomputeRequest(BaseModel):
    machine_id: int | None = None
    workshop_id: int | None = Field(default=None, description="Recompute all machines of this workshop")

    @model_validator(mode="after")
    def exactly_one(self) -> "RecomputeRequest":
        if (self.machine_id is None) == (self.workshop_id is None):
            raise ValueError("give exactly one of machine_id or workshop_id")
        return self


class WhatIfRequest(BaseModel):
    machine_id: int
    overrides: WhatIfOverrides


class WhatIfResponse(BaseModel):
    current: RiskScoreRead
    scenario: RiskScoreRead
    saved: bool = Field(default=False, description="Always false: what-if never writes to the database")
