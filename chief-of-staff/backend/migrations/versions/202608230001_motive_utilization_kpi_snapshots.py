"""Add canonical Motive vehicle-utilization KPI snapshots.

Revision ID: 202608230001
Revises: 202608150001
Create Date: 2026-08-23 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202608230001"
down_revision = "202608150001"
branch_labels = None
depends_on = None

TABLE_NAME = "motive_vehicle_utilization_kpi_snapshots"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("organization_slug", sa.String(), nullable=False),
        sa.Column("kpi", sa.String(length=120), nullable=False),
        sa.Column("kpi_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("request_timezone", sa.String(length=80), nullable=False),
        sa.Column("value_percent", sa.Numeric(10, 4), nullable=True),
        sa.Column("selected_vehicle_count", sa.Integer(), nullable=False),
        sa.Column("expected_requested_vehicle_days", sa.Integer(), nullable=False),
        sa.Column("provider_rollup_vehicle_days", sa.Integer(), nullable=False),
        sa.Column("metric_valid_vehicle_days", sa.Integer(), nullable=False),
        sa.Column("missing_requested_vehicle_days", sa.Integer(), nullable=False),
        sa.Column("provider_rollup_coverage_percent", sa.Numeric(7, 2), nullable=False),
        sa.Column("utilization_metric_coverage_percent", sa.Numeric(7, 2), nullable=False),
        sa.Column("fleet_representative", sa.Boolean(), nullable=False),
        sa.Column("fuel_unit", sa.String(length=40), nullable=False),
        sa.Column("unit_request_mode", sa.String(length=40), nullable=False),
        sa.Column("source_history_id", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["source_history_id"], ["motive_sync_history.id"]),
        sa.UniqueConstraint(
            "organization_id",
            "kpi",
            "window_start",
            "window_end",
            name="uq_motive_vehicle_util_kpi_snapshot_org_window",
        ),
    )
    op.create_index(
        "ix_motive_vehicle_util_kpi_snapshot_organization_id",
        TABLE_NAME,
        ["organization_id"],
    )
    op.create_index(
        "ix_motive_vehicle_util_kpi_snapshot_organization_slug",
        TABLE_NAME,
        ["organization_slug"],
    )
    op.create_index("ix_motive_vehicle_util_kpi_snapshot_kpi", TABLE_NAME, ["kpi"])
    op.create_index("ix_motive_vehicle_util_kpi_snapshot_status", TABLE_NAME, ["status"])
    op.create_index("ix_motive_vehicle_util_kpi_snapshot_window_start", TABLE_NAME, ["window_start"])
    op.create_index("ix_motive_vehicle_util_kpi_snapshot_window_end", TABLE_NAME, ["window_end"])
    op.create_index(
        "ix_motive_vehicle_util_kpi_snapshot_source_history_id",
        TABLE_NAME,
        ["source_history_id"],
    )


def downgrade() -> None:
    raise RuntimeError(
        "unsafe destructive downgrade is intentionally disabled for Motive utilization KPI snapshots"
    )
