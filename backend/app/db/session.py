"""Async engine and session factory.

SQLite runs in WAL mode so the API and background tasks can read while one writer writes.
foreign_keys=ON makes SQLite enforce ON DELETE CASCADE / SET NULL (it is off by default).
busy_timeout makes a writer wait up to 5 s for a lock instead of failing immediately.
Switching to PostgreSQL = change DATABASE_URL only.

Rule: background tasks never reuse the request session. They open their own
`async with SessionLocal() as session:` and receive only IDs as arguments.
"""

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def ensure_sqlite_dir(database_url: str) -> None:
    """Create the folder of a SQLite file (e.g. data/sqlite/) so the first connect does not fail."""
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)


engine = create_async_engine(settings.database_url, echo=False)

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()


SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, closed automatically afterwards."""
    async with SessionLocal() as session:
        yield session
