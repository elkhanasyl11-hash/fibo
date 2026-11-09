"""System: GET /health. Used by the Docker healthcheck and by the team before the demo.

Returns 200 when the database answers, 503 otherwise. Also reports whether the risk model is
loaded (False = index-only mode), the AI mode (mock/live), the vector store status and the AI service
(sidecar) status. The AI service being down never makes health fail: the backend falls back (D76).
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.modules.ai_gateway.status import ai_status
from app.modules.assistant.chroma import reachable as chroma_reachable
from app.modules.machine.risk_model import get_active_model
from app.schemas.health import HealthRead

router = APIRouter(tags=["System"])
logger = logging.getLogger("fibo.health")


@router.get(
    "/health",
    response_model=HealthRead,
    summary="Service health",
    responses={503: {"model": HealthRead, "description": "Database unreachable"}},
)
async def health(request: Request, session: AsyncSession = Depends(get_session)) -> JSONResponse:
    try:
        await session.execute(text("SELECT 1"))
        database = "ok"
    except SQLAlchemyError:
        logger.exception("health check: database ping failed")
        database = "error"

    risk_model = get_active_model()
    body = HealthRead(
        status="ok" if database == "ok" else "error",
        database=database,
        risk_model_loaded=risk_model is not None,
        risk_model_version=risk_model.version if risk_model is not None else "none",
        ai_mode=settings.ai_mode,
        chroma="ok" if await asyncio.to_thread(chroma_reachable) else "error",
        profiles_loaded=len(request.app.state.profiles),
        ai_provider=settings.ai_provider,
        **await ai_status(),
    )
    return JSONResponse(status_code=200 if database == "ok" else 503, content=body.model_dump())
