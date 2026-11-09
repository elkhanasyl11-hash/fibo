from typing import Literal

from pydantic import ConfigDict, Field

from fibo_ai.schemas.common import BaseResponse, Confidence, FiboBaseModel, Lang
from fibo_ai.schemas.risk import MachineReadings


class QualityRequest(FiboBaseModel):
    file_path: str | None = Field(None, description="Path to image file in FIBO_SHARED_DIR")
    image_b64: str | None = Field(None, description="Base64 encoded image data")


class QualityResponse(BaseResponse):
    is_acceptable: bool = Field(..., description="Whether photo passes minimum quality threshold")
    issues: list[str] = Field(default_factory=list, description="Quality defects detected: blur, dark, bright, glare")
    sharpness_laplacian: float = Field(..., description="Variance of Laplacian focus metric")
    mean_luminance: float = Field(..., description="Average image luminance [0-255]")
    glare_ratio: float = Field(..., description="Proportion of overexposed/specular reflection pixels")
    retake_advice_ru: str | None = Field(None, description="Russian instruction for retaking picture")
    retake_advice_kk: str | None = Field(None, description="Kazakh instruction for retaking picture")


class PanelRequest(FiboBaseModel):
    file_path: str | None = Field(None, description="Path to CNC panel image")
    machine_id: str | None = Field(None, description="Optional machine ID to fetch bounds")
    workshop_id: str | None = Field(None, description="Workshop scope for machine catalog lookup")
    lang: Lang = Field(Lang.ru, description="Language for localized guidance")


class PanelResponse(BaseResponse):
    readings: MachineReadings = Field(..., description="Extracted numerical machine readings")
    alarms: list[str] = Field(default_factory=list, description="Active CNC alarm codes and banners")
    per_field_confidence: dict[str, Confidence] = Field(
        default_factory=dict, description="Confidence per extracted reading field"
    )
    raw_ocr_tokens: list[str] = Field(
        default_factory=list, description="Raw tokens found by OCR for cross-verification"
    )


class CompareRequest(FiboBaseModel):
    file_path_reference: str | None = Field(None, description="Reference image of new tool")
    file_path_current: str | None = Field(None, description="Current photo of tool")
    lang: Lang = Field(Lang.ru, description="Language for visual evidence")


class CompareResponse(BaseResponse):
    defect_found: bool = Field(..., description="Whether measurable tool wear/defect was detected")
    defect_type: Literal["chipping", "edge_wear", "build_up", "crack", "none"] = Field(
        ..., description="Type of wear: chipping, edge_wear, build_up, crack, none"
    )
    zone: str = Field(..., description="Identified wear region, e.g. 'main_cutting_edge'")
    wear_level: Literal["none", "slight", "moderate", "severe"] = Field(
        ..., description="Three discrete levels: none, slight, moderate, severe"
    )
    confidence: Confidence = Field(..., description="Confidence rating")
    evidence: str = Field(..., description="Visual justification describing observed defects")


class PatchCoreRequest(FiboBaseModel):
    file_path: str = Field(..., description="Path to part photo")
    category: str = Field("metal_nut", description="MVTec category or part family")


class PatchCoreResponse(BaseResponse):
    anomaly_score: float = Field(..., description="PatchCore nearest-neighbor anomaly score")
    is_defect: bool = Field(..., description="True if anomaly_score >= calibrated threshold")
    threshold: float = Field(..., description="Operating threshold calibrated on validation set")
    heatmap_png_b64: str | None = Field(None, description="Base64 encoded PNG of defect localization heatmap")
    top_region_bbox: list[float] | None = Field(
        None, description="Normalized bounding box [ymin, xmin, ymax, xmax] of maximum anomaly"
    )

    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "example": {
                "request_id": "req-vision-01",
                "anomaly_score": 0.742,
                "is_defect": True,
                "threshold": 0.580,
                "heatmap_png_b64": None,
                "top_region_bbox": [0.35, 0.42, 0.58, 0.65],
                "degraded": [],
            }
        },
    )
