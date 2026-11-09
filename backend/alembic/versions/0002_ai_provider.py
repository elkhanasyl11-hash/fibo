"""Incidents remember who analysed them: ai_source ("ai" | "builtin") and degraded (list of tags).

Both are filled by the incident pipeline since the AI gateway (D76). Old rows: ai_source NULL (analysed
before the gateway existed), degraded []. batch_alter_table so the downgrade also works on SQLite.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-08 23:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("incidents") as batch:
        batch.add_column(sa.Column("ai_source", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("degraded", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("incidents") as batch:
        batch.drop_column("degraded")
        batch.drop_column("ai_source")
