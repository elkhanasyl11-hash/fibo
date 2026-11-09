"""Shared test setup.

Environment variables are set BEFORE any app import, because app.core.config.settings and the
database engine are created at import time. Every test run gets a fresh temporary folder with its
own SQLite file, so tests never touch data/ and never call external services (FIBO_AI_MODE=mock).

Tables are created with Base.metadata.create_all (allowed in tests only; the real app uses Alembic).
"""

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="fibo-test-"))
os.environ["FIBO_ENV"] = "test"
os.environ["FIBO_AI_MODE"] = "mock"
os.environ["FIBO_DATA_DIR"] = str(_TMP / "data")
os.environ["FIBO_DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP / 'test.db'}"
os.environ["FIBO_RISK_MODEL_DIR"] = str(_TMP / "no-artifacts")
os.environ["FIBO_BOT_SHARED_SECRET"] = "test-bot-secret"
os.environ["FIBO_EMBEDDING_BACKEND"] = "hash"  # no model download in tests
os.environ["FIBO_RAG_MIN_SIMILARITY"] = "0.2"  # hash vectors measure word overlap, on a lower scale
os.environ["FIBO_RISK_RECOMPUTE_MINUTES"] = "0"  # no background loop in tests (tested directly)

import httpx  # noqa: E402
import pytest  # noqa: E402

import app.models  # noqa: E402, F401  (registers all tables)
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.ai_gateway import provider as ai_provider  # noqa: E402
from app.modules.ai_gateway import status as ai_status  # noqa: E402
from app.modules.ai_gateway.client import FiboAIClient  # noqa: E402
from tests import routes_for_tests  # noqa: E402

# A developer's ../.env must not leak into tests (a dashboard key would make every call 401,
# a live API key could cause real network calls). Environment variables above already win over
# .env; these optional values are forced here.
settings.dashboard_api_key = None
settings.llm_api_key = None
settings.telegram_bot_token = None  # notifications are tested with their own MockTransport


def _ai_service_down(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("no AI service in tests", request=request)


# FIBO_AI_PROVIDER=sidecar runs the whole suite against an AI service that is down (every path must
# fall back to builtin). Either way no test reaches the network: tests that need AI answers patch
# provider.make_client / status._transport with their own MockTransport (tests/test_ai_gateway.py).
_AI_DOWN = httpx.MockTransport(_ai_service_down)
ai_provider.make_client = lambda: FiboAIClient(settings.ai_url, transport=_AI_DOWN, retry_waits=())
ai_status._transport = _AI_DOWN

BOT_HEADERS = {"X-Fibo-Bot-Token": "test-bot-secret"}

routes_for_tests.install(app)


@pytest.fixture(scope="session")
def tmp_root() -> Path:
    return _TMP


@pytest.fixture(scope="session")
async def started_app():
    """Run the real startup (lifespan) once and create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def client(started_app):
    # raise_app_exceptions=False: let unexpected errors become 500 responses, like in production.
    transport = httpx.ASGITransport(app=started_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def session(started_app):
    async with SessionLocal() as s:
        yield s


@pytest.fixture
def make_workshop(client):
    """Create a workshop through the API; returns its JSON."""

    async def _make(profile: str = "metalworking", name: str = "Тестовый цех") -> dict:
        response = await client.post("/api/v1/workshops", json={"name": name, "profile": profile})
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def make_machine(client):
    """Create a machine through the API; returns its JSON."""

    async def _make(workshop_id: int, **fields) -> dict:
        body = {
            "workshop_id": workshop_id,
            "name": "ЧПУ-1",
            "type": "cnc_mill",
            "criticality": 3,
            "downtime_cost_per_hour_kzt": "15000.00",
            **fields,
        }
        response = await client.post("/api/v1/machines", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    return _make
