"""Background indexing of an uploaded PDF manual.

index_manual(manual_id) opens its own session: status INDEXING -> extract + chunk + embed + store
(rag_index.index_pdf, in a thread) -> READY with page_count. Scanned pages are listed as a warning in
error_message (OCR is out of scope). No text at all, or any error -> FAILED with a short reason.
Every step is inside one guard, so a manual can never stay INDEXING because of an error here
(a server restart is handled by the startup sweep in pipelines/recovery.py).
Re-running is safe: old chunks of the manual are deleted first.
FIBO_AI_PROVIDER=sidecar: the manual is ALSO sent to the AI service's index (so its cards can cite pages).
The backend's own index stays the source of truth for index_status: it serves the builtin fallback and
the dashboard assistant. The AI index status is logged, not stored (D78); a failed AI index only means
the AI answers MANUAL_NOT_INDEXED and the incident falls back to the builtin card with the manual pages.
"""

import asyncio
import logging

from app.db.base import IndexStatus
from app.db.session import SessionLocal
from app.models.manual import Manual
from app.modules.ai_gateway import ids
from app.modules.ai_gateway import provider as ai_provider
from app.modules.ai_gateway.errors import AIRequestRejected
from app.modules.ai_gateway.paths import shared_path
from app.modules.assistant.rag_index import index_pdf
from app.storage.files import resolve_media_path

logger = logging.getLogger("fibo.pipeline.manual")


def _pages_text(pages: list[int]) -> str:
    shown = ", ".join(map(str, pages[:20]))
    return shown + (" …" if len(pages) > 20 else "")


async def _record_failure(manual_id: int, exc: Exception) -> None:
    """Mark FAILED in a fresh session; if even that fails, log it (the startup sweep fixes the row)."""
    try:
        async with SessionLocal() as session:
            manual = await session.get(Manual, manual_id)
            if manual is not None:
                manual.index_status = IndexStatus.FAILED
                manual.error_message = f"{type(exc).__name__}: {str(exc)[:200]}"
                await session.commit()
    except Exception:  # logged with traceback; the startup sweep marks the row FAILED
        logger.exception("could not record manual failure", extra={"manual_id": manual_id})


async def _not_sent() -> None:
    return None


async def _send_to_ai(manual: Manual) -> None:
    """Never raises: the AI index is an extra, the backend's index is already READY or FAILED."""
    request = {
        "manual_id": ids.manual_id(manual.id),
        "machine_id": ids.m_id(manual.machine_id),
        "file_path": shared_path(manual.file_path),
    }
    try:
        outcome = await ai_provider.index_manual(request, _not_sent)
    except (AIRequestRejected, OSError) as exc:  # logged; the incident path falls back to the builtin card
        logger.warning("AI service did not index manual %s: %s", manual.id, exc)
        return
    status = outcome.value[0].value if outcome.value else None
    logger.info(
        "manual sent to AI index",
        extra={"manual_id": manual.id, "ai_status": status, "degraded": outcome.degraded},
    )


async def index_manual(manual_id: int) -> None:
    try:
        async with SessionLocal() as session:
            manual = await session.get(Manual, manual_id)
            if manual is None:  # machine or manual deleted before the task ran
                logger.warning("manual to index no longer exists", extra={"manual_id": manual_id})
                return
            manual.index_status, manual.error_message = IndexStatus.INDEXING, None
            await session.commit()
            pdf = await asyncio.to_thread(
                index_pdf, resolve_media_path(manual.file_path), manual.machine_id, manual.id
            )
            manual.page_count = len(pdf.pages)
            if len(pdf.scanned_pages) == len(pdf.pages):
                manual.index_status = IndexStatus.FAILED
                manual.error_message = "No extractable text: the PDF looks scanned (OCR is not supported yet)"
            else:
                manual.index_status = IndexStatus.READY
                if pdf.scanned_pages:
                    manual.error_message = (
                        f"Warning: pages without text (scanned?): {_pages_text(pdf.scanned_pages)}"
                    )
            await session.commit()
            logger.info(
                "manual indexed",
                extra={
                    "manual_id": manual_id,
                    "pages": manual.page_count,
                    "status": manual.index_status.value,
                },
            )
            if ai_provider.sidecar_enabled() and manual.index_status == IndexStatus.READY:
                await _send_to_ai(manual)
    except Exception as exc:  # recorded on the manual row, never swallowed
        logger.exception("manual indexing failed", extra={"manual_id": manual_id})
        await _record_failure(manual_id, exc)
