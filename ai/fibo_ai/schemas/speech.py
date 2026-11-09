from typing import Any

from pydantic import ConfigDict, Field

from fibo_ai.schemas.common import (
    BaseResponse,
    Confidence,
    Criticality,
    FiboBaseModel,
    Lang,
    Profile,
)


class TranscribeRequest(FiboBaseModel):
    file_path: str | None = Field(None, description="Path to audio file in FIBO_SHARED_DIR")
    language_hint: Lang | None = Field(None, description="Expected language (ru, kk, en)")
    profile: Profile = Field(Profile.metalworking, description="Vocabulary context for recognition")
    catalog_machines: list[str] = Field(
        default_factory=list, description="Workshop machine names added to the ASR vocabulary"
    )


class TranscriptSegment(FiboBaseModel):
    start_s: float
    end_s: float
    text: str
    no_speech_prob: float
    avg_logprob: float
    compression_ratio: float


class TranscribeResponse(BaseResponse):
    text: str = Field(..., description="Recognized speech text")
    language: Lang = Field(..., description="Detected language (ru, kk, en)")
    confidence: Confidence = Field(..., description="Confidence rating")
    duration_s: float = Field(..., description="Audio duration in seconds")
    segments: list[TranscriptSegment] = Field(default_factory=list)


class ParseRequest(FiboBaseModel):
    text: str = Field(..., description="Operator spoken transcript or typed message")
    profile: Profile = Field(Profile.metalworking, description="Industry profile")
    catalog_machines: list[str] = Field(default_factory=list, description="List of valid machine names/IDs in workshop")

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "text": "ЧПУ второй сильно греется шпиндель и появился запах гари",
                "profile": "metalworking",
                "catalog_machines": ["ЧПУ-1", "ЧПУ-2", "ЧПУ-3", "Пила-1"],
            }
        },
    )


class ParsedSymptom(BaseResponse):
    machine_id: str | None = Field(None, description="Resolved machine ID if matched unambiguously")
    machine_candidates: list[str] = Field(
        default_factory=list, description="Fuzzy matched candidate machines if ambiguous"
    )
    symptom_text: str = Field(..., description="Normalized symptom description")
    symptom_category: str = Field(
        ...,
        description="Category: noise, vibration, overheat, smell_smoke, leak, quality_defect, stoppage, electrical, other",
    )
    conditions: dict[str, Any] = Field(
        default_factory=dict, description="Extracted operating conditions (under_load, idle, etc.)"
    )
    urgency: Criticality = Field(Criticality.medium, description="Assessed urgency level")
    safety_flags: list[str] = Field(default_factory=list, description="Detected safety hazards from text")
    language: Lang = Field(Lang.ru, description="Primary language of utterance")
    needs_clarification: bool = Field(False, description="True if machine name or critical symptom is ambiguous")
    clarifying_prompt: str | None = Field(None, description="Suggested question to prompt operator for clarification")
