from typing import Any

from pydantic import Field

from fibo_ai.schemas.common import BaseResponse, FiboBaseModel


class HealthResponse(FiboBaseModel):
    status: str = Field("ok", description="Service liveness status")
    timestamp: str = Field(..., description="Current ISO-8601 UTC timestamp")


class ReadyResponse(FiboBaseModel):
    ready: bool = Field(..., description="True if all models and storage are ready for inference")
    models_loaded: dict[str, bool] = Field(default_factory=dict)
    storage_ready: bool = Field(True)


class ModelMetaInfo(FiboBaseModel):
    name: str
    version: str
    description: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class ModelsMetaResponse(BaseResponse):
    models: list[ModelMetaInfo] = Field(default_factory=list)
    system_metrics: dict[str, Any] = Field(default_factory=dict)
