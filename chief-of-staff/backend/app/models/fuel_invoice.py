"""Durable supplier fuel-invoice evidence owned by Polaris."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FuelInvoiceImportRun(Base):
    """One bounded supplier invoice-file import attempt with sanitized provenance."""

    __tablename__ = "fuel_invoice_import_runs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "supplier",
            "source_sha256",
            name="uq_fuel_invoice_import_org_supplier_hash",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    supplier: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(40), nullable=False, default="invoice_pdf", index=True)
    source_message_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_attachment_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[str] = mapped_column(String(40), nullable=False, default="processing", index=True)
    error_category: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    invoice_number: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True, index=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    records_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    organization = relationship("Organization")
    lines = relationship("FuelInvoiceLineEvidence", back_populates="import_run", cascade="all, delete-orphan")


class FuelInvoiceLineEvidence(Base):
    """Immutable provider-authored line evidence from one supplier invoice PDF."""

    __tablename__ = "fuel_invoice_line_evidence"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "supplier",
            "source_sha256",
            "line_number",
            name="uq_fuel_invoice_line_org_source_line",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    import_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("fuel_invoice_import_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    supplier: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)

    provider_transaction_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    card_number: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    driver_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    unit_raw: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    unit_normalized: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    transaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True, index=True)

    supplier_site_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    site_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    site_city: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    region_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    product_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    # Exact supplier-authored decimal text is retained. Polaris does not rewrite
    # supplier invoice values into calculated accounting facts at ingestion time.
    quantity: Mapped[str] = mapped_column(String(40), nullable=False)
    retail_price: Mapped[str | None] = mapped_column(String(40), nullable=True)
    billed_price: Mapped[str] = mapped_column(String(40), nullable=False)
    sales_tax: Mapped[str | None] = mapped_column(String(40), nullable=True)
    hst: Mapped[str | None] = mapped_column(String(40), nullable=True)
    gst: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pst: Mapped[str | None] = mapped_column(String(40), nullable=True)
    qst: Mapped[str | None] = mapped_column(String(40), nullable=True)
    discount_per_unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    discount_amount: Mapped[str | None] = mapped_column(String(40), nullable=True)
    transaction_fee: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pre_tax_amount: Mapped[str | None] = mapped_column(String(40), nullable=True)
    total_amount: Mapped[str | None] = mapped_column(String(40), nullable=True)
    final_amount: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cash_amount: Mapped[str | None] = mapped_column(String(40), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    organization = relationship("Organization")
    import_run = relationship("FuelInvoiceImportRun", back_populates="lines")
