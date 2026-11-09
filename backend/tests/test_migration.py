"""The Alembic migration creates exactly the schema described by the models.

Runs `alembic upgrade head` on an empty SQLite file, then asks Alembic to compare the result with
Base.metadata. Any difference means a model changed without a migration.
"""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

import app.models  # noqa: F401
from app.db.base import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_migration_matches_models(tmp_path):
    db_file = tmp_path / "migrated.db"
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_file}")
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")

    sync_engine = create_engine(f"sqlite:///{db_file}")
    with sync_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    sync_engine.dispose()
    assert diff == []

    command.downgrade(config, "base")
