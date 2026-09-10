"""Add TorqueAI operational enrichment table for certified provider fields.

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
    op.create_table(
        "torqueai_dispatch_operational",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("dispatch_id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=12), nullable=True),
        sa.Column("total_charge", sa.Numeric(precision=16, scale=4), nullable=True),
        sa.Column("stop_count", sa.Integer(), nullable=True),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_torqueai_dispatch_operational_organization_id",
        ),
        sa.ForeignKeyConstraint(
            ["dispatch_id"],
            ["torqueai_dispatches.id"],
            name="fk_torqueai_dispatch_operational_dispatch_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("dispatch_id", name="uq_torqueai_dispatch_operational_dispatch"),
        sa.UniqueConstraint(
            "organization_id",
            "dispatch_id",
            name="uq_torqueai_dispatch_operational_org_dispatch",
        ),
        sa.CheckConstraint(
            "stop_count IS NULL OR stop_count >= 0",
            name="ck_torqueai_dispatch_operational_stop_count_nonnegative",
        ),
    )
    op.create_index(
        "ix_torqueai_dispatch_operational_organization_id",
        "torqueai_dispatch_operational",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_torqueai_dispatch_operational_dispatch_id",
        "torqueai_dispatch_operational",
        ["dispatch_id"],
        unique=False,
    )


def downgrade() -> None:
    raise RuntimeError(
        "unsafe destructive downgrade is intentionally disabled for TorqueAI operational dispatch enrichment"
    )
