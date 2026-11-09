from fastapi import APIRouter, Depends

from fibo_ai.api.deps import get_ai
from fibo_ai.facade import FiboAI
from fibo_ai.schemas.risk import AnomalyRequest, AnomalyResponse

router = APIRouter(prefix="/v1/anomaly", tags=["Anomaly"])


@router.post("/readings", response_model=AnomalyResponse)
async def detect_anomaly(req: AnomalyRequest, ai: FiboAI = Depends(get_ai)) -> AnomalyResponse:
    """Detect multi-variate reading drift using Isolation Forest and robust z-score attribution."""
    return await ai.risk.anomaly(req)
