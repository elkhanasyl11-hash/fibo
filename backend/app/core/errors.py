"""Error hierarchy and the exception handlers that turn errors into one JSON shape.

Every error response looks like:
    {"error": {"code": "not_found", "message": "...", "details": {}, "request_id": "..."}}

Business code raises an AppError subclass (e.g. NotFoundError). The handlers below convert it,
FastAPI's validation errors, Starlette HTTP errors (unknown route, wrong method) and any unexpected
exception into that shape. Unexpected exceptions get a generic message: the traceback goes to the
log (with the request id), never to the client.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

logger = logging.getLogger("fibo.errors")


class AppError(Exception):
    """Base class for errors we raise on purpose. Subclasses set status_code and code."""

    status_code: int = 400
    code: str = "app_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class DomainValidationError(AppError):
    status_code = 422
    code = "validation_failed"


class UnsupportedMediaError(AppError):
    status_code = 415
    code = "unsupported_media"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


class AuthError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class TooManyRequestsError(AppError):
    status_code = 429
    code = "too_many_requests"


class ExternalServiceError(AppError):
    status_code = 502
    code = "external_service_error"


class ModelUnavailableError(AppError):
    status_code = 503
    code = "model_unavailable"


# Codes for errors raised by Starlette itself (unknown URL, wrong HTTP method, ...).
_HTTP_STATUS_CODES = {401: "unauthorized", 404: "not_found", 405: "method_not_allowed"}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or request_id_var.get()


def error_response(
    request: Request, status_code: int, code: str, message: str, details: dict
) -> JSONResponse:
    """Build the single error JSON shape used by the whole API."""
    request_id = _request_id(request)
    body = {"error": {"code": code, "message": message, "details": details, "request_id": request_id}}
    return JSONResponse(status_code=status_code, content=body, headers={"X-Request-ID": request_id})


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    logger.info("app error", extra={"code": exc.code, "status": exc.status_code, "error": exc.message})
    return error_response(request, exc.status_code, exc.code, exc.message, exc.details)


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Keep only location, message and type: the raw error may contain objects that are not JSON.
    fields = [
        {
            "loc": [str(part) for part in err.get("loc", [])],
            "msg": err.get("msg", ""),
            "type": err.get("type", ""),
        }
        for err in exc.errors()
    ]
    return error_response(request, 422, "validation_failed", "Request validation failed", {"fields": fields})


async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_STATUS_CODES.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    return error_response(request, exc.status_code, code, message, {})


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # This handler runs outside RequestIDMiddleware, so restore the id for the log line first.
    request_id_var.set(_request_id(request))
    logger.error("unhandled exception", exc_info=exc, extra={"path": request.url.path})
    return error_response(request, 500, "internal_error", "Internal server error", {})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
