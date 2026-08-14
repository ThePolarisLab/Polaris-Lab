"""Harden Motive vehicle utilization schema for future ingestion.

Revision ID: 202608140001
Revises: 202608130003
Create Date: 2026-08-14 14:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "202608140001"
down_revision = "202608130003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("motive_vehicle_utilization")}
    foreign_keys = {foreign_key["name"] for foreign_key in inspector.get_foreign_keys("motive_vehicle_utilization")}

    with op.batch_alter_table("motive_vehicle_utilization") as batch_op:
        if "motive_vehicle_id" not in columns:
            batch_op.add_column(sa.Column("motive_vehicle_id", sa.Integer(), nullable=True))
        if "fk_motive_vehicle_utilization_motive_vehicle_id" not in foreign_keys:
            batch_op.create_foreign_key(
                "fk_motive_vehicle_utilization_motive_vehicle_id",
                "motive_vehicles",
                ["motive_vehicle_id"],
                ["id"],
            )
        if "request_window_start" not in columns:
            batch_op.add_column(sa.Column("request_window_start", sa.Date(), nullable=True))
        if "request_window_end" not in columns:
            batch_op.add_column(sa.Column("request_window_end", sa.Date(), nullable=True))
        if "idle_time" not in columns:
            batch_op.add_column(sa.Column("idle_time", sa.Numeric(14, 4), nullable=True))
        if "driving_time" not in columns:
            batch_op.add_column(sa.Column("driving_time", sa.Numeric(14, 4), nullable=True))
        if "idle_fuel" not in columns:
            batch_op.add_column(sa.Column("idle_fuel", sa.Numeric(14, 4), nullable=True))
        if "driving_fuel" not in columns:
            batch_op.add_column(sa.Column("driving_fuel", sa.Numeric(14, 4), nullable=True))
        if "metric_units" not in columns:
            batch_op.add_column(sa.Column("metric_units", sa.Boolean(), nullable=True))
        if "parser_version" not in columns:
            batch_op.add_column(sa.Column("parser_version", sa.String(length=80), nullable=True))

    indexes = {index["name"] for index in inspector.get_indexes("motive_vehicle_utilization")}
    if "ix_motive_vehicle_utilization_motive_vehicle_id" not in indexes:
        op.create_index("ix_motive_vehicle_utilization_motive_vehicle_id", "motive_vehicle_utilization", ["motive_vehicle_id"])
    if "ix_motive_vehicle_utilization_request_window_start" not in indexes:
        op.create_index("ix_motive_vehicle_utilization_request_window_start", "motive_vehicle_utilization", ["request_window_start"])
    if "ix_motive_vehicle_utilization_request_window_end" not in indexes:
        op.create_index("ix_motive_vehicle_utilization_request_window_end", "motive_vehicle_utilization", ["request_window_end"])


def downgrade() -> None:
    raise RuntimeError("unsafe destructive downgrade is intentionally disabled for Motive utilization schema hardening")
