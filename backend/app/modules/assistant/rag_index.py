"""Fibo Assistant: turning a PDF manual into searchable chunks (and the profile knowledge notes).

PDF -> chunks:
  1. PyMuPDF extracts the text of every page.
  2. A page with fewer than 50 characters is probably a scan (an image of text). OCR is out of
     scope for the MVP: such pages are listed in manuals.error_message as a warning.
  3. Each page is cut into chunks of ~800 characters with 150 characters overlap. A chunk never
     crosses a page boundary, so every chunk has exactly one page number to cite. Cuts are moved
     back to the nearest space so words are not split.
  4. Chunks are embedded as "passage: ..." and stored in the Chroma collection "manuals" with
     metadata machine_id, manual_id, page. Re-indexing a manual first deletes its old chunks.
Profile knowledge (app/profiles/kb/<profile>.md, "## " sections: symptom -> cause -> action) goes into
the collection "profile_kb" with metadata profile; it has no page numbers and is never cited as a page.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.modules.assistant.chroma import kb_collection, manuals_collection
from app.modules.assistant.embeddings import get_embedder

CHUNK_CHARS = 800
OVERLAP_CHARS = 150
SCANNED_PAGE_CHARS = 50
KB_DIR = Path(__file__).resolve().parents[2] / "profiles" / "kb"


@dataclass
class PdfText:
    pages: list[str]  # index 0 = page 1
    scanned_pages: list[int]  # 1-based page numbers with (almost) no text


def extract_pages(pdf_path: Path) -> PdfText:
    with pymupdf.open(pdf_path) as document:
        pages = [re.sub(r"\s+", " ", page.get_text()).strip() for page in document]
    scanned = [number for number, text in enumerate(pages, 1) if len(text) < SCANNED_PAGE_CHARS]
    return PdfText(pages, scanned)


def chunk_page(text: str) -> list[str]:
    """~800-character pieces with 150 overlap, cut at a space when possible."""
    chunks, start = [], 0
    while start < len(text):
        end = min(start + CHUNK_CHARS, len(text))
        if end < len(text):
            space = text.rfind(" ", start + CHUNK_CHARS // 2, end)
            end = space if space > 0 else end
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - OVERLAP_CHARS, start + 1)
    return [c for c in chunks if c]


def index_pdf(pdf_path: Path, machine_id: int, manual_id: int) -> PdfText:
    """Extract, chunk, embed and store one manual. CPU work: call via asyncio.to_thread."""
    pdf = extract_pages(pdf_path)
    ids, texts, metadatas = [], [], []
    for number, page_text in enumerate(pdf.pages, 1):
        if number in pdf.scanned_pages:
            continue
        for index, chunk in enumerate(chunk_page(page_text)):
            ids.append(f"manual{manual_id}-p{number}-c{index}")
            texts.append(chunk)
            metadatas.append({"machine_id": machine_id, "manual_id": manual_id, "page": number})
    collection = manuals_collection()
    collection.delete(where={"manual_id": manual_id})
    if texts:
        collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=get_embedder().embed_passages(texts).tolist(),
        )
    return pdf


def read_kb_notes(profile_id: str) -> list[str]:
    path = KB_DIR / f"{profile_id}.md"
    if not path.exists():
        return []
    sections = re.split(r"^## ", path.read_text(encoding="utf-8"), flags=re.MULTILINE)[1:]
    return [re.sub(r"\s+", " ", section).strip() for section in sections if section.strip()]


def index_profile_kb(profile_ids: list[str]) -> int:
    """(Re)load the knowledge notes of every profile. Called once at startup."""
    collection, total = kb_collection(), 0
    for profile_id in profile_ids:
        notes = read_kb_notes(profile_id)
        collection.delete(where={"profile": profile_id})
        if notes:
            collection.add(
                ids=[f"kb-{profile_id}-{i}" for i in range(len(notes))],
                documents=notes,
                metadatas=[{"profile": profile_id} for _ in notes],
                embeddings=get_embedder().embed_passages(notes).tolist(),
            )
            total += len(notes)
    return total
