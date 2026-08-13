"""Allow ACE penalty indicator to remain unreported.

Revision ID: 202608130002
Revises: 202608130001
Create Date: 2026-08-13 15:30:00
"""

from alembic import op
import sqlalchemy as sa

revision = "202608130002"
down_revision = "202608130001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ace_inbond_movements") as batch_op:
        batch_op.alter_column(
            "penalty_indicator",
            existing_type=sa.Boolean(),
            nullable=True,
            server_default=None,
        )


def downgrade() -> None:
    raise RuntimeError("unsafe destructive downgrade is intentionally disabled for ACE compliance/audit data")
