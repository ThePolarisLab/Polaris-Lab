"""Reconcile the truck plate column created by the initial clean-install migration.

Revision ID: 202608280001
Revises: 202608230001
Create Date: 2026-08-28 20:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202608280001"
down_revision = "202608230001"
branch_labels = None
depends_on = None

TABLE_NAME = "trucks"


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if TABLE_NAME not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(TABLE_NAME)}


def upgrade() -> None:
    columns = _columns()
    if not columns:
        return

    # The initial clean-install migration created `license_plate`, while the
    # canonical ORM/API contract has always exposed `plate`. Existing legacy
    # databases may already have `plate`, so keep this migration idempotent.
    if "plate" in columns:
        return

    if "license_plate" in columns:
        op.execute(sa.text("ALTER TABLE trucks RENAME COLUMN license_plate TO plate"))
        return

    # Defensive compatibility for a partially-created legacy schema.
    op.add_column(TABLE_NAME, sa.Column("plate", sa.String(), nullable=True))


def downgrade() -> None:
    raise RuntimeError(
        "unsafe destructive downgrade is intentionally disabled for truck schema reconciliation"
    )
