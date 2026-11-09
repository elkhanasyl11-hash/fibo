"""Alembic migration runner (async).

Takes the database URL from app settings (or from alembic.ini's sqlalchemy.url if a caller set it,
which the tests do) and compares against Base.metadata, which contains every table because we
import app.models. render_as_batch lets future migrations ALTER tables on SQLite (SQLite can't
ALTER most things in place, so Alembic copies the table instead).
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401  (registers all tables on Base.metadata)
from app.core.config import settings
from app.db.base import Base, UTCDateTime
from app.db.session import ensure_sqlite_dir

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or settings.database_url


def render_item(type_: str, obj, autogen_context):
    """Write our UTCDateTime columns as plain sa.DateTime(timezone=True) in generated migrations.

    UTCDateTime only changes how Python reads/writes values; the stored column type is the same,
    and migration files should not import application code.
    """
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False  # False = let Alembic render everything else as usual


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (alembic upgrade head --sql)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync_migrations(connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, render_as_batch=True, render_item=render_item
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    url = _database_url()
    ensure_sqlite_dir(url)
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
