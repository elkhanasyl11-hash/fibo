"""AI helpers of the web app: onboarding questions and "what if" advice (app/modules/web_ai)."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_dashboard_key
from app.models.workshop import Workshop
from app.modules.web_ai import advice, questions
from app.schemas.auth import QuestionsRequest, QuestionsResponse
from app.services import machines as machines_service

router = APIRouter(tags=["Web AI"], dependencies=[Depends(require_dashboard_key)])


class AdviceRequest(BaseModel):
    machine_id: int
    language: Literal["ru", "kk"] = "ru"


@router.post("/onboarding/questions", response_model=QuestionsResponse, summary="Industry survey questions")
async def onboarding_questions(payload: QuestionsRequest) -> QuestionsResponse:
    return await questions.questions_for(payload)


@router.post("/ai/advice", response_model=advice.AdviceResponse, summary="What-if options for a machine")
async def machine_advice(
    payload: AdviceRequest, session: AsyncSession = Depends(get_session)
) -> advice.AdviceResponse:
    machine = await machines_service.get_or_404(session, payload.machine_id)
    workshop = await session.get(Workshop, machine.workshop_id)
    return await advice.advise(session, machine, workshop, payload.language)
