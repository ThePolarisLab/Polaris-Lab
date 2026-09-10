"""Add TorqueAI operational enrichment and normalized certified stops.

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
        sa.Column("billing_currency", sa.String(length=12), nullable=True),
        sa.Column("billing_rate", sa.Numeric(precision=16, scale=4), nullable=True),
        sa.Column("billing_subtotal", sa.Numeric(precision=16, scale=4), nullable=True),
        sa.Column("billing_tax_amount", sa.Numeric(precision=16, scale=4), nullable=True),
        sa.Column("billing_total", sa.Numeric(precision=16, scale=4), nullable=True),
        sa.Column("stop_count", sa.Integer(), nullable=True),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_torqueai_dispatch_operational_organization_id"),
        sa.ForeignKeyConstraint(["dispatch_id"], ["torqueai_dispatches.id"], name="fk_torqueai_dispatch_operational_dispatch_id", ondelete="CASCADE"),
        sa.UniqueConstraint("dispatch_id", name="uq_torqueai_dispatch_operational_dispatch"),
        sa.UniqueConstraint("organization_id", "dispatch_id", name="uq_torqueai_dispatch_operational_org_dispatch"),
        sa.CheckConstraint("stop_count IS NULL OR stop_count >= 0", name="ck_torqueai_dispatch_operational_stop_count_nonnegative"),
    )
    op.create_index("ix_torqueai_dispatch_operational_organization_id", "torqueai_dispatch_operational", ["organization_id"], unique=False)
    op.create_index("ix_torqueai_dispatch_operational_dispatch_id", "torqueai_dispatch_operational", ["dispatch_id"], unique=False)

    op.create_table(
        "torqueai_dispatch_stops",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("dispatch_id", sa.Integer(), nullable=False),
        sa.Column("stop_index", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("stop_no", sa.String(length=120), nullable=True),
        sa.Column("job", sa.String(length=120), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("city", sa.String(length=255), nullable=True),
        sa.Column("province", sa.String(length=120), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("zip_code", sa.String(length=40), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("commodity", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("driver_name", sa.String(length=255), nullable=True),
        sa.Column("co_driver_name", sa.String(length=255), nullable=True),
        sa.Column("carrier_name", sa.String(length=255), nullable=True),
        sa.Column("truck_number", sa.String(length=120), nullable=True),
        sa.Column("trailer_number", sa.String(length=120), nullable=True),
        sa.Column("scheduled_is_window", sa.Boolean(), nullable=True),
        sa.Column("scheduled_pickup_date_text", sa.String(length=120), nullable=True),
        sa.Column("scheduled_pickup_date2_text", sa.String(length=120), nullable=True),
        sa.Column("scheduled_pickup_time_text", sa.String(length=120), nullable=True),
        sa.Column("scheduled_pickup_time2_text", sa.String(length=120), nullable=True),
        sa.Column("temperature_text", sa.String(length=255), nullable=True),
        sa.Column("temperature_unit", sa.String(length=40), nullable=True),
        sa.Column("weight", sa.Numeric(precision=16, scale=4), nullable=True),
        sa.Column("weight_unit", sa.String(length=40), nullable=True),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_torqueai_dispatch_stops_organization_id"),
        sa.ForeignKeyConstraint(["dispatch_id"], ["torqueai_dispatches.id"], name="fk_torqueai_dispatch_stops_dispatch_id", ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "dispatch_id", "stop_index", name="uq_torqueai_dispatch_stop_org_dispatch_index"),
        sa.CheckConstraint("stop_index >= 0", name="ck_torqueai_dispatch_stop_index_nonnegative"),
    )
    for column in ("organization_id", "dispatch_id", "job", "city", "province", "country"):
        op.create_index(f"ix_torqueai_dispatch_stops_{column}", "torqueai_dispatch_stops", [column], unique=False)


def downgrade() -> None:
    raise RuntimeError("unsafe destructive downgrade is intentionally disabled for TorqueAI operational dispatch enrichment")
