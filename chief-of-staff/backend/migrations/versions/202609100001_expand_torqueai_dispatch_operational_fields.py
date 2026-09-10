"""Expand durable TorqueAI dispatches with certified provider fields.

Revision ID: 202609100001
Revises: 202609050001
Create Date: 2026-09-10 00:15:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202609100001"
down_revision = "202609050001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("torqueai_dispatches", sa.Column("currency", sa.String(length=12), nullable=True))
    op.add_column("torqueai_dispatches", sa.Column("total_charge", sa.Numeric(precision=16, scale=4), nullable=True))
    op.add_column("torqueai_dispatches", sa.Column("stop_count", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_torqueai_dispatch_stop_count_nonnegative",
        "torqueai_dispatches",
        "stop_count IS NULL OR stop_count >= 0",
    )


def downgrade() -> None:
    raise RuntimeError(
        "unsafe destructive downgrade is intentionally disabled for TorqueAI operational dispatch enrichment"
    )
