from fastapi import APIRouter, Depends

from fibo_ai.api.deps import get_ai
from fibo_ai.facade import FiboAI
from fibo_ai.schemas.speech import (
    ParsedSymptom,
    ParseRequest,
    TranscribeRequest,
    TranscribeResponse,
)

router = APIRouter(prefix="/v1/speech", tags=["Speech"])


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(req: TranscribeRequest, ai: FiboAI = Depends(get_ai)) -> TranscribeResponse:
    """Transcribe spoken voice note (Faster-Whisper) with hallucination guards."""
    return await ai.speech.transcribe(req)


@router.post("/parse", response_model=ParsedSymptom)
async def parse_symptom(req: ParseRequest, ai: FiboAI = Depends(get_ai)) -> ParsedSymptom:
    """Extract structured symptom, fuzzy match machine name, assess urgency, and flag safety triggers."""
    return await ai.speech.parse(req)
