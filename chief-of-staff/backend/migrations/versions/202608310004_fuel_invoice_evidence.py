"""Add durable supplier fuel-invoice evidence.

Revision ID: 202608310004
Revises: 202608310003
Create Date: 2026-08-31 05:15:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202608310004"
down_revision = "202608310003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fuel_invoice_import_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("supplier", sa.String(length=40), nullable=False),
        sa.Column("source_kind", sa.String(length=40), nullable=False),
        sa.Column("source_message_id", sa.String(length=500), nullable=True),
        sa.Column("source_attachment_id", sa.String(length=500), nullable=True),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("source_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("error_category", sa.String(length=80), nullable=True),
        sa.Column("invoice_number", sa.String(length=80), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("records_read", sa.Integer(), nullable=False),
        sa.Column("records_inserted", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.UniqueConstraint(
            "organization_id",
            "supplier",
            "source_sha256",
            name="uq_fuel_invoice_import_org_supplier_hash",
        ),
    )
    for column in (
        "organization_id",
        "supplier",
        "source_kind",
        "status",
        "error_category",
        "invoice_number",
        "currency",
        "invoice_date",
        "period_start",
        "period_end",
        "due_date",
        "completed_at",
    ):
        op.create_index(f"ix_fuel_invoice_import_runs_{column}", "fuel_invoice_import_runs", [column], unique=False)

    op.create_table(
        "fuel_invoice_line_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("import_run_id", sa.Integer(), nullable=False),
        sa.Column("supplier", sa.String(length=40), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("invoice_number", sa.String(length=80), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("provider_transaction_id", sa.String(length=120), nullable=True),
        sa.Column("card_number", sa.String(length=80), nullable=True),
        sa.Column("driver_name", sa.String(length=160), nullable=True),
        sa.Column("unit_raw", sa.String(length=80), nullable=True),
        sa.Column("unit_normalized", sa.String(length=80), nullable=True),
        sa.Column("transaction_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("supplier_site_id", sa.String(length=80), nullable=True),
        sa.Column("site_name", sa.String(length=255), nullable=True),
        sa.Column("site_city", sa.String(length=160), nullable=True),
        sa.Column("region_code", sa.String(length=20), nullable=True),
        sa.Column("product_code", sa.String(length=40), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("quantity", sa.String(length=40), nullable=False),
        sa.Column("retail_price", sa.String(length=40), nullable=True),
        sa.Column("unit_price", sa.String(length=40), nullable=True),
        sa.Column("billed_price", sa.String(length=40), nullable=False),
        sa.Column("sales_tax", sa.String(length=40), nullable=True),
        sa.Column("hst", sa.String(length=40), nullable=True),
        sa.Column("gst", sa.String(length=40), nullable=True),
        sa.Column("pst", sa.String(length=40), nullable=True),
        sa.Column("qst", sa.String(length=40), nullable=True),
        sa.Column("discount_per_unit", sa.String(length=40), nullable=True),
        sa.Column("discount_amount", sa.String(length=40), nullable=True),
        sa.Column("transaction_fee", sa.String(length=40), nullable=True),
        sa.Column("pre_tax_amount", sa.String(length=40), nullable=True),
        sa.Column("total_amount", sa.String(length=40), nullable=True),
        sa.Column("final_amount", sa.String(length=40), nullable=True),
        sa.Column("cash_amount", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["import_run_id"], ["fuel_invoice_import_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "organization_id",
            "supplier",
            "source_sha256",
            "line_number",
            name="uq_fuel_invoice_line_org_source_line",
        ),
    )
    for column in (
        "organization_id",
        "import_run_id",
        "supplier",
        "source_sha256",
        "invoice_number",
        "currency",
        "provider_transaction_id",
        "card_number",
        "unit_raw",
        "unit_normalized",
        "transaction_at",
        "supplier_site_id",
        "site_name",
        "site_city",
        "region_code",
        "product_code",
        "category",
    ):
        op.create_index(f"ix_fuel_invoice_line_evidence_{column}", "fuel_invoice_line_evidence", [column], unique=False)


def downgrade() -> None:
    raise RuntimeError(
        "unsafe destructive downgrade is intentionally disabled for fuel invoice evidence"
    )
