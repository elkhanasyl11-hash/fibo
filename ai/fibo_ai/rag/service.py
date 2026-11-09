"""Manual indexing and retrieval facade."""

import asyncio
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

from fibo_ai.core.errors import FiboError
from fibo_ai.core.llm.base import LLMClient
from fibo_ai.rag.embed import MultilingualE5Small, TextEmbedder
from fibo_ai.rag.index import read_machine_index, upsert_manual
from fibo_ai.rag.ingest import ManualChunk, chunk_page, extract_pdf_pages
from fibo_ai.rag.retrieve import retrieve_chunks
from fibo_ai.schemas.common import Usage
from fibo_ai.schemas.rag import (
    ManualIndexRequest,
    ManualQueryRequest,
    ManualQueryResponse,
    ManualStatusResponse,
)
from fibo_ai.settings import Settings


class RAGService:
    def __init__(self, settings: Settings, llm: LLMClient | None = None) -> None:
        self.settings = settings
        self.llm = llm
        self.root = Path(settings.fibo_data_dir) / "rag"
        self._embedder: TextEmbedder | None = None
        self._embedder_checked = False

    def _get_embedder(self) -> TextEmbedder | None:
        if self._embedder_checked:
            return self._embedder
        self._embedder_checked = True
        try:
            self._embedder = MultilingualE5Small(Path(self.settings.fibo_data_dir) / "models" / "multilingual-e5")
        except Exception:
            self._embedder = None
        return self._embedder

    def _status_path(self, manual_id: str) -> Path:
        return self.root / "status" / f"{quote(manual_id, safe='')}.json"

    def _write_status(
        self,
        *,
        manual_id: str,
        machine_id: str,
        status: str,
        pages_indexed: int = 0,
        error: str | None = None,
    ) -> ManualStatusResponse:
        response = ManualStatusResponse(
            request_id=f"rag-{uuid.uuid4().hex[:8]}",
            model_version=self.settings.model_version,
            config_version=self.settings.config_version,
            manual_id=manual_id,
            machine_id=machine_id,
            status=status,
            pages_indexed=pages_indexed,
            error=error,
        )
        path = self._status_path(manual_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(response.model_dump_json(indent=2), encoding="utf-8")
        return response

    def index_pages(
        self,
        manual_id: str,
        machine_id: str,
        language: str,
        pages: list[tuple[int, str]],
        *,
        source: str = "manual",
    ) -> ManualStatusResponse:
        config_path = Path("configs/rag.yaml")
        config: dict[str, Any] = (
            yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        ) or {}
        chunk_config = config.get("retrieval", {})
        chunks: list[ManualChunk] = []
        indexed_pages = 0
        for page_number, page_text in pages:
            page_chunks = chunk_page(
                machine_id=machine_id,
                manual_id=manual_id,
                page=page_number,
                language=language,
                text=page_text,
                max_chars=int(chunk_config.get("chunk_chars", 700)),
                overlap=int(chunk_config.get("overlap_chars", 100)),
            )
            if page_chunks:
                indexed_pages += 1
                chunks.extend(page_chunks)
        if not chunks:
            return self._write_status(
                manual_id=manual_id,
                machine_id=machine_id,
                status="failed",
                error="No text pages were extracted; scanned PDF OCR is unavailable.",
            )
        embedder = self._get_embedder()
        if embedder is not None:
            try:
                vectors = embedder.embed_passages([chunk.text for chunk in chunks])
                for chunk, vector in zip(chunks, vectors, strict=True):
                    chunk.embedding = vector
            except Exception:
                embedder = None
        upsert_manual(self.root, machine_id, manual_id, chunks)
        response = self._write_status(
            manual_id=manual_id,
            machine_id=machine_id,
            status="ready",
            pages_indexed=indexed_pages,
        )
        response.degraded = ["lexical_rag_fallback_embedder_unavailable"] if embedder is None else []
        if source != "manual":
            response.degraded.append("fixture_manual_not_a_real_manual")
        return response

    async def index_manual(self, req: ManualIndexRequest) -> ManualStatusResponse:
        self._write_status(manual_id=req.manual_id, machine_id=req.machine_id, status="indexing")
        try:
            path = Path(req.file_path)
            if not path.is_absolute():
                path = Path(self.settings.fibo_shared_dir) / path
            path = path.resolve()
            shared = Path(self.settings.fibo_shared_dir).resolve()
            if shared not in path.parents or not path.is_file():
                raise FiboError("INVALID_FILE_PATH", "Manual must be in FIBO_SHARED_DIR", 400)
            pages = await asyncio.to_thread(extract_pdf_pages, path)
            if not any(text.strip() for _, text in pages):
                return self._write_status(
                    manual_id=req.manual_id,
                    machine_id=req.machine_id,
                    status="failed",
                    error="No selectable text found; scanned-page OCR is unavailable.",
                )
            response = await asyncio.to_thread(
                self.index_pages,
                req.manual_id,
                req.machine_id,
                req.language.value,
                pages,
            )
            return response
        except FiboError as exc:
            self._write_status(
                manual_id=req.manual_id,
                machine_id=req.machine_id,
                status="failed",
                error=exc.code,
            )
            raise
        except Exception as exc:
            return self._write_status(
                manual_id=req.manual_id,
                machine_id=req.machine_id,
                status="failed",
                error=f"Manual indexing failed: {type(exc).__name__}",
            )

    async def get_manual_status(self, manual_id: str) -> ManualStatusResponse:
        path = self._status_path(manual_id)
        if not path.is_file():
            raise FiboError("MANUAL_NOT_INDEXED", "Manual status is not available", 404, False)
        try:
            return ManualStatusResponse.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise FiboError("MANUAL_NOT_INDEXED", "Manual status record is corrupt", 404) from exc

    async def query_manual(self, req: ManualQueryRequest) -> ManualQueryResponse:
        chunks = await asyncio.to_thread(read_machine_index, self.root, req.machine_id)
        config_path = Path("configs/rag.yaml")
        config: dict[str, Any] = (
            yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        ) or {}
        min_score = float(config.get("retrieval", {}).get("min_score", 0.15))
        embedder = await asyncio.to_thread(self._get_embedder)
        query_embedding: list[float] | None = None
        if embedder is not None:
            try:
                query_embedding = (await asyncio.to_thread(embedder.embed_query, req.query)).tolist()
            except Exception:
                query_embedding = None
        fragments = await asyncio.to_thread(
            retrieve_chunks,
            chunks,
            req.query,
            min(req.top_k, int(config.get("retrieval", {}).get("top_k", 5))),
            query_embedding,
        )
        fragments = [fragment for fragment in fragments if fragment.score >= min_score]
        return ManualQueryResponse(
            request_id=f"rag-{uuid.uuid4().hex[:8]}",
            model_version=self.settings.model_version,
            config_version=self.settings.config_version,
            machine_id=req.machine_id,
            fragments=fragments,
            general_safety_fallback=not bool(fragments),
            usage=Usage(embed_calls=1),
        )
