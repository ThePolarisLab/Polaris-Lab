"""Record ACE feed check outcomes.

Revision ID: 202608130003
Revises: 202608130002
Create Date: 2026-08-13 20:30:00
"""

from alembic import op
import sqlalchemy as sa

revision = "202608130003"
down_revision = "202608130002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ace_feed_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("mode", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("source_found", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("replayed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("records_read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exceptions_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_category", sa.String(80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("organization_id", "mode", "status", "error_category", "completed_at"):
        op.create_index(f"ix_ace_feed_runs_{column}", "ace_feed_runs", [column])


def downgrade() -> None:
    raise RuntimeError("unsafe destructive downgrade is intentionally disabled for ACE compliance/audit data")
