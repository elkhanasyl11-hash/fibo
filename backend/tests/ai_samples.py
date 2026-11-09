"""AI service answers in the service's REAL shapes (ai/fibo_ai/schemas), shared by the AI tests.

tests/test_ai_contract.py validates every sample here against the service's Pydantic models, so the mocks
cannot drift from the real API again (D81).
"""

import copy

META = {"request_id": "req-test", "model_version": "0.1.0-stub", "config_version": "2026.11", "degraded": []}

CARD = {
    "level": "attention",
    "confidence": "medium",
    "headline": "🟡 ЧПУ-1 · Внимание · уверенность: средняя",
    "findings": ["Износ подшипника шпинделя", "Гул на высоких оборотах"],
    "possible_causes": [{"text": "Подшипник", "manual_page": 12}, {"text": "Смазка", "manual_page": 99}],
    "actions_now": [{"text": "Снизить обороты", "manual_page": None}, {"text": "Позвать механика"}],
    "clarifying_question": None,
    "suggested_buttons": ["resolved", "call_mechanic"],
    "manual_pages": [12],
    "card_text": "🟡 <b>ЧПУ-1 · Внимание</b>",
    "lang": "ru",
}
SIGNALS = {
    "machine_id": "m-1",
    "extracted_readings": {},
    "audio_z": None,
    "audio_level": None,
    "photo_wear": None,
    "symptom_category": "noise",
    "safety_triggers": [],
}
FACTORS = [
    {
        "name": "tool_hours",
        "label_ru": "Наработка инструмента",
        "label_kk": "Құрал",
        "value": 58.0,
        "contribution": 0.12,
        "direction": "increases_risk",
    },
    {
        "name": "spindle_load_pct",
        "label_ru": "Нагрузка шпинделя",
        "label_kk": "Жүктеме",
        "value": 82.0,
        "contribution": -0.2,
        "direction": "decreases_risk",
    },
]
RISK = {
    **META,
    "machine_id": "m-1",
    "risk_index": 0.42,
    "risk_band": "medium",
    "priority_kzt": 120000,
    "p_model_raw": 0.4,
    "p_model_cal": 0.42,
    "p_fail_next_cycle": 0.42,
    "factors": FACTORS,
    "base_value": 0.2,
    "coverage": {"used": ["model"], "missing": [], "stale": [], "assumptions_used": []},
    "confidence": "medium",
    "ood_warning": False,
}
PANEL = {
    **META,
    "readings": {"spindle_rpm": 2400.0, "spindle_load_pct": 400.0, "temp_c": None, "runtime_h": 1200.0},
    "alarms": [],
    "per_field_confidence": {"spindle_rpm": "high", "spindle_load_pct": "low"},
    "raw_ocr_tokens": [],
}
BASELINE = {
    **META,
    "machine_id": "m-1",
    "embedder_id": "mfcc_baseline",
    "embedder_version": "1.0.0",
    "blob_path": "baselines/m-1.npz",
    "sha256": "ab" * 32,
    "created_at": "2026-11-09T08:00:00Z",
    "stats": {"mean_distance": 1.0, "spread": 0.2, "spread_floor": 0.05},
    "window_params": {"duration_s": 1.0, "overlap": 0.5},
}
MANUAL_STATUS = {**META, "manual_id": "man-1", "machine_id": "m-1", "status": "ready", "pages_indexed": 40}


def incident(card: dict | None = None, signals: dict | None = None, degraded: list | None = None) -> dict:
    """An IncidentAnalyzeResponse; card/signals entries override the defaults."""
    return {
        **META,
        "degraded": degraded or [],
        "card": {**copy.deepcopy(CARD), **(card or {})},
        "signals": {**copy.deepcopy(SIGNALS), **(signals or {})},
        "risk": copy.deepcopy(RISK),
    }
