"""Fibo Machine: risk scores — recompute, ranking by priority in tenge, what-if, history."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_profiles, get_session, require_dashboard_key
from app.core.errors import DomainValidationError
from app.models.risk_score import RiskScore
from app.models.workshop import Workshop
from app.modules.machine import service as risk_service
from app.schemas.common import UTCDatetime
from app.schemas.risk_score import (
    RankingItem,
    RankingResponse,
    RecomputeRequest,
    RiskScoreRead,
    WhatIfRequest,
    WhatIfResponse,
)
from app.services import machines as machines_service
from app.services import workshops as workshops_service
from app.services.readings import validate_reading_values

router = APIRouter(tags=["Fibo Machine"], dependencies=[Depends(require_dashboard_key)])


@router.post("/risk-scores/recompute", response_model=list[RiskScoreRead], summary="Recompute risk now")
async def recompute(
    payload: RecomputeRequest, session: AsyncSession = Depends(get_session)
) -> list[RiskScore]:
    if payload.machine_id is not None:
        machine_ids = [(await machines_service.get_or_404(session, payload.machine_id)).id]
    else:
        await workshops_service.get_or_404(session, payload.workshop_id)
        machine_ids = [m.id for m in await machines_service.list_for_workshop(session, payload.workshop_id)]
    return [await risk_service.recompute_and_save(session, machine_id) for machine_id in machine_ids]


@router.get("/risk-scores/ranking", response_model=RankingResponse, summary="Maintenance priority ranking")
async def ranking(workshop_id: int, session: AsyncSession = Depends(get_session)) -> RankingResponse:
    """Latest score per machine, highest expected loss (priority_kzt) first, with top-3 SHAP factors."""
    await workshops_service.get_or_404(session, workshop_id)
    rows = await risk_service.ranking(session, workshop_id)
    scored = {machine.id for _, machine in rows}
    all_machines = await machines_service.list_for_workshop(session, workshop_id)
    items = [
        RankingItem(
            machine_id=m.id,
            machine_name=m.name,
            machine_type=m.type,
            criticality=m.criticality,
            is_demo=m.is_demo,
            score=RiskScoreRead.model_validate(score),
        )
        for score, m in rows
    ]
    unscored = [m.id for m in all_machines if m.id not in scored]
    return RankingResponse(workshop_id=workshop_id, items=items, unscored_machine_ids=unscored)


@router.post("/risk-scores/what-if", response_model=WhatIfResponse, summary="What if… (not saved)")
async def what_if(
    payload: WhatIfRequest,
    session: AsyncSession = Depends(get_session),
    profiles: dict = Depends(get_profiles),
) -> WhatIfResponse:
    """Recompute with hypothetical values (e.g. lower load, new tool, maintenance done). Nothing is saved."""
    machine = await machines_service.get_or_404(session, payload.machine_id)
    workshop = await session.get(Workshop, machine.workshop_id)
    values = payload.overrides.model_dump(include={"load_pct", "spindle_rpm", "temperature_c"})
    if any(v is not None for v in values.values()):
        problems = validate_reading_values(profiles[workshop.profile], values, None)
        if problems:
            raise DomainValidationError("Override values are not valid", details={"fields": problems})
    current, scenario = await risk_service.what_if(session, machine.id, payload.overrides)
    return WhatIfResponse(
        current=RiskScoreRead.model_validate(current), scenario=RiskScoreRead.model_validate(scenario)
    )


@router.get("/machines/{machine_id}/risk-history", response_model=list[RiskScoreRead], summary="Risk history")
async def risk_history(
    machine_id: int,
    date_from: UTCDatetime | None = Query(None, alias="from"),
    date_to: UTCDatetime | None = Query(None, alias="to"),
    daily: bool = Query(False, description="Only the last score of each day (charts); no paging"),
    utc_offset_minutes: int = Query(0, ge=-720, le=840, description="Caller's time zone for `daily` days"),
    page: Pagination = Depends(),
    session: AsyncSession = Depends(get_session),
) -> list[RiskScore]:
    """Oldest first (chart order). The scheduler adds a score every hour; charts use daily=true."""
    if daily:
        return await risk_service.daily_history(session, machine_id, date_from, date_to, utc_offset_minutes)
    return await risk_service.history(session, machine_id, date_from, date_to, page.limit, page.offset)
