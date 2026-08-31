"""Support BVD USD PCN provider-specific price components.

Revision ID: 202608310002
Revises: 202608310001
Create Date: 2026-08-31 02:25:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202608310002"
down_revision = "202608310001"
branch_labels = None
depends_on = None


_CAD_ONLY_COLUMNS = (
    "base_price",
    "fet",
    "pft",
    "pct",
    "local_tax",
    "fuel_price",
    "in_tax_price",
    "qst",
)


def upgrade() -> None:
    with op.batch_alter_table("fuel_price_evidence") as batch_op:
        for column_name in _CAD_ONLY_COLUMNS:
            batch_op.alter_column(
                column_name,
                existing_type=sa.String(length=40),
                nullable=True,
            )
        batch_op.add_column(sa.Column("product_code", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("federal_tax", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("state_tax", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("other_cost", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("total_cost", sa.String(length=40), nullable=True))


def downgrade() -> None:
    raise RuntimeError(
        "unsafe destructive downgrade is intentionally disabled for fuel price evidence"
    )
