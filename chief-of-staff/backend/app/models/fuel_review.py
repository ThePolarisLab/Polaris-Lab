"""Append-only human review decisions for fuel price discrepancies."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FuelDiscrepancyReviewEvent(Base):
    """Immutable audit event; never rewrites supplier evidence or accounting facts."""

    __tablename__ = "fuel_discrepancy_review_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    invoice_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("fuel_invoice_import_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_line_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("fuel_invoice_line_evidence.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    approval_mode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewer_identity_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    reviewer_role: Mapped[str] = mapped_column(String(40), nullable=False)

    # Snapshot the exact technical result at decision time. These fields are
    # audit evidence only and are not used to rewrite provider-authored data.
    technical_status: Mapped[str] = mapped_column(String(40), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    invoice_billed_price: Mapped[str | None] = mapped_column(String(40), nullable=True)
    quote_price: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rate_difference: Mapped[str | None] = mapped_column(String(40), nullable=True)
    analytical_impact: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)
