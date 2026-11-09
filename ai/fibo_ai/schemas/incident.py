from typing import Any

from pydantic import ConfigDict, Field

from fibo_ai.schemas.audio import BaselineArtifact
from fibo_ai.schemas.common import (
    BaseResponse,
    Confidence,
    FiboBaseModel,
    IncidentLevel,
    Lang,
    Profile,
)
from fibo_ai.schemas.risk import MachineContext, MachineReadings, RiskResult


class CauseItem(FiboBaseModel):
    text: str = Field(..., description="Hypothesized failure root cause")
    manual_page: int | None = Field(None, description="Page in manual where cause is cited")


class ActionItem(FiboBaseModel):
    text: str = Field(..., description="Immediate operator action")
    manual_page: int | None = Field(None, description="Page in manual where procedure is detailed")


class IncidentCardDraft(FiboBaseModel):
    """LLM-authored content only; level and confidence are always computed by code."""

    findings: list[str] = Field(default_factory=list, max_length=5)
    possible_causes: list[CauseItem] = Field(default_factory=list, max_length=3)
    actions_now: list[ActionItem] = Field(default_factory=list, max_length=4)
    clarifying_question: str | None = Field(None, max_length=300)
    suggested_buttons: list[str] = Field(default_factory=list, max_length=4)

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "findings": ["Operator reports smoke near spindle."],
                "possible_causes": [],
                "actions_now": [{"text": "Call the mechanic.", "manual_page": None}],
                "clarifying_question": None,
                "suggested_buttons": ["call_mechanic"],
            }
        },
    )


class IncidentCard(FiboBaseModel):
    level: IncidentLevel = Field(..., description="Deterministic incident level")
    confidence: Confidence = Field(..., description="Deterministic confidence rating")
    headline: str = Field(..., description="Header text for Telegram card")
    findings: list[str] = Field(default_factory=list, description="List of observed symptoms and facts")
    possible_causes: list[CauseItem] = Field(
        default_factory=list, description="Causes with verified manual page citations"
    )
    actions_now: list[ActionItem] = Field(default_factory=list, description="Actionable safe steps for operator")
    clarifying_question: str | None = Field(None, description="At most one single clarifying question for the operator")
    suggested_buttons: list[str] = Field(
        default_factory=list, description="Action buttons (resolved, call_mechanic, etc.)"
    )
    manual_pages: list[int] = Field(default_factory=list, description="All cited manual pages")
    card_text: str = Field(..., description="Rendered Telegram-HTML card (<=4096 chars)")
    lang: Lang = Field(Lang.ru, description="Card presentation language")


class IncidentSignals(FiboBaseModel):
    machine_id: str | None = None
    extracted_readings: MachineReadings = Field(default_factory=lambda: MachineReadings())
    audio_z: float | None = None
    audio_level: IncidentLevel | None = None
    photo_wear: str | None = None
    symptom_category: str | None = None
    safety_triggers: list[str] = Field(default_factory=list)


class IncidentAnalyzeRequest(FiboBaseModel):
    workshop_id: str = Field(..., description="Workshop identifier")
    machine_id: str | None = Field(None, description="Pre-selected machine ID if known")
    profile: Profile = Field(Profile.metalworking, description="Industry domain profile")
    lang: Lang = Field(Lang.ru, description="Desired communication language")
    voice_file_path: str | None = Field(None, description="Voice note audio path")
    audio_file_path: str | None = Field(None, description="Machine sound recording path")
    panel_photo_path: str | None = Field(None, description="CNC panel photo path")
    tool_photo_path: str | None = Field(None, description="Cutter/tool photo path")
    tool_reference_photo_path: str | None = Field(
        None, description="Known-good reference tool photo path for comparison"
    )
    text: str | None = Field(None, description="Operator typed text description")
    catalog_machines: list[str] = Field(
        default_factory=list, description="Machine IDs/names available for spoken-name resolution"
    )
    context: MachineContext = Field(default_factory=lambda: MachineContext())
    baseline_ref: BaselineArtifact | None = Field(None, description="Baseline reference artifact")
    answers: dict[str, str] | None = Field(None, description="Answers to previously asked clarifying question")
    incident_context: dict[str, Any] | None = Field(None, description="Context from previous turn in multi-turn triage")


class IncidentAnalyzeResponse(BaseResponse):
    card: IncidentCard = Field(..., description="Ready-to-send operator card")
    signals: IncidentSignals = Field(..., description="Extracted signals for backend persistence")
    risk: RiskResult = Field(..., description="Updated risk computation result")

    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "example": {
                "request_id": "req-inc-01",
                "card": {
                    "level": "critical",
                    "confidence": "medium",
                    "headline": "🔴 ЧПУ-2 · Критично · уверенность: средняя",
                    "findings": [
                        "Звук отличается от нормы этого станка (+3,1σ), рост высоких частот",
                        "Запах гари в районе шпинделя",
                    ],
                    "possible_causes": [
                        {
                            "text": "Перегрев подшипников шпинделя из-за масляного голодания",
                            "manual_page": 47,
                        }
                    ],
                    "actions_now": [
                        {"text": "Остановите станок и отключите питание.", "manual_page": None},
                        {"text": "Проверьте уровень масла в маслостанции №2.", "manual_page": 47},
                    ],
                    "clarifying_question": "Вращается ли шпиндель свободно вручную при выключенном питании?",
                    "suggested_buttons": ["resolved", "call_mechanic", "manual_page_47"],
                    "manual_pages": [47],
                    "card_text": "🔴 <b>ЧПУ-2 · Критично · уверенность: средняя</b>\n\n<b>Что найдено:</b> звук отличается от нормы этого станка (отклонение 3,1σ), рост высоких частот.\n<b>Возможные причины</b> (по паспорту, с. 47): 1. Перегрев подшипников шпинделя из-за масляного голодания.\n<b>Что делать сейчас:</b>\n1. Остановите станок и отключите питание.\n2. Проверьте уровень масла в маслостанции №2 (паспорт, с. 47).",
                    "lang": "ru",
                },
                "signals": {
                    "machine_id": "ЧПУ-2",
                    "extracted_readings": {
                        "spindle_rpm": 3200.0,
                        "spindle_load_pct": 82.0,
                        "temp_c": 54.0,
                    },
                    "audio_z": 3.12,
                    "audio_level": "critical",
                    "photo_wear": "moderate",
                    "symptom_category": "overheat",
                    "safety_triggers": ["гар*"],
                },
                "risk": {
                    "machine_id": "ЧПУ-2",
                    "risk_index": 0.84,
                    "risk_band": "high",
                    "priority_kzt": 315000,
                    "p_model_raw": 0.78,
                    "p_model_cal": 0.82,
                    "p_fail_next_cycle": 0.82,
                    "factors": [
                        {
                            "name": "audio",
                            "label_ru": "Отклонение звука от нормы станка",
                            "label_kk": "Дыбыстың станок нормасынан ауытқуы",
                            "value": 3.12,
                            "contribution": 0.32,
                            "direction": "increases_risk",
                        }
                    ],
                    "base_value": 0.20,
                    "coverage": {
                        "used": ["audio", "model", "pm_overdue"],
                        "missing": ["photo_wear"],
                        "stale": [],
                        "assumptions_used": ["spindle load % as torque proxy"],
                    },
                    "confidence": "medium",
                    "ood_warning": False,
                    "request_id": "req-inc-01",
                    "model_version": "0.1.0-stub",
                    "config_version": "2026.11",
                    "degraded": [],
                },
                "degraded": [],
            }
        },
    )
