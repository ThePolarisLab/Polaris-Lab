"""Support Eco Petroleum provider-authored fuel price evidence.

Revision ID: 202608310003
Revises: 202608310002
Create Date: 2026-08-31 03:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202608310003"
down_revision = "202608310002"
branch_labels = None
depends_on = None


_BVD_OPTIONAL_COLUMNS = (
    "site_name",
    "city",
    "cost",
    "freight",
    "sales_tax",
    "retail_price",
    "savings",
)


def upgrade() -> None:
    with op.batch_alter_table("fuel_price_evidence") as batch_op:
        for column_name in _BVD_OPTIONAL_COLUMNS:
            length = 255 if column_name == "site_name" else 160 if column_name == "city" else 40
            batch_op.alter_column(
                column_name,
                existing_type=sa.String(length=length),
                nullable=True,
            )
        batch_op.add_column(sa.Column("brand", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("location_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("eco_price", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("eco_gst_hst", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("eco_total_price", sa.String(length=40), nullable=True))
        batch_op.create_index("ix_fuel_price_evidence_brand", ["brand"], unique=False)
        batch_op.create_index("ix_fuel_price_evidence_location_name", ["location_name"], unique=False)


def downgrade() -> None:
    raise RuntimeError(
        "unsafe destructive downgrade is intentionally disabled for fuel price evidence"
    )
