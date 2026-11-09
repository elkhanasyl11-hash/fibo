from fastapi import APIRouter, Depends

from fibo_ai.api.deps import get_ai
from fibo_ai.facade import FiboAI
from fibo_ai.schemas.incident import IncidentAnalyzeRequest, IncidentAnalyzeResponse

router = APIRouter(prefix="/v1/incident", tags=["Incident Orchestration"])


@router.post("/analyze", response_model=IncidentAnalyzeResponse)
async def analyze_incident(req: IncidentAnalyzeRequest, ai: FiboAI = Depends(get_ai)) -> IncidentAnalyzeResponse:
    """One-shot multimodal orchestration: ASR + audio + vision + risk + RAG + safety guard -> Operator card."""
    return await ai.incident.analyze(req)
