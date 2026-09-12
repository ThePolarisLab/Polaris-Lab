"""Add durable Motive inspection-part maintenance memory.

Revision ID: 202609120001
Revises: 202609100001
Create Date: 2026-09-12 21:05:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202609120001"
down_revision = "202609100001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "motive_maintenance_issue_memory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("organization_slug", sa.String(), nullable=False),
        sa.Column("truck_number", sa.String(length=120), nullable=False),
        sa.Column("identity_key", sa.String(length=64), nullable=False),
        sa.Column("part_category", sa.String(length=255), nullable=True),
        sa.Column("part_type", sa.String(length=120), nullable=True),
        sa.Column("part_name", sa.String(length=255), nullable=True),
        sa.Column("lifecycle_state", sa.String(length=40), nullable=False),
        sa.Column("first_open_date", sa.Date(), nullable=True),
        sa.Column("last_seen_date", sa.Date(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_odometer", sa.Integer(), nullable=True),
        sa.Column("explicit_resolution_status", sa.String(length=60), nullable=True),
        sa.Column("explicit_resolution_date", sa.Date(), nullable=True),
        sa.Column("last_reopened_date", sa.Date(), nullable=True),
        sa.Column("reopen_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("open_observation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_window_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("disappearance_means_resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_motive_maintenance_issue_org"),
        sa.UniqueConstraint("organization_id", "truck_number", "identity_key", name="uq_motive_maintenance_issue_identity"),
    )
    for column in ("organization_id", "organization_slug", "truck_number", "identity_key", "lifecycle_state", "first_open_date", "last_seen_date", "explicit_resolution_date", "last_reopened_date"):
        op.create_index(f"ix_motive_maintenance_issue_memory_{column}", "motive_maintenance_issue_memory", [column], unique=False)

    op.create_table(
        "motive_maintenance_issue_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("issue_id", sa.Integer(), nullable=False),
        sa.Column("truck_number", sa.String(length=120), nullable=False),
        sa.Column("identity_key", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("structured_status", sa.String(length=60), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("report_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("odometer", sa.Integer(), nullable=True),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_endpoint", sa.String(length=120), nullable=False),
        sa.Column("provider_write_performed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_motive_maintenance_event_org"),
        sa.ForeignKeyConstraint(["issue_id"], ["motive_maintenance_issue_memory.id"], name="fk_motive_maintenance_event_issue", ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "source_fingerprint", name="uq_motive_maintenance_event_fingerprint"),
    )
    for column in ("organization_id", "issue_id", "truck_number", "identity_key", "event_type", "report_date", "source_fingerprint"):
        op.create_index(f"ix_motive_maintenance_issue_events_{column}", "motive_maintenance_issue_events", [column], unique=False)


def downgrade() -> None:
    raise RuntimeError("unsafe destructive downgrade is intentionally disabled for durable maintenance memory")
