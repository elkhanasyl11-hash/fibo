"""Fibo Reports: period summary (downtime, losses in KZT, MTBF, top causes) and CSV export.

Both endpoints take workshop_id and an optional period (`from`, `to`, with timezone); without a
period the last 30 days are used. Incidents are counted by the time they were reported.
"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_dashboard_key
from app.modules.reports.summary import build_summary, to_csv
from app.schemas.common import UTCDatetime
from app.schemas.report import ReportSummary

router = APIRouter(prefix="/reports", tags=["Fibo Reports"], dependencies=[Depends(require_dashboard_key)])


@router.get("/summary", response_model=ReportSummary, summary="Downtime, losses, MTBF, top causes")
async def summary(
    workshop_id: int,
    date_from: UTCDatetime | None = Query(None, alias="from"),
    date_to: UTCDatetime | None = Query(None, alias="to"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await build_summary(session, workshop_id, date_from, date_to)


@router.get(
    "/export.csv",
    summary="Same report as CSV (UTF-8 with BOM, ';' separated, for Excel)",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_csv(
    workshop_id: int,
    date_from: UTCDatetime | None = Query(None, alias="from"),
    date_to: UTCDatetime | None = Query(None, alias="to"),
    session: AsyncSession = Depends(get_session),
) -> Response:
    report = await build_summary(session, workshop_id, date_from, date_to)
    filename = f"fibo-report-{workshop_id}-{report['period_to']:%Y%m%d}.csv"
    return Response(
        content=to_csv(report),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
