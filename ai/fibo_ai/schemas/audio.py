from typing import Any, Literal

from pydantic import ConfigDict, Field

from fibo_ai.schemas.common import (
    BaseResponse,
    Confidence,
    FiboBaseModel,
    IncidentLevel,
)


class AudioRouteRequest(FiboBaseModel):
    file_path: str | None = Field(None, description="Path to audio file in FIBO_SHARED_DIR")
    mode: Literal["voice", "machine"] | None = Field(
        None, description="Manual override from bot button: 'voice' or 'machine'"
    )
    also_analyze_background: bool = Field(
        False, description="Analyze machine sound behind a voice note when routing as voice"
    )


class AudioRouteResponse(BaseResponse):
    route: str = Field(..., description="Classification: 'voice' or 'machine'")
    speech_ratio: float = Field(..., description="Fraction of frames containing speech (VAD)")
    confidence: Confidence = Field(..., description="Confidence in routing decision")
    also_analyze_background: bool = Field(False, description="True if voice note has machine sound in background")


class BaselineArtifact(BaseResponse):
    machine_id: str = Field(..., description="Machine identifier")
    embedder_id: str = Field("panns_cnn14", description="Model identifier used for embeddings")
    embedder_version: str = Field("1.0.0", description="Embedder model release")
    blob_path: str = Field(..., description="Relative path under FIBO_DATA_DIR to .npz baseline blob")
    sha256: str = Field(..., description="SHA-256 integrity hash of .npz blob")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    stats: dict[str, float] = Field(
        ..., description="Reference distribution stats: mean distance, spread, spread_floor"
    )
    window_params: dict[str, float] = Field(..., description="Windowing parameters (duration_s, overlap)")


class BaselineCreateRequest(FiboBaseModel):
    machine_id: str = Field(..., description="Machine identifier")
    clip_count: int = Field(3, description="Number of normal clips supplied (minimum 3)")
    file_paths: list[str] = Field(default_factory=list, description="Paths to normal clips in FIBO_SHARED_DIR")
    embedder_id: Literal["panns_cnn14", "ast", "mfcc_baseline"] | None = Field(
        None, description="Optional override; defaults to the benchmark-selected embedder"
    )


class AudioAnalyzeRequest(FiboBaseModel):
    machine_id: str
    file_path: str = Field(..., description="Path to current recording in FIBO_SHARED_DIR")
    baseline_ref: BaselineArtifact


class AudioDescriptors(FiboBaseModel):
    band_deltas_db: dict[str, float] = Field(..., description="Delta energy in dB across 6 standard acoustic bands")
    new_tonal_peaks: list[dict[str, Any]] = Field(
        default_factory=list, description="New spectral peaks (Hz, prominence) absent in baseline"
    )
    impulse_index: float = Field(..., description="Crest factor / kurtosis of energy")
    spectral_centroid_shift_hz: float = Field(..., description="Shift of spectral energy centroid relative to baseline")


class AudioAnalysis(BaseResponse):
    machine_id: str = Field(..., description="Machine identifier")
    route: str = Field("machine", description="Classified audio route")
    level: IncidentLevel = Field(..., description="Determined level: normal, attention, critical")
    z_score: float = Field(..., description="Statistical deviation from machine baseline in sigma")
    confidence: Confidence = Field(..., description="Confidence rating")
    descriptors: AudioDescriptors = Field(..., description="Deterministic physical audio descriptors")
    descriptors_text_ru: str = Field(..., description="Verbalized physical explanation in Russian")
    descriptors_text_kk: str = Field(..., description="Verbalized physical explanation in Kazakh")
    spectrogram_png_b64: str | None = Field(
        None, description="Base64 encoded PNG of side-by-side baseline vs current spectrogram"
    )
    quality: dict[str, Any] = Field(default_factory=dict, description="Audio quality metrics (RMS, duration, clipping)")
    baseline_ref: BaselineArtifact | None = Field(None, description="Reference metadata of baseline used for scoring")
    limitations: str = Field(
        "A 5-10 s phone audio recording indicates presence and strength of acoustic deviation from the machine's own baseline, not specific mechanical fault type.",
        description="Scientific limitations statement",
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "request_id": "req-audio-001",
                "machine_id": "ЧПУ-2",
                "route": "machine",
                "level": "critical",
                "z_score": 3.12,
                "confidence": "medium",
                "descriptors": {
                    "band_deltas_db": {
                        "0_250Hz": 1.2,
                        "250_500Hz": 2.1,
                        "500_1000Hz": 3.8,
                        "1000_2000Hz": 5.4,
                        "2000_4000Hz": 7.8,
                        "4000_8000Hz": 9.2,
                    },
                    "new_tonal_peaks": [{"frequency_hz": 4200.0, "prominence_db": 12.4}],
                    "impulse_index": 4.8,
                    "spectral_centroid_shift_hz": 640.0,
                },
                "descriptors_text_ru": "Звук отличается от нормы этого станка (+3,1σ). Выросла энергия на высоких частотах (4–8 кГц, +9,2 дБ), обнаружен новый тональный пик 4200 Гц.",
                "descriptors_text_kk": "Дыбыс осы станоктың нормасынан ауытқыған (+3,1σ). Жоғары жиіліктердегі энергия өсті (4–8 кГц, +9,2 дБ), 4200 Гц жаңа тоналды шың анықталды.",
                "spectrogram_png_b64": None,
                "quality": {"duration_s": 7.4, "rms": 0.042, "clipping_ratio": 0.001},
                "degraded": [],
                "limitations": "Sound gives deviation from the machine's own norm, not fault type.",
            }
        },
    )
