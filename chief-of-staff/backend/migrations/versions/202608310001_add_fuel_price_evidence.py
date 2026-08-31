"""Add durable fuel price evidence and import history.

Revision ID: 202608310001
Revises: 202608290002
Create Date: 2026-08-31 01:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202608310001"
down_revision = "202608290002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fuel_price_import_runs",
        sa.Column("id", sa.Integer(), nullable=False),
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
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("effective_start", sa.Date(), nullable=True),
        sa.Column("effective_end", sa.Date(), nullable=True),
        sa.Column("records_read", sa.Integer(), nullable=False),
        sa.Column("records_inserted", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "supplier",
            "source_sha256",
            name="uq_fuel_price_import_org_supplier_hash",
        ),
    )
    op.create_index("ix_fuel_price_import_runs_organization_id", "fuel_price_import_runs", ["organization_id"])
    op.create_index("ix_fuel_price_import_runs_supplier", "fuel_price_import_runs", ["supplier"])
    op.create_index("ix_fuel_price_import_runs_source_kind", "fuel_price_import_runs", ["source_kind"])
    op.create_index("ix_fuel_price_import_runs_status", "fuel_price_import_runs", ["status"])
    op.create_index("ix_fuel_price_import_runs_error_category", "fuel_price_import_runs", ["error_category"])
    op.create_index("ix_fuel_price_import_runs_currency", "fuel_price_import_runs", ["currency"])
    op.create_index("ix_fuel_price_import_runs_effective_start", "fuel_price_import_runs", ["effective_start"])
    op.create_index("ix_fuel_price_import_runs_effective_end", "fuel_price_import_runs", ["effective_end"])
    op.create_index("ix_fuel_price_import_runs_completed_at", "fuel_price_import_runs", ["completed_at"])

    op.create_table(
        "fuel_price_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("import_run_id", sa.Integer(), nullable=False),
        sa.Column("supplier", sa.String(length=40), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("effective_start", sa.Date(), nullable=False),
        sa.Column("effective_end", sa.Date(), nullable=False),
        sa.Column("supplier_site_id", sa.String(length=40), nullable=False),
        sa.Column("site_name", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=160), nullable=False),
        sa.Column("region_code", sa.String(length=20), nullable=False),
        sa.Column("cost", sa.String(length=40), nullable=False),
        sa.Column("freight", sa.String(length=40), nullable=False),
        sa.Column("base_price", sa.String(length=40), nullable=False),
        sa.Column("fet", sa.String(length=40), nullable=False),
        sa.Column("pft", sa.String(length=40), nullable=False),
        sa.Column("pct", sa.String(length=40), nullable=False),
        sa.Column("local_tax", sa.String(length=40), nullable=False),
        sa.Column("fuel_price", sa.String(length=40), nullable=False),
        sa.Column("sales_tax", sa.String(length=40), nullable=False),
        sa.Column("in_tax_price", sa.String(length=40), nullable=False),
        sa.Column("qst", sa.String(length=40), nullable=False),
        sa.Column("retail_price", sa.String(length=40), nullable=False),
        sa.Column("contracted_price", sa.String(length=40), nullable=False),
        sa.Column("savings", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["import_run_id"], ["fuel_price_import_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "supplier",
            "source_sha256",
            "supplier_site_id",
            name="uq_fuel_price_evidence_org_source_site",
        ),
    )
    op.create_index("ix_fuel_price_evidence_organization_id", "fuel_price_evidence", ["organization_id"])
    op.create_index("ix_fuel_price_evidence_import_run_id", "fuel_price_evidence", ["import_run_id"])
    op.create_index("ix_fuel_price_evidence_supplier", "fuel_price_evidence", ["supplier"])
    op.create_index("ix_fuel_price_evidence_source_sha256", "fuel_price_evidence", ["source_sha256"])
    op.create_index("ix_fuel_price_evidence_currency", "fuel_price_evidence", ["currency"])
    op.create_index("ix_fuel_price_evidence_effective_start", "fuel_price_evidence", ["effective_start"])
    op.create_index("ix_fuel_price_evidence_effective_end", "fuel_price_evidence", ["effective_end"])
    op.create_index("ix_fuel_price_evidence_supplier_site_id", "fuel_price_evidence", ["supplier_site_id"])
    op.create_index("ix_fuel_price_evidence_site_name", "fuel_price_evidence", ["site_name"])
    op.create_index("ix_fuel_price_evidence_city", "fuel_price_evidence", ["city"])
    op.create_index("ix_fuel_price_evidence_region_code", "fuel_price_evidence", ["region_code"])


def downgrade() -> None:
    raise RuntimeError(
        "unsafe destructive downgrade is intentionally disabled for fuel price evidence"
    )
