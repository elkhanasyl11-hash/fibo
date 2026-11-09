"""RAG building blocks: chunking, PDF text, retrieval per machine, page excerpts, profile notes."""

from app.db.base import IndexStatus
from app.models import Manual
from app.modules.assistant import rag
from app.modules.assistant.rag_index import (
    CHUNK_CHARS,
    chunk_page,
    extract_pages,
    index_pdf,
    index_profile_kb,
    read_kb_notes,
)
from tests.pdf_samples import standard_manual


def test_chunks_are_bounded_and_overlap():
    text = " ".join(f"слово{i}" for i in range(600))
    chunks = chunk_page(text)
    assert len(chunks) > 3 and all(len(c) <= CHUNK_CHARS for c in chunks)
    assert chunks[0][-60:].split()[-1] in chunks[1]  # consecutive chunks overlap
    assert chunk_page("короткий текст") == ["короткий текст"]
    assert chunk_page("") == []


def test_pdf_pages_and_scanned_detection(tmp_path):
    path = tmp_path / "m.pdf"
    path.write_bytes(standard_manual())
    pdf = extract_pages(path)
    assert len(pdf.pages) == 4 and pdf.scanned_pages == [4]
    assert "шпиндель гудит" in pdf.pages[1]


async def _machine_with_ready_manual(session, make_workshop, make_machine, tmp_path) -> tuple[int, int]:
    machine = await make_machine((await make_workshop())["id"])
    path = tmp_path / "m.pdf"
    path.write_bytes(standard_manual())
    manual = Manual(
        machine_id=machine["id"],
        file_path="manual/x.pdf",
        original_filename="x.pdf",
        index_status=IndexStatus.READY,
    )
    session.add(manual)
    await session.commit()
    index_pdf(path, machine_id=machine["id"], manual_id=manual.id)
    return machine["id"], manual.id


async def test_retrieval_is_per_machine_with_pages(tmp_path, session, make_workshop, make_machine):
    machine_id, manual_id = await _machine_with_ready_manual(session, make_workshop, make_machine, tmp_path)
    path = tmp_path / "m.pdf"

    hit = await rag.retrieve(session, machine_id, "шпиндель гудит на высоких оборотах, подшипники")
    assert hit.found and hit.chunks[0].page == 2 and 2 in hit.pages
    assert all(c.similarity >= 0.2 for c in hit.chunks)
    other_machine = await rag.retrieve(
        session, machine_id + 1000, "шпиндель гудит на высоких оборотах, подшипники"
    )
    assert not other_machine.found  # another machine's manual is never used
    unrelated = await rag.retrieve(session, machine_id, "рецепт хлеба")
    assert not unrelated.found

    excerpts = await rag.page_excerpts(session, machine_id, [2, 77])
    assert [e["page"] for e in excerpts] == [2] and "смазку" in excerpts[0]["text"]

    index_pdf(path, machine_id=machine_id, manual_id=manual_id)  # re-index: no duplicate chunks
    again = await rag.retrieve(session, machine_id, "шпиндель гудит на высоких оборотах, подшипники")
    assert len(again.chunks) == len(hit.chunks)


async def test_chunks_of_deleted_manuals_are_ignored(tmp_path, session, make_workshop, make_machine):
    """A deleted machine's chunks stay in Chroma; a new machine reusing its id must not see them."""
    machine_id, manual_id = await _machine_with_ready_manual(session, make_workshop, make_machine, tmp_path)
    await session.delete(await session.get(Manual, manual_id))
    await session.commit()
    stale = await rag.retrieve(session, machine_id, "шпиндель гудит на высоких оборотах, подшипники")
    assert not stale.found
    assert await rag.page_excerpts(session, machine_id, [2]) == []


async def test_profile_knowledge_notes(session):
    assert len(read_kb_notes("metalworking")) == 5
    assert index_profile_kb(["metalworking", "bakery"]) >= 8
    result = await rag.retrieve(session, 424242, "гул шпинделя на высоких оборотах", "metalworking")
    assert not result.found and result.pages == set()  # notes are context, not citable pages
    assert any("подшипников шпинделя" in note for note in result.notes)
