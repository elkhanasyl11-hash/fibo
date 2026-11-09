"""PDF metadata-preserving text extraction and page/section chunking."""

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from fibo_ai.core.errors import ModelNotReadyError


class ManualChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    machine_id: str
    manual_id: str
    page: int
    section: str
    language: str
    text: str
    embedding: list[float] | None = None


def chunk_page(
    *,
    machine_id: str,
    manual_id: str,
    page: int,
    language: str,
    text: str,
    max_chars: int = 700,
    overlap: int = 100,
) -> list[ManualChunk]:
    normalized = re.sub(r"[ \t]+", " ", text).strip()
    if not normalized:
        return []
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    section = "General"
    if lines and (len(lines[0]) < 160):
        section = lines[0][:160]
    chunks: list[ManualChunk] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + max_chars)
        if end < len(normalized):
            boundary = normalized.rfind(" ", start + max_chars // 2, end)
            if boundary > start:
                end = boundary
        value = normalized[start:end].strip()
        if value:
            chunks.append(
                ManualChunk(
                    machine_id=machine_id,
                    manual_id=manual_id,
                    page=page,
                    section=section,
                    language=language,
                    text=value,
                )
            )
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap)
    return chunks


def extract_pdf_pages(path: Path) -> list[tuple[int, str]]:
    if path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("PDF exceeds 50 MB")
    if path.read_bytes()[:5] != b"%PDF-":
        raise ValueError("Unsupported media: expected a PDF")
    try:
        import fitz
    except ImportError as exc:
        raise ModelNotReadyError("PyMuPDF is required to ingest PDF manuals (install the rag extra)") from exc
    pages: list[tuple[int, str]] = []
    with fitz.open(path) as document:
        for index, page in enumerate(document, start=1):
            pages.append((index, page.get_text("text")))
    return pages
