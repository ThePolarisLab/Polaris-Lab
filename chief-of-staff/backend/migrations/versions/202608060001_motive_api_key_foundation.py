"""Motive API-key production foundation.

Revision ID: 202608060001
Revises: 202607310001
Create Date: 2026-08-06 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202608060001"
down_revision = "202607310001"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _create_index_if_missing(name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if name not in _indexes(table_name):
        op.create_index(name, table_name, columns, unique=unique)


def upgrade() -> None:
    existing = _tables()

    if "motive_credentials" not in existing:
        op.create_table(
            "motive_credentials",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("organization_slug", sa.String(), nullable=False),
            sa.Column("provider", sa.String(length=60), nullable=False, server_default="motive"),
            sa.Column("authentication_method", sa.String(length=40), nullable=False, server_default="api_key"),
            sa.Column("environment_mode", sa.String(length=40), nullable=False, server_default="test"),
            sa.Column("encrypted_api_key", sa.Text(), nullable=False),
            sa.Column("key_present", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("connection_status", sa.String(length=60), nullable=False, server_default="configured_unverified"),
            sa.Column("authorization_required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error_code", sa.String(length=80), nullable=True),
            sa.Column("last_error_message_sanitized", sa.Text(), nullable=True),
            sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "authentication_method", "environment_mode", name="uq_motive_credential_org_method_env"),
        )
        _create_index_if_missing("ix_motive_credentials_organization_id", "motive_credentials", ["organization_id"])
        _create_index_if_missing("ix_motive_credentials_organization_slug", "motive_credentials", ["organization_slug"])
        _create_index_if_missing("ix_motive_credentials_provider", "motive_credentials", ["provider"])
        _create_index_if_missing("ix_motive_credentials_authentication_method", "motive_credentials", ["authentication_method"])
        _create_index_if_missing("ix_motive_credentials_connection_status", "motive_credentials", ["connection_status"])

    if "motive_sync_history" not in existing:
        op.create_table(
            "motive_sync_history",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("organization_slug", sa.String(), nullable=False),
            sa.Column("provider", sa.String(length=60), nullable=False, server_default="motive"),
            sa.Column("provider_resource", sa.String(length=80), nullable=False, server_default="verification"),
            sa.Column("mode", sa.String(length=40), nullable=False, server_default="verification"),
            sa.Column("status", sa.String(length=60), nullable=False),
            sa.Column("run_id", sa.String(length=120), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("records_read", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("records_written", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_code", sa.String(length=80), nullable=True),
            sa.Column("error_message_sanitized", sa.Text(), nullable=True),
            sa.Column("checkpoint_before", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("checkpoint_after", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("resource_counts", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_id", name="uq_motive_sync_history_run_id"),
        )
        _create_index_if_missing("ix_motive_sync_history_organization_id", "motive_sync_history", ["organization_id"])
        _create_index_if_missing("ix_motive_sync_history_organization_slug", "motive_sync_history", ["organization_slug"])
        _create_index_if_missing("ix_motive_sync_history_provider", "motive_sync_history", ["provider"])
        _create_index_if_missing("ix_motive_sync_history_status", "motive_sync_history", ["status"])
        _create_index_if_missing("ix_motive_sync_history_run_id", "motive_sync_history", ["run_id"], unique=True)
        _create_index_if_missing("ix_motive_sync_history_started_at", "motive_sync_history", ["started_at"])

    if "motive_sync_checkpoints" not in existing:
        op.create_table(
            "motive_sync_checkpoints",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("organization_slug", sa.String(), nullable=False),
            sa.Column("provider", sa.String(length=60), nullable=False, server_default="motive"),
            sa.Column("provider_resource", sa.String(length=80), nullable=False),
            sa.Column("cursor", sa.Text(), nullable=True),
            sa.Column("page_number", sa.Integer(), nullable=True),
            sa.Column("updated_after_watermark", sa.String(length=80), nullable=True),
            sa.Column("last_successful_position", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("checkpoint_status", sa.String(length=60), nullable=False, server_default="not_started"),
            sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "provider_resource", name="uq_motive_checkpoint_org_resource"),
        )
        _create_index_if_missing("ix_motive_sync_checkpoints_organization_id", "motive_sync_checkpoints", ["organization_id"])
        _create_index_if_missing("ix_motive_sync_checkpoints_organization_slug", "motive_sync_checkpoints", ["organization_slug"])
        _create_index_if_missing("ix_motive_sync_checkpoints_provider", "motive_sync_checkpoints", ["provider"])
        _create_index_if_missing("ix_motive_sync_checkpoints_provider_resource", "motive_sync_checkpoints", ["provider_resource"])

    if "motive_vehicles" not in existing:
        op.create_table(
            "motive_vehicles",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("organization_slug", sa.String(), nullable=False),
            sa.Column("provider", sa.String(length=60), nullable=False, server_default="motive"),
            sa.Column("provider_vehicle_id", sa.String(length=120), nullable=False),
            sa.Column("source_endpoint", sa.String(length=120), nullable=False, server_default="/v1/vehicles"),
            sa.Column("unit_number", sa.String(length=120), nullable=True),
            sa.Column("vin", sa.String(length=80), nullable=True),
            sa.Column("make", sa.String(length=120), nullable=True),
            sa.Column("model", sa.String(length=120), nullable=True),
            sa.Column("year", sa.Integer(), nullable=True),
            sa.Column("license_plate", sa.String(length=80), nullable=True),
            sa.Column("status", sa.String(length=80), nullable=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("provider_payload_metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "provider_vehicle_id", name="uq_motive_vehicle_org_provider"),
        )
        _create_index_if_missing("ix_motive_vehicles_organization_id", "motive_vehicles", ["organization_id"])
        _create_index_if_missing("ix_motive_vehicles_organization_slug", "motive_vehicles", ["organization_slug"])
        _create_index_if_missing("ix_motive_vehicles_provider", "motive_vehicles", ["provider"])
        _create_index_if_missing("ix_motive_vehicles_provider_vehicle_id", "motive_vehicles", ["provider_vehicle_id"])

    if "motive_drivers" not in existing:
        op.create_table(
            "motive_drivers",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("organization_slug", sa.String(), nullable=False),
            sa.Column("provider", sa.String(length=60), nullable=False, server_default="motive"),
            sa.Column("provider_driver_id", sa.String(length=120), nullable=False),
            sa.Column("source_endpoint", sa.String(length=120), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("email", sa.String(length=320), nullable=True),
            sa.Column("status", sa.String(length=80), nullable=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("provider_payload_metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "provider_driver_id", name="uq_motive_driver_org_provider"),
        )
        _create_index_if_missing("ix_motive_drivers_organization_id", "motive_drivers", ["organization_id"])
        _create_index_if_missing("ix_motive_drivers_organization_slug", "motive_drivers", ["organization_slug"])
        _create_index_if_missing("ix_motive_drivers_provider", "motive_drivers", ["provider"])
        _create_index_if_missing("ix_motive_drivers_provider_driver_id", "motive_drivers", ["provider_driver_id"])

    _create_utilization_tables(existing)


def _create_utilization_tables(existing: set[str]) -> None:
    if "motive_vehicle_utilization" not in existing:
        op.create_table(
            "motive_vehicle_utilization",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("organization_slug", sa.String(), nullable=False),
            sa.Column("provider", sa.String(length=60), nullable=False, server_default="motive"),
            sa.Column("provider_vehicle_id", sa.String(length=120), nullable=True),
            sa.Column("source_endpoint", sa.String(length=120), nullable=False, server_default="/v1/vehicle_utilization"),
            sa.Column("reporting_period_start", sa.Date(), nullable=True),
            sa.Column("reporting_period_end", sa.Date(), nullable=True),
            sa.Column("utilization_percent", sa.Numeric(10, 4), nullable=True),
            sa.Column("distance", sa.Numeric(14, 4), nullable=True),
            sa.Column("engine_hours", sa.Numeric(14, 4), nullable=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("provider_payload_metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "provider_vehicle_id", "reporting_period_start", "reporting_period_end", name="uq_motive_vehicle_util_org_period"),
        )
        _resource_indexes("motive_vehicle_utilization", "provider_vehicle_id")

    if "motive_driver_utilization" not in existing:
        op.create_table(
            "motive_driver_utilization",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("organization_slug", sa.String(), nullable=False),
            sa.Column("provider", sa.String(length=60), nullable=False, server_default="motive"),
            sa.Column("provider_driver_id", sa.String(length=120), nullable=True),
            sa.Column("source_endpoint", sa.String(length=120), nullable=False, server_default="/v2/driver_utilization"),
            sa.Column("reporting_period_start", sa.Date(), nullable=True),
            sa.Column("reporting_period_end", sa.Date(), nullable=True),
            sa.Column("utilization_percent", sa.Numeric(10, 4), nullable=True),
            sa.Column("distance", sa.Numeric(14, 4), nullable=True),
            sa.Column("driving_time_seconds", sa.Integer(), nullable=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("provider_payload_metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "provider_driver_id", "reporting_period_start", "reporting_period_end", name="uq_motive_driver_util_org_period"),
        )
        _resource_indexes("motive_driver_utilization", "provider_driver_id")

    if "motive_ifta_summaries" not in existing:
        op.create_table(
            "motive_ifta_summaries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("organization_slug", sa.String(), nullable=False),
            sa.Column("provider", sa.String(length=60), nullable=False, server_default="motive"),
            sa.Column("provider_vehicle_id", sa.String(length=120), nullable=True),
            sa.Column("jurisdiction", sa.String(length=80), nullable=True),
            sa.Column("source_endpoint", sa.String(length=120), nullable=False, server_default="/v1/ifta/summary"),
            sa.Column("reporting_period_start", sa.Date(), nullable=True),
            sa.Column("reporting_period_end", sa.Date(), nullable=True),
            sa.Column("distance", sa.Numeric(14, 4), nullable=True),
            sa.Column("fuel_volume", sa.Numeric(14, 4), nullable=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("provider_payload_metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "provider_vehicle_id", "jurisdiction", "reporting_period_start", "reporting_period_end", name="uq_motive_ifta_org_vehicle_jurisdiction_period"),
        )
        _resource_indexes("motive_ifta_summaries", "provider_vehicle_id")
        _create_index_if_missing("ix_motive_ifta_summaries_jurisdiction", "motive_ifta_summaries", ["jurisdiction"])


def _resource_indexes(table_name: str, provider_id_column: str) -> None:
    _create_index_if_missing(f"ix_{table_name}_organization_id", table_name, ["organization_id"])
    _create_index_if_missing(f"ix_{table_name}_organization_slug", table_name, ["organization_slug"])
    _create_index_if_missing(f"ix_{table_name}_provider", table_name, ["provider"])
    _create_index_if_missing(f"ix_{table_name}_{provider_id_column}", table_name, [provider_id_column])
    _create_index_if_missing(f"ix_{table_name}_reporting_period_start", table_name, ["reporting_period_start"])
    _create_index_if_missing(f"ix_{table_name}_reporting_period_end", table_name, ["reporting_period_end"])


def downgrade() -> None:
    raise RuntimeError(
        "unsafe downgrade: revision 202608060001 would delete Motive credentials, verification history, "
        "checkpoints, and tenant-owned Motive foundation tables. Restore from backup instead."
    )
