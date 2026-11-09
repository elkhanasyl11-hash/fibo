"""Response schema of GET /health."""

from typing import Any, Literal

from pydantic import BaseModel


class HealthRead(BaseModel):
    status: Literal["ok", "error"]  # "error" only when the database is unreachable (HTTP 503)
    database: Literal["ok", "error"]
    risk_model_loaded: bool  # False = index-only mode (no trained model artifacts)
    risk_model_version: str
    ai_mode: Literal["mock", "live"]
    chroma: Literal["ok", "error"]  # RAG vector store (data/chroma)
    profiles_loaded: int
    ai_provider: Literal["sidecar", "builtin"]  # FIBO_AI_PROVIDER
    ai_sidecar: Literal["ready", "unreachable", "disabled"]  # disabled = builtin provider
    ai_models: dict[str, Any] | None = None  # AI service /v1/meta/models (cached 60 s), None if unknown
