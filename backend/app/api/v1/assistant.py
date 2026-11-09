"""Fibo Assistant: POST /ai/assistant/chat — questions about the workshop, answered from its data.

The client sends the conversation (user/assistant turns only) and the workshop id. The model can
only read that workshop's data, through the tools in modules/assistant/tools.py.
"""

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_profiles, get_session, require_dashboard_key
from app.core.config import settings
from app.core.errors import ExternalServiceError
from app.modules.assistant.chat import run_chat
from app.modules.assistant.llm import LiveLLMClient, MockLLMClient, missing_llm_settings
from app.schemas.assistant import AssistantRequest, AssistantResponse, AssistantStatus
from app.services import workshops as workshops_service

router = APIRouter(
    prefix="/ai/assistant", tags=["Fibo Assistant"], dependencies=[Depends(require_dashboard_key)]
)


@router.get("/status", response_model=AssistantStatus)
async def status() -> AssistantStatus:
    missing = missing_llm_settings()
    return AssistantStatus(
        configured=not missing,
        model=settings.llm_model if "FIBO_LLM_MODEL" not in missing else None,
        missing=missing,
    )


@router.post("/chat", response_model=AssistantResponse, summary="Ask the assistant about the workshop")
async def chat(
    payload: AssistantRequest,
    session: AsyncSession = Depends(get_session),
    profiles: dict = Depends(get_profiles),
) -> AssistantResponse:
    workshop = await workshops_service.get_or_404(session, payload.workshop_id)
    messages = [m.model_dump() for m in payload.messages]
    # The interactive chat uses the API unless the user explicitly chooses offline calculations.
    # FIBO_AI_MODE still controls other pipelines; it must not silently replace this conversation.
    client = LiveLLMClient() if payload.mode == "live" else MockLLMClient()
    try:
        result = await asyncio.wait_for(
            run_chat(session, client, workshop, profiles[workshop.profile], messages, payload.language),
            timeout=60,
        )
    except TimeoutError as exc:
        raise ExternalServiceError("AI response timed out", details={"reason": "timeout"}) from exc
    return AssistantResponse(
        source="ai" if payload.mode == "live" else "builtin",
        answer=result.answer,
        referenced_machine_ids=result.machine_ids,
        referenced_incident_ids=result.incident_ids,
        tools_used=result.tools_used,
        is_demo=workshop.is_demo,
    )
