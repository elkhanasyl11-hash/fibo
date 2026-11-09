"""FastAPI application entry point: wiring only, no business logic.

Startup (lifespan): configure logging, create data folders, load + validate industry profiles
(the app refuses to start on an invalid YAML), load the risk model or fall back to index-only mode,
load the profile knowledge notes into the vector store (skipped with a warning if the embedding
model is unavailable).
Then the periodic risk recompute starts (app/modules/machine/scheduler.py).
Shutdown: stop it, close database connections.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import ModelUnavailableError, register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestIDMiddleware
from app.db.session import engine, ensure_sqlite_dir
from app.modules.assistant.rag_index import index_profile_kb
from app.modules.machine import scheduler
from app.modules.machine.risk_model import RiskModel, set_active_model
from app.pipelines.recovery import fail_interrupted_work
from app.profiles.loader import get_profiles


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    for reason in settings.insecure_reasons():  # prod refuses to start (config.py); dev just warns
        logging.getLogger("fibo.startup").warning("insecure setting (fine for local dev only): %s", reason)
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    ensure_sqlite_dir(settings.database_url)
    app.state.profiles = get_profiles()  # fail fast on invalid YAML
    await fail_interrupted_work()  # rows a restart left in RECEIVED/PROCESSING/INDEXING -> FAILED
    set_active_model(RiskModel.load_or_none(settings.risk_model_dir))  # None -> index-only mode, logged
    try:  # profile knowledge notes into the vector store; the app still works without them
        notes = await asyncio.to_thread(index_profile_kb, [p.value for p in app.state.profiles])
        logging.getLogger("fibo.startup").info("profile knowledge indexed", extra={"notes": notes})
    except ModelUnavailableError:
        logging.getLogger("fibo.startup").warning(
            "embedding model unavailable: profile knowledge not indexed"
        )
    recompute_task = asyncio.create_task(scheduler.run_forever())  # periodic risk (scheduler.py)
    yield
    recompute_task.cancel()
    await engine.dispose()


app = FastAPI(title="Fibo API", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)
app.include_router(api_router, prefix="/api/v1")
