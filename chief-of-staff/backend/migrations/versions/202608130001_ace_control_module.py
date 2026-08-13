"""ACE control module schema.

Revision ID: 202608130001
Revises: 202608060001
Create Date: 2026-08-13 03:30:00
"""

from alembic import op
import sqlalchemy as sa

revision = "202608130001"
down_revision = "202608060001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ace_inbond_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("inbond_number", sa.String(32), nullable=False),
        sa.Column("bill_of_lading_number", sa.String(120), nullable=False, server_default=""),
        sa.Column("inbond_type_code", sa.String(8), nullable=True),
        sa.Column("inbond_type_description", sa.String(160), nullable=True),
        sa.Column("source_type_description", sa.String(160), nullable=True),
        sa.Column("record_status", sa.String(80), nullable=True),
        sa.Column("inbond_carrier_code", sa.String(20), nullable=True),
        sa.Column("inbond_carrier_name", sa.String(255), nullable=True),
        sa.Column("bonded_carrier_code", sa.String(20), nullable=True),
        sa.Column("bonded_carrier_name", sa.String(255), nullable=True),
        sa.Column("manifest_carrier_code", sa.String(20), nullable=True),
        sa.Column("manifest_carrier_name", sa.String(255), nullable=True),
        sa.Column("qp_filer_code", sa.String(20), nullable=True),
        sa.Column("qp_filer_name", sa.String(255), nullable=True),
        sa.Column("shipper_name", sa.String(255), nullable=True),
        sa.Column("consignee_name", sa.String(255), nullable=True),
        sa.Column("origination_port_name", sa.String(160), nullable=True),
        sa.Column("destination_port_name", sa.String(160), nullable=True),
        sa.Column("create_date", sa.Date(), nullable=True),
        sa.Column("arrival_date", sa.Date(), nullable=True),
        sa.Column("export_date", sa.Date(), nullable=True),
        sa.Column("transfer_of_liability_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("days_late", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("days_overdue_for_export", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("late_in_transit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("overdue_for_export", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("penalty_indicator", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("authorization_status", sa.String(80), nullable=True),
        sa.Column("authorization_notes", sa.Text(), nullable=True),
        sa.Column("evidence_reference", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(40), nullable=False, server_default="clear"),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "inbond_number", "bill_of_lading_number", name="uq_ace_inbond_org_inbond_bol"),
    )
    for column in (
        "organization_id", "inbond_number", "bill_of_lading_number", "record_status", "inbond_type_code",
        "inbond_carrier_code", "bonded_carrier_code", "manifest_carrier_code", "qp_filer_code",
        "shipper_name", "consignee_name", "create_date", "arrival_date", "export_date",
        "late_in_transit", "overdue_for_export", "penalty_indicator", "authorization_status",
        "review_status", "resolved_at", "last_seen_at",
    ):
        op.create_index(f"ix_ace_inbond_movements_{column}", "ace_inbond_movements", [column])

    op.create_table(
        "ace_inbond_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("movement_id", sa.Integer(), sa.ForeignKey("ace_inbond_movements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("field_name", sa.String(120), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("organization_id", "movement_id", "event_type", "occurred_at"):
        op.create_index(f"ix_ace_inbond_events_{column}", "ace_inbond_events", [column])

    op.create_table(
        "ace_import_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("source_message_id", sa.String(500), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=True),
        sa.Column("source_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="processing"),
        sa.Column("records_read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exceptions_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("organization_id", "source_message_id", name="uq_ace_import_org_message"),
    )
    for column in ("organization_id", "status"):
        op.create_index(f"ix_ace_import_runs_{column}", "ace_import_runs", [column])


def downgrade() -> None:
    raise RuntimeError("unsafe destructive downgrade is intentionally disabled for ACE compliance/audit data")
