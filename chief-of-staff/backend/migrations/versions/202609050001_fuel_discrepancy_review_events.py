"""Add append-only fuel discrepancy review events.

Revision ID: 202609050001
Revises: 202608310004
Create Date: 2026-09-05 12:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202609050001"
down_revision = "202608310004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fuel_discrepancy_review_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("invoice_run_id", sa.Integer(), nullable=False),
        sa.Column("invoice_line_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("approval_mode", sa.String(length=40), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("reviewer_identity_id", sa.String(length=120), nullable=False),
        sa.Column("reviewer_role", sa.String(length=40), nullable=False),
        sa.Column("technical_status", sa.String(length=40), nullable=False),
        sa.Column("policy_version", sa.String(length=80), nullable=False),
        sa.Column("invoice_billed_price", sa.String(length=40), nullable=True),
        sa.Column("quote_price", sa.String(length=40), nullable=True),
        sa.Column("rate_difference", sa.String(length=40), nullable=True),
        sa.Column("analytical_impact", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["invoice_run_id"], ["fuel_invoice_import_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_line_id"], ["fuel_invoice_line_evidence.id"], ondelete="CASCADE"),
    )
    for column in (
        "organization_id",
        "invoice_run_id",
        "invoice_line_id",
        "action",
        "reviewer_identity_id",
        "created_at",
    ):
        op.create_index(
            f"ix_fuel_discrepancy_review_events_{column}",
            "fuel_discrepancy_review_events",
            [column],
            unique=False,
        )


def downgrade() -> None:
    raise RuntimeError(
        "unsafe destructive downgrade is intentionally disabled for fuel discrepancy review audit history"
    )
