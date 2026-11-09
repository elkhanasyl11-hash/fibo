import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError

from fibo_ai.api.deps import verify_auth_token
from fibo_ai.api.routers import (
    anomaly,
    assistant,
    audio,
    incident,
    manuals,
    meta,
    risk,
    speech,
    vision,
)
from fibo_ai.core.errors import (
    FiboError,
    fibo_error_handler,
    validation_error_handler,
)
from fibo_ai.core.logging import get_logger, request_id_ctx, setup_logging
from fibo_ai.settings import get_settings

logger = get_logger("fibo_ai.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings.log_level)
    mode_str = "STUB" if settings.ai_stub_mode else "LIVE"
    logger.info(f"Starting Fibo AI Service v{settings.model_version} [{mode_str} MODE]")
    yield
    logger.info("Shutting down Fibo AI Service")


app = FastAPI(
    title="Fibo AI/ML Service",
    description="Stateless predictive maintenance and operator assistant service for sensorless workshops.",
    version="0.1.0",
    lifespan=lifespan,
    dependencies=[Depends(verify_auth_token)],
)

# Exception handlers
app.add_exception_handler(FiboError, fibo_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    req_id = request.headers.get("X-Request-ID") or f"req-{uuid.uuid4().hex[:8]}"
    token = request_id_ctx.set(req_id)
    start_time = time.time()
    try:
        response: Response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000.0
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
        return response
    finally:
        request_id_ctx.reset(token)


# Register routers
app.include_router(meta.router)
app.include_router(risk.router)
app.include_router(anomaly.router)
app.include_router(audio.router)
app.include_router(speech.router)
app.include_router(vision.router)
app.include_router(manuals.router)
app.include_router(incident.router)
app.include_router(assistant.router)
