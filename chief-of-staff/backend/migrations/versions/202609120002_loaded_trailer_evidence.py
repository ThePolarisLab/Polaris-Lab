"""Durable location observations and per-dispatch last-seen evidence.

Revision ID: 202609120002
Revises: 202609120001
"""
from alembic import op
import sqlalchemy as sa

revision = "202609120002"
down_revision = "202609120001"
branch_labels = None
depends_on = None


def upgrade():
    # No backfill: historical change timestamps do not prove recent observation.
    op.add_column("torqueai_dispatches", sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "motive_location_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("motive_vehicles.id"), nullable=False),
        sa.Column("truck_number", sa.String(120)),
        sa.Column("city", sa.String(255)), sa.Column("province", sa.String(120)),
        sa.Column("country", sa.String(120)),
        sa.Column("location_observed_at", sa.DateTime(timezone=True)),
        sa.Column("current_driver_name", sa.String(255)),
        sa.Column("pairing_observed_at", sa.DateTime(timezone=True)),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_status", sa.String(40), nullable=False),
        sa.UniqueConstraint("organization_id", "vehicle_id", name="uq_motive_location_org_vehicle"),
    )
    op.create_index("ix_motive_location_observations_organization_id", "motive_location_observations", ["organization_id"])
    op.create_index("ix_motive_location_observations_vehicle_id", "motive_location_observations", ["vehicle_id"])


def downgrade():
    raise RuntimeError("unsafe destructive downgrade is intentionally disabled for durable location evidence")
