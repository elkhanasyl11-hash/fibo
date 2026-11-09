"""Step 3 of compute_score: the failure probability p_model and its explanation (D78, D81).

FIBO_AI_PROVIDER=sidecar: the AI service's model (/v1/risk/predict, RiskRequest with the machine's latest
readings + MachineContext) answers first; only its calibrated probability and factors are used — the risk
index, priority and anomaly stay the backend's. On any failure, including a rejected request, the local
model answers instead (or, without local artifacts, the score runs index-only). The backend still decides
WHETHER a probability is possible (map_features: fresh reading with rpm and load, tool change known), with
the local manifest's training ranges or AI4I_TRAINING_RANGES (min/max of the AI4I 2020 training data).
"""

import asyncio
from datetime import datetime

from app.models.machine import Machine
from app.modules.ai_gateway import provider
from app.modules.ai_gateway.errors import AIRequestRejected
from app.modules.ai_gateway.ids import m_id
from app.modules.ai_gateway.requests import machine_context, machine_readings
from app.modules.machine.feature_map import ReadingValues, map_features, tool_wear_minutes
from app.modules.machine.risk_model import get_active_model
from app.profiles.loader import ProfileConfig

AI4I_TRAINING_RANGES = {
    "type_L": [0.0, 1.0],
    "type_M": [0.0, 1.0],
    "type_H": [0.0, 1.0],
    "air_temperature_k": [295.3, 304.5],
    "process_temperature_k": [305.7, 313.8],
    "rotational_speed_rpm": [1168.0, 2886.0],
    "torque_nm": [3.8, 76.6],
    "tool_wear_min": [0.0, 253.0],
}
NOT_LOADED = {"kind": "note", "topic": "model_not_used", "code": "risk_model_not_loaded"}


async def model_part(
    profile: ProfileConfig,
    machine: Machine,
    readings: list[ReadingValues],
    as_of: datetime,
    tool_wear_override: float | None,
) -> tuple[float | None, str, list[dict]]:
    """Returns (p_model, model_version, explanation entries)."""
    model = get_active_model()
    use_ai = provider.sidecar_enabled() and profile.model_applicable
    if model is None and not use_ai:
        return None, "none", [NOT_LOADED] if profile.model_applicable else []
    ranges = model.training_ranges if model is not None else AI4I_TRAINING_RANGES
    mapped = map_features(profile, machine.tool_changed_at, readings, as_of, ranges, tool_wear_override)
    if mapped.features is None:
        return None, "none", [{"kind": "note", "topic": "model_not_used", "code": c} for c in mapped.missing]
    assumptions = [{"kind": "note", "topic": "assumption", **note} for note in mapped.assumptions]

    async def local() -> tuple[float | None, str, list[dict]]:
        if model is None:
            return None, "none", [NOT_LOADED]
        prediction = await asyncio.to_thread(model.predict, mapped.features)
        shap = [{"kind": "shap", **factor} for factor in prediction.shap_factors]
        return round(prediction.probability, 4), model.version, shap

    if not use_ai:
        p_model, version, entries = await local()
        return p_model, version, entries + assumptions
    usable = [r for r in readings if r.spindle_rpm is not None and r.load_pct is not None]
    wear = (
        tool_wear_override
        if tool_wear_override is not None
        else tool_wear_minutes(machine.tool_changed_at, readings, as_of)[0]
    )
    request = {
        "machine_id": m_id(machine.id),
        "profile": profile.id.value,
        "readings": machine_readings(usable[-1], wear, profile.default_air_temperature_k - 273.15),
        "context": machine_context(machine),
    }
    try:
        outcome = await provider.predict_risk(request, local)
    except AIRequestRejected as exc:  # e.g. readings the AI schema refuses: never a 500 on risk endpoints
        p_model, version, entries = await local()
        note = {"kind": "note", "topic": "degraded", "code": f"ai_rejected:{exc.error.code}"}
        return p_model, version, entries + assumptions + [note]
    if outcome.source == "builtin":
        p_model, version, entries = outcome.value
        notes = [{"kind": "note", "topic": "degraded", "code": code} for code in outcome.degraded]
        return p_model, version, entries + assumptions + notes
    risk = outcome.value
    if risk is None or risk.probability is None:  # input error or no probability for these readings
        return None, risk.model_version if risk else "none", assumptions
    return round(risk.probability, 4), risk.model_version, risk.factors + assumptions
