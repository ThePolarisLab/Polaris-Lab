"""Add minimized durable TorqueAI dispatch ingestion tables.

Revision ID: 202608290001
Revises: 202608280001
Create Date: 2026-08-29 04:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202608290001"
down_revision = "202608280001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "torqueai_dispatches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("provider_load_number", sa.String(length=120), nullable=False),
        sa.Column("provider_order_number", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=120), nullable=True),
        sa.Column("order_date_text", sa.String(length=120), nullable=True),
        sa.Column("ship_date_text", sa.String(length=120), nullable=True),
        sa.Column("delivery_date_text", sa.String(length=120), nullable=True),
        sa.Column("customer_name", sa.String(length=255), nullable=True),
        sa.Column("dispatcher_name", sa.String(length=255), nullable=True),
        sa.Column("driver_name", sa.String(length=255), nullable=True),
        sa.Column("carrier_name", sa.String(length=255), nullable=True),
        sa.Column("truck_number", sa.String(length=120), nullable=True),
        sa.Column("trailer_number", sa.String(length=120), nullable=True),
        sa.Column("loaded_miles", sa.Numeric(14, 4), nullable=True),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_torqueai_dispatches_organization_id"),
        sa.UniqueConstraint("organization_id", "provider_load_number", "provider_order_number", name="uq_torqueai_dispatch_org_provider_identity"),
        sa.CheckConstraint("loaded_miles IS NULL OR loaded_miles >= 0", name="ck_torqueai_dispatch_loaded_miles_nonnegative"),
    )
    op.create_index("ix_torqueai_dispatches_organization_id", "torqueai_dispatches", ["organization_id"])

    op.create_table(
        "torqueai_dispatch_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(length=120), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("requested_from", sa.Date(), nullable=False),
        sa.Column("requested_to", sa.Date(), nullable=False),
        sa.Column("page_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("pages_fetched", sa.Integer(), nullable=False),
        sa.Column("provider_total_count", sa.Integer(), nullable=True),
        sa.Column("rows_validated", sa.Integer(), nullable=False),
        sa.Column("rows_inserted", sa.Integer(), nullable=False),
        sa.Column("rows_updated", sa.Integer(), nullable=False),
        sa.Column("rows_unchanged", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_torqueai_dispatch_sync_runs_organization_id"),
        sa.UniqueConstraint("run_id", name="uq_torqueai_dispatch_sync_run_id"),
    )
    op.create_index("ix_torqueai_dispatch_sync_runs_organization_id", "torqueai_dispatch_sync_runs", ["organization_id"])
    op.create_index("ix_torqueai_dispatch_sync_runs_status", "torqueai_dispatch_sync_runs", ["status"])

    op.create_table(
        "torqueai_dispatch_sync_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("last_successful_window_start", sa.Date(), nullable=False),
        sa.Column("last_successful_window_end", sa.Date(), nullable=False),
        sa.Column("last_successful_run_id", sa.String(length=120), nullable=False),
        sa.Column("last_successful_completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_torqueai_dispatch_sync_state_organization_id"),
        sa.UniqueConstraint("organization_id", name="uq_torqueai_dispatch_sync_state_org"),
    )


def downgrade() -> None:
    raise RuntimeError("unsafe destructive downgrade is intentionally disabled for TorqueAI durable ingestion")
