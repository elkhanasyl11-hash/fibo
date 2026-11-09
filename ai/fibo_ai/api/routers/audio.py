from fastapi import APIRouter, Body, Depends, HTTPException, Query

from fibo_ai.api.deps import get_ai
from fibo_ai.facade import FiboAI
from fibo_ai.schemas.audio import (
    AudioAnalysis,
    AudioAnalyzeRequest,
    AudioRouteRequest,
    AudioRouteResponse,
    BaselineArtifact,
    BaselineCreateRequest,
)

router = APIRouter(prefix="/v1/audio", tags=["Audio"])


@router.post("/route", response_model=AudioRouteResponse)
async def route_audio(req: AudioRouteRequest, ai: FiboAI = Depends(get_ai)) -> AudioRouteResponse:
    """Classify recording as voice note (ASR) or machine sound using VAD speech ratio."""
    return await ai.audio.route(req)


@router.post("/baseline", response_model=BaselineArtifact)
async def create_baseline(req: BaselineCreateRequest, ai: FiboAI = Depends(get_ai)) -> BaselineArtifact:
    """Build acoustic centroid and spread floor from 3 reference normal operation clips."""
    return await ai.audio.create_baseline(req)


@router.post("/analyze", response_model=AudioAnalysis)
async def analyze_audio(
    req: AudioAnalyzeRequest | None = Body(default=None),
    machine_id: str | None = Query(default=None),
    file_path: str | None = Query(default=None),
    ai: FiboAI = Depends(get_ai),
) -> AudioAnalysis:
    """Score deviation (z-score) against machine baseline, generate Welch PSD descriptors and spectrogram."""
    if req is not None:
        return await ai.audio.analyze(machine_id=req.machine_id, file_path=req.file_path, baseline_ref=req.baseline_ref)
    if machine_id and file_path:
        return await ai.audio.analyze(machine_id=machine_id, file_path=file_path)
    raise HTTPException(status_code=422, detail="Provide an AudioAnalyzeRequest body")
