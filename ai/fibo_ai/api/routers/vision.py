from fastapi import APIRouter, Depends

from fibo_ai.api.deps import get_ai
from fibo_ai.facade import FiboAI
from fibo_ai.schemas.vision import (
    CompareRequest,
    CompareResponse,
    PanelRequest,
    PanelResponse,
    PatchCoreRequest,
    PatchCoreResponse,
    QualityRequest,
    QualityResponse,
)

router = APIRouter(prefix="/v1/vision", tags=["Vision"])


@router.post("/quality", response_model=QualityResponse)
async def check_image_quality(req: QualityRequest, ai: FiboAI = Depends(get_ai)) -> QualityResponse:
    """Evaluate focus sharpness (Laplacian), exposure, and glare before expensive LLM inference."""
    return await ai.vision.check_quality(req)


@router.post("/panel", response_model=PanelResponse)
async def read_panel(req: PanelRequest, ai: FiboAI = Depends(get_ai)) -> PanelResponse:
    """Extract CNC panel telemetry (spindle RPM, load %, temperature, alarms) with OCR cross-validation."""
    return await ai.vision.read_panel(req)


@router.post("/tool-compare", response_model=CompareResponse)
async def compare_tool(req: CompareRequest, ai: FiboAI = Depends(get_ai)) -> CompareResponse:
    """Compare worn tool photo with reference photo to determine 3-tier wear level and confidence."""
    return await ai.vision.compare_tool(req)


@router.post("/part-defect", response_model=PatchCoreResponse)
async def detect_part_defect(req: PatchCoreRequest, ai: FiboAI = Depends(get_ai)) -> PatchCoreResponse:
    """PatchCore anomaly detection on manufactured part photo with localization heatmap."""
    return await ai.vision.detect_part_defect(req)
