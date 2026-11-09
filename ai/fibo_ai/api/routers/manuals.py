from fastapi import APIRouter, Depends

from fibo_ai.api.deps import get_ai
from fibo_ai.facade import FiboAI
from fibo_ai.schemas.rag import (
    ManualIndexRequest,
    ManualQueryRequest,
    ManualQueryResponse,
    ManualStatusResponse,
)

router = APIRouter(prefix="/v1/manuals", tags=["Manuals RAG"])


@router.post("/index", response_model=ManualStatusResponse)
async def index_manual(req: ManualIndexRequest, ai: FiboAI = Depends(get_ai)) -> ManualStatusResponse:
    """Ingest, OCR/extract, chunk, and embed a PDF machine manual into vector store."""
    return await ai.rag.index_manual(req)


@router.get("/{manual_id}/status", response_model=ManualStatusResponse)
async def get_manual_status(manual_id: str, ai: FiboAI = Depends(get_ai)) -> ManualStatusResponse:
    """Check background indexing status of machine manual."""
    return await ai.rag.get_manual_status(manual_id)


@router.post("/query", response_model=ManualQueryResponse)
async def query_manual(req: ManualQueryRequest, ai: FiboAI = Depends(get_ai)) -> ManualQueryResponse:
    """Retrieve top-K manual passages with verified page citations and general safety fallback."""
    return await ai.rag.query_manual(req)
