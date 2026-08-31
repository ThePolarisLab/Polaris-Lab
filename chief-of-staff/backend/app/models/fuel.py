"""Durable fuel price evidence owned by Polaris."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FuelPriceImportRun(Base):
    """One bounded provider price-file import attempt with sanitized provenance."""

    __tablename__ = "fuel_price_import_runs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "supplier",
            "source_sha256",
            name="uq_fuel_price_import_org_supplier_hash",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    supplier: Mapped[str] = mapped_column(String(40), nullable=False, default="bvd", index=True)
    source_kind: Mapped[str] = mapped_column(String(40), nullable=False, default="pcn_pdf", index=True)
    source_message_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_attachment_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[str] = mapped_column(String(40), nullable=False, default="processing", index=True)
    error_category: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True, index=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    effective_start: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    effective_end: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    records_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    organization = relationship("Organization")
    evidence = relationship("FuelPriceEvidence", back_populates="import_run", cascade="all, delete-orphan")


class FuelPriceEvidence(Base):
    """Immutable provider-authored station price evidence from one source file."""

    __tablename__ = "fuel_price_evidence"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "supplier",
            "source_sha256",
            "supplier_site_id",
            name="uq_fuel_price_evidence_org_source_site",
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
        ForeignKey("fuel_price_import_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    supplier: Mapped[str] = mapped_column(String(40), nullable=False, default="bvd", index=True)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    effective_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    effective_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    supplier_site_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    brand: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    site_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    location_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    region_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Exact provider-authored decimal text is retained. Polaris does not recompute
    # supplier price components or round them into a new accounting representation.
    product_code: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # BVD-specific shared/source components. Nullable because Eco reports do not
    # expose these fields under the same provider-authored labels.
    cost: Mapped[str | None] = mapped_column(String(40), nullable=True)
    freight: Mapped[str | None] = mapped_column(String(40), nullable=True)
    base_price: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fet: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pft: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pct: Mapped[str | None] = mapped_column(String(40), nullable=True)
    local_tax: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fuel_price: Mapped[str | None] = mapped_column(String(40), nullable=True)
    in_tax_price: Mapped[str | None] = mapped_column(String(40), nullable=True)
    qst: Mapped[str | None] = mapped_column(String(40), nullable=True)
    federal_tax: Mapped[str | None] = mapped_column(String(40), nullable=True)
    state_tax: Mapped[str | None] = mapped_column(String(40), nullable=True)
    other_cost: Mapped[str | None] = mapped_column(String(40), nullable=True)
    total_cost: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Eco CAD source fields. Eco CAD's invoice Billed price corresponds to the
    # provider-authored Total Price; Price and GST/HST remain separate evidence.
    eco_price: Mapped[str | None] = mapped_column(String(40), nullable=True)
    eco_gst_hst: Mapped[str | None] = mapped_column(String(40), nullable=True)
    eco_total_price: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Cross-provider fields. contracted_price is the provider-authored rate used
    # for later quote-vs-invoice comparison: BVD Your Price, Eco USD Your Price,
    # or Eco CAD Total Price. Other fields remain nullable when a supplier does
    # not publish them in its rate report.
    sales_tax: Mapped[str | None] = mapped_column(String(40), nullable=True)
    retail_price: Mapped[str | None] = mapped_column(String(40), nullable=True)
    contracted_price: Mapped[str] = mapped_column(String(40), nullable=False)
    savings: Mapped[str | None] = mapped_column(String(40), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    organization = relationship("Organization")
    import_run = relationship("FuelPriceImportRun", back_populates="evidence")
