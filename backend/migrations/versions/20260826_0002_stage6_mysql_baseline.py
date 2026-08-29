"""stage6 mysql baseline

Bootstraps the full current-model schema on a fresh MySQL (or SQLite)
database and upgrades pre-existing MVP databases, reusing the same
logic the API applies on startup (Base.metadata.create_all +
apply_mvp_schema_upgrades) so both paths stay consistent.

Revision ID: 20260826_0002
Revises: 20260731_0001
Create Date: 2026-08-26 00:00:00

"""
from collections.abc import Sequence

from alembic import op

from app import models  # noqa: F401  (register models on Base.metadata)
from app.db import Base, apply_mvp_schema_upgrades

revision: str = "20260826_0002"
down_revision: str | None = "20260731_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    # Fresh deployments (e.g. MySQL): create every current-model table.
    Base.metadata.create_all(bind=bind, checkfirst=True)
    # Pre-existing MVP databases: add missing columns, backfills and
    # unique indexes. No-op on a schema that is already up to date.
    apply_mvp_schema_upgrades(bind)


def downgrade() -> None:
    raise NotImplementedError("Stage 6 is a baseline migration and is not reversible.")
