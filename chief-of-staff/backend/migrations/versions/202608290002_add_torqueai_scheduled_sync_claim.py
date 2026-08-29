"""Add durable TorqueAI scheduled-sync trigger claims.

Revision ID: 202608290002
Revises: 202608290001
Create Date: 2026-08-29 05:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202608290002"
down_revision = "202608290001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode keeps the forward migration compatible with the repository's
    # SQLite migration gate while producing the same columns/constraint on
    # PostgreSQL.
    with op.batch_alter_table("torqueai_dispatch_sync_runs") as batch_op:
        batch_op.add_column(sa.Column("trigger_mode", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("trigger_slot", sa.String(length=40), nullable=True))
        batch_op.create_unique_constraint(
            "uq_torqueai_dispatch_sync_scheduled_slot",
            ["organization_id", "trigger_mode", "trigger_slot"],
        )


def downgrade() -> None:
    raise RuntimeError(
        "unsafe destructive downgrade is intentionally disabled for TorqueAI scheduled-sync claims"
    )
