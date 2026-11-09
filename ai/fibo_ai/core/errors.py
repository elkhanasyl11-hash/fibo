from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from fibo_ai.schemas.common import ErrorDetail, ErrorResponse


class FiboError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        retriable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retriable = retriable
        self.details = details or {}


class FileTooLargeError(FiboError):
    def __init__(
        self,
        message: str = "Submitted file exceeds size limit",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("FILE_TOO_LARGE", message, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, False, details)


class UnsupportedMediaError(FiboError):
    def __init__(self, message: str = "Unsupported media format", details: dict[str, Any] | None = None) -> None:
        super().__init__("UNSUPPORTED_MEDIA", message, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, False, details)


class AudioTooShortError(FiboError):
    def __init__(
        self,
        message: str = "Audio duration is below minimum threshold (3 s)",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("AUDIO_TOO_SHORT", message, status.HTTP_422_UNPROCESSABLE_ENTITY, True, details)


class AudioSilentError(FiboError):
    def __init__(
        self,
        message: str = "Audio RMS energy below noise floor (silent recording)",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("AUDIO_SILENT", message, status.HTTP_422_UNPROCESSABLE_ENTITY, True, details)


class PhotoQualityLowError(FiboError):
    def __init__(self, message: str = "Photo rejected by quality gate", details: dict[str, Any] | None = None) -> None:
        super().__init__("PHOTO_QUALITY_LOW", message, status.HTTP_422_UNPROCESSABLE_ENTITY, True, details)


class ASRLowConfidenceError(FiboError):
    def __init__(
        self,
        message: str = "Speech recognition confidence too low or hallucination flagged",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("ASR_LOW_CONFIDENCE", message, status.HTTP_422_UNPROCESSABLE_ENTITY, True, details)


class MachineAmbiguousError(FiboError):
    def __init__(
        self,
        message: str = "Machine identification is ambiguous",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("MACHINE_AMBIGUOUS", message, status.HTTP_422_UNPROCESSABLE_ENTITY, True, details)


class BaselineMissingError(FiboError):
    def __init__(
        self,
        message: str = "No baseline artifact found for machine",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("BASELINE_MISSING", message, status.HTTP_404_NOT_FOUND, False, details)


class BaselineVersionMismatchError(FiboError):
    def __init__(
        self,
        message: str = "Baseline was created with different embedder version or corrupted blob",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("BASELINE_VERSION_MISMATCH", message, status.HTTP_409_CONFLICT, True, details)


class ManualNotIndexedError(FiboError):
    def __init__(
        self,
        message: str = "Manual for machine is not yet indexed in vector store",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("MANUAL_NOT_INDEXED", message, status.HTTP_404_NOT_FOUND, False, details)


class LLMUnavailableError(FiboError):
    def __init__(
        self,
        message: str = "Upstream LLM provider unavailable or timeout exceeded",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("LLM_UNAVAILABLE", message, status.HTTP_503_SERVICE_UNAVAILABLE, True, details)


class ModelNotReadyError(FiboError):
    def __init__(
        self,
        message: str = "Required model weights or indices are not loaded",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("MODEL_NOT_READY", message, status.HTTP_503_SERVICE_UNAVAILABLE, True, details)


async def fibo_error_handler(_: Request, exc: FiboError) -> JSONResponse:
    content = ErrorResponse(
        error=ErrorDetail(
            code=exc.code,
            message=exc.message,
            retriable=exc.retriable,
            details=exc.details,
        )
    ).model_dump()
    return JSONResponse(status_code=exc.status_code, content=content)


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    content = ErrorResponse(
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message="Request body or query parameter validation failed",
            retriable=False,
            details={"errors": exc.errors()},
        )
    ).model_dump()
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=content)
