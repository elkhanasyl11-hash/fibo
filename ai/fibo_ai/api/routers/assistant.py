from fastapi import APIRouter, Depends

from fibo_ai.api.deps import get_ai
from fibo_ai.facade import FiboAI
from fibo_ai.schemas.assistant import (
    DashboardChatRequest,
    DashboardChatResponse,
    OperatorChatRequest,
    OperatorChatResponse,
)

router = APIRouter(prefix="/v1/assistant", tags=["Assistants"])


@router.post("/operator", response_model=OperatorChatResponse)
async def operator_chat(req: OperatorChatRequest, ai: FiboAI = Depends(get_ai)) -> OperatorChatResponse:
    """Operator follow-up conversation grounded in machine manual with safety guard."""
    return await ai.assistant.operator_chat(req)


@router.post("/dashboard", response_model=DashboardChatResponse)
async def dashboard_chat(req: DashboardChatRequest, ai: FiboAI = Depends(get_ai)) -> DashboardChatResponse:
    """Chief mechanic dashboard assistant executing read-only data repository tools with verified numbers."""
    return await ai.assistant.dashboard_chat(req)
