"""Fibo Machine: incident feed, incident detail and "Resolved".

Incidents are created by the bot through /ingest/*. retry re-runs a failed pipeline; escalate
("Call mechanic") returns the masters the bot should notify.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_session, require_dashboard_key
from app.db.base import IncidentLevel, IncidentStatus
from app.models.incident import Incident
from app.modules.assistant import rag
from app.pipelines import incident_pipeline
from app.schemas.common import UTCDatetime
from app.schemas.incident import IncidentDetail, IncidentRead
from app.schemas.ingest import EscalateResponse, IngestAccepted
from app.schemas.manual import ManualExcerpts
from app.services import incidents as incidents_service

router = APIRouter(prefix="/incidents", tags=["Fibo Machine"], dependencies=[Depends(require_dashboard_key)])


@router.get("", response_model=list[IncidentRead], summary="Incident feed")
async def list_incidents(
    workshop_id: int | None = None,
    machine_id: int | None = None,
    status: IncidentStatus | None = None,
    level: IncidentLevel | None = None,
    date_from: UTCDatetime | None = Query(None, alias="from", description="created_at >= from"),
    date_to: UTCDatetime | None = Query(None, alias="to", description="created_at <= to"),
    page: Pagination = Depends(),
    session: AsyncSession = Depends(get_session),
) -> list[Incident]:
    """Newest first."""
    filters = incidents_service.IncidentFilters(workshop_id, machine_id, status, level, date_from, date_to)
    return await incidents_service.list_incidents(session, filters, page.limit, page.offset)


@router.get("/{incident_id}", response_model=IncidentDetail, summary="Incident with card and attachments")
async def get_incident(incident_id: int, session: AsyncSession = Depends(get_session)) -> Incident:
    return await incidents_service.get_detail_or_404(session, incident_id)


@router.patch("/{incident_id}/resolve", response_model=IncidentRead, summary="Mark incident resolved")
async def resolve_incident(incident_id: int, session: AsyncSession = Depends(get_session)) -> Incident:
    """downtime_hours = resolved_at - created_at; loss_kzt = downtime x hourly cost. 409 if resolved."""
    return await incidents_service.resolve_incident(session, incident_id)


@router.post(
    "/{incident_id}/retry",
    response_model=IngestAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-run a failed pipeline",
)
async def retry_incident(
    incident_id: int, background: BackgroundTasks, session: AsyncSession = Depends(get_session)
) -> IngestAccepted:
    """409 unless the incident is FAILED. A caption from the first run is not re-checked (its safety
    result is already stored and is never removed)."""
    incident = await incidents_service.prepare_retry(session, incident_id)
    background.add_task(incident_pipeline.process_incident, incident.id)
    return IngestAccepted(incident_id=incident.id)


@router.post("/{incident_id}/escalate", response_model=EscalateResponse, summary="Call mechanic")
async def escalate_incident(
    incident_id: int, session: AsyncSession = Depends(get_session)
) -> EscalateResponse:
    incident, machine, telegram_ids = await incidents_service.escalation_targets(session, incident_id)
    return EscalateResponse(
        incident_id=incident.id,
        machine_id=machine.id,
        machine_name=machine.name,
        master_telegram_ids=telegram_ids,
        card_text=incident.card_text,
    )


@router.get(
    "/{incident_id}/manual-excerpts", response_model=ManualExcerpts, summary="Text of cited manual pages"
)
async def manual_excerpts(incident_id: int, session: AsyncSession = Depends(get_session)) -> ManualExcerpts:
    """For the bot's "📖 Manual page" button: the stored text of the pages cited on the card."""
    incident = await incidents_service.get_or_404(session, incident_id)
    excerpts = await rag.page_excerpts(session, incident.machine_id, list(incident.manual_pages or []))
    return ManualExcerpts(incident_id=incident.id, excerpts=excerpts)
