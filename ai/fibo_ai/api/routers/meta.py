from fastapi import APIRouter, Depends, Response

from fibo_ai.api.deps import get_ai
from fibo_ai.facade import FiboAI
from fibo_ai.schemas.meta import HealthResponse, ModelsMetaResponse, ReadyResponse

router = APIRouter(tags=["Metadata & Health"])


@router.get("/healthz", response_model=HealthResponse)
def healthz(ai: FiboAI = Depends(get_ai)) -> HealthResponse:
    """Liveness probe returning HTTP 200 when service process is running."""
    return ai.meta.get_health()


@router.get("/readyz", response_model=ReadyResponse)
def readyz(response: Response, ai: FiboAI = Depends(get_ai)) -> ReadyResponse:
    """Readiness probe returning HTTP 200 when model artifacts and vector stores are ready for traffic."""
    result = ai.meta.get_ready()
    if not result.ready:
        response.status_code = 503
    return result


@router.get("/v1/meta/models", response_model=ModelsMetaResponse)
def get_models_meta(ai: FiboAI = Depends(get_ai)) -> ModelsMetaResponse:
    """List loaded model versions and validation metrics recorded in reports/metrics.json."""
    return ai.meta.get_models_meta()
