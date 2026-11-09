"""Startup sweep: finish work that a restart or crash left half-done.

Background tasks (FastAPI BackgroundTasks) live in the server process. If the server stops while an
incident is RECEIVED/PROCESSING or a manual is PENDING/INDEXING, nothing will ever finish them and the
bot would wait forever. At startup no task can be running yet, so every such row is marked FAILED with
a clear reason; the user can retry (POST /incidents/{id}/retry, or upload the manual again).
A safety result already saved on an incident is kept (its card text and CRITICAL level stay).
"""

import logging

from sqlalchemy import update

from app.db.base import IncidentStatus, IndexStatus
from app.db.session import SessionLocal
from app.models.incident import Incident
from app.models.manual import Manual

logger = logging.getLogger("fibo.recovery")
INTERRUPTED = "interrupted: the server restarted during processing, please retry"


async def fail_interrupted_work() -> tuple[int, int]:
    """Returns (incidents, manuals) marked FAILED."""
    async with SessionLocal() as session:
        incidents = await session.execute(
            update(Incident)
            .where(Incident.status.in_([IncidentStatus.RECEIVED, IncidentStatus.PROCESSING]))
            .values(status=IncidentStatus.FAILED, error_message=INTERRUPTED)
        )
        manuals = await session.execute(
            update(Manual)
            .where(Manual.index_status.in_([IndexStatus.PENDING, IndexStatus.INDEXING]))
            .values(index_status=IndexStatus.FAILED, error_message=INTERRUPTED)
        )
        await session.commit()
    counts = (incidents.rowcount, manuals.rowcount)
    if any(counts):
        logger.warning("interrupted work marked failed", extra={"incidents": counts[0], "manuals": counts[1]})
    return counts
