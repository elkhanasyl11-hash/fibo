from fastapi import APIRouter, Depends

from fibo_ai.api.deps import get_ai
from fibo_ai.facade import FiboAI
from fibo_ai.schemas.risk import (
    RiskRankRequest,
    RiskRankResponse,
    RiskRequest,
    RiskResult,
    WhatIfRequest,
    WhatIfResult,
)

router = APIRouter(prefix="/v1/risk", tags=["Risk"])


@router.post("/predict", response_model=RiskResult)
async def predict_risk(req: RiskRequest, ai: FiboAI = Depends(get_ai)) -> RiskResult:
    """Compute failure risk, transparent factor attribution (SHAP), and priority score in KZT."""
    return await ai.risk.predict(req)


@router.post("/rank", response_model=RiskRankResponse)
async def rank_machines(req: RiskRankRequest, ai: FiboAI = Depends(get_ai)) -> RiskRankResponse:
    """Rank N workshop machines descending by expected loss in KZT (priority_kzt)."""
    return await ai.risk.rank(req)


@router.post("/what-if", response_model=WhatIfResult)
async def what_if_simulation(req: WhatIfRequest, ai: FiboAI = Depends(get_ai)) -> WhatIfResult:
    """Simulate maintenance action overrides and calculate risk reduction and savings in KZT."""
    return await ai.risk.what_if(req)
