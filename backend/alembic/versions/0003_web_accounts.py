"""Web accounts and onboarding: users.email + users.password_hash, workshops.survey.

The web dashboard now has a sign-up (workshop + owner) and a sign-in. Bot users keep NULL in both
new user columns. batch_alter_table so the migration (and its downgrade) works on SQLite.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-09 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("email", sa.String(length=254), nullable=True))
        batch.add_column(sa.Column("password_hash", sa.String(length=255), nullable=True))
        batch.create_unique_constraint("uq_users_email", ["email"])
    with op.batch_alter_table("workshops") as batch:
        batch.add_column(sa.Column("survey", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workshops") as batch:
        batch.drop_column("survey")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_email", type_="unique")
        batch.drop_column("password_hash")
        batch.drop_column("email")
