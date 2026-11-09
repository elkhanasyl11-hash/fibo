from pydantic import ConfigDict, Field

from fibo_ai.schemas.common import BaseResponse, FiboBaseModel, Lang


class ManualIndexRequest(FiboBaseModel):
    manual_id: str = Field(..., description="Unique manual identifier")
    machine_id: str = Field(..., description="Target machine ID")
    file_path: str = Field(..., description="Path to PDF manual in FIBO_SHARED_DIR")
    language: Lang = Field(Lang.ru, description="Primary manual language")


class ManualStatusResponse(BaseResponse):
    manual_id: str
    machine_id: str
    status: str = Field(..., description="Status: 'indexing', 'ready', 'failed'")
    pages_indexed: int = Field(0, description="Total pages chunked and vectorized")
    error: str | None = Field(None, description="Failure details if status is 'failed'")


class ManualQueryRequest(FiboBaseModel):
    machine_id: str
    query: str
    top_k: int = Field(5, description="Number of passages to retrieve")


class ManualFragment(FiboBaseModel):
    page: int = Field(..., description="Cited document page number")
    section: str = Field("General", description="Section heading")
    snippet: str = Field(..., description="Retrieved excerpt text")
    score: float = Field(..., description="Vector/BM25 similarity score")


class ManualQueryResponse(BaseResponse):
    machine_id: str
    fragments: list[ManualFragment] = Field(default_factory=list)
    general_safety_fallback: bool = Field(
        False, description="True if no relevant page was found and profile safety rules were used"
    )

    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "example": {
                "request_id": "req-rag-01",
                "machine_id": "ЧПУ-2",
                "fragments": [
                    {
                        "page": 47,
                        "section": "7.3 Система смазки шпинделя",
                        "snippet": "При появлении высокочастотного шума или запаха гари немедленно отключите шпиндель. Проверьте уровень масла в маслостанции №2.",
                        "score": 0.884,
                    }
                ],
                "general_safety_fallback": False,
                "degraded": [],
            }
        },
    )
