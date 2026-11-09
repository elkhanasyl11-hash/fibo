"""Fibo Assistant: retrieval over machine manuals (RAG) with page numbers.

retrieve(session, machine_id, query, profile_id):
  - embeds "query: <symptom + machine type/model>" with the same e5 model as the chunks;
  - asks Chroma for the 5 nearest chunks of THIS MACHINE'S manuals that are READY in the database
    (filter machine_id + manual_id). The manual-id filter matters: when a machine or workshop is
    deleted its chunks stay in Chroma, and SQLite may give the next new machine the same id;
  - keeps only chunks with cosine similarity >= FIBO_RAG_MIN_SIMILARITY. If none is left the result is
    "not found in the manual" and the card must say so (card.GENERAL_SAFETY_ADVICE);
  - also returns up to 3 profile knowledge notes (no page numbers, never cited as pages).
The card may only cite pages that are in `chunks` (card.finalize drops every other page).
page_excerpts() returns the text of cited pages for the bot's "📖 Manual page" button.
Chroma and the embedder are synchronous, so that work runs in a thread.
"""

import asyncio
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import IndexStatus
from app.models.manual import Manual
from app.modules.assistant.chroma import kb_collection, manuals_collection
from app.modules.assistant.embeddings import get_embedder

TOP_K = 5
KB_TOP_K = 3
EXCERPT_CHARS = 900


@dataclass
class ManualChunk:
    page: int
    text: str
    similarity: float


@dataclass
class RagResult:
    found: bool
    chunks: list[ManualChunk] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # profile knowledge, not citable as pages

    @property
    def pages(self) -> set[int]:
        return {chunk.page for chunk in self.chunks}


async def ready_manual_ids(session: AsyncSession, machine_id: int) -> list[int]:
    stmt = select(Manual.id).where(Manual.machine_id == machine_id, Manual.index_status == IndexStatus.READY)
    return list((await session.scalars(stmt)).all())


def _manual_filter(machine_id: int, manual_ids: list[int]) -> list[dict]:
    return [{"machine_id": machine_id}, {"manual_id": {"$in": manual_ids}}]


def _query(collection, vector, where: dict, k: int) -> list[tuple[str, dict, float]]:
    if collection.count() == 0:
        return []
    result = collection.query(
        query_embeddings=[vector.tolist()],
        n_results=k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    return [
        (doc, meta, 1.0 - dist)  # cosine distance -> similarity
        for doc, meta, dist in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0], strict=True
        )
    ]


def _retrieve_sync(machine_id: int, manual_ids: list[int], query: str, profile_id: str | None) -> RagResult:
    vector = get_embedder().embed_query(query)
    hits = []
    if manual_ids:
        hits = _query(manuals_collection(), vector, {"$and": _manual_filter(machine_id, manual_ids)}, TOP_K)
    chunks = [
        ManualChunk(int(meta["page"]), doc, round(sim, 4))
        for doc, meta, sim in hits
        if sim >= settings.rag_min_similarity
    ]
    notes = []
    if profile_id:
        notes = [
            doc
            for doc, _meta, sim in _query(kb_collection(), vector, {"profile": profile_id}, KB_TOP_K)
            if sim >= settings.rag_min_similarity
        ]
    return RagResult(found=bool(chunks), chunks=chunks, notes=notes)


async def retrieve(
    session: AsyncSession, machine_id: int, query: str, profile_id: str | None = None
) -> RagResult:
    manual_ids = await ready_manual_ids(session, machine_id)
    return await asyncio.to_thread(_retrieve_sync, machine_id, manual_ids, query, profile_id)


def _excerpts_sync(machine_id: int, manual_ids: list[int], pages: list[int]) -> list[dict]:
    collection = manuals_collection()
    if not pages or not manual_ids or collection.count() == 0:
        return []
    found = collection.get(
        where={"$and": [*_manual_filter(machine_id, manual_ids), {"page": {"$in": pages}}]},
        include=["documents", "metadatas"],
    )
    by_page: dict[int, list[str]] = {}
    for doc, meta in zip(found["documents"], found["metadatas"], strict=True):
        by_page.setdefault(int(meta["page"]), []).append(doc)
    return [{"page": page, "text": " … ".join(by_page[page])[:EXCERPT_CHARS]} for page in sorted(by_page)]


async def page_excerpts(session: AsyncSession, machine_id: int, pages: list[int]) -> list[dict]:
    manual_ids = await ready_manual_ids(session, machine_id)
    return await asyncio.to_thread(_excerpts_sync, machine_id, manual_ids, pages)
