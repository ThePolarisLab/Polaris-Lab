"""ACE manifest and in-bond persistence for Polaris compliance control."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AceInBondMovement(Base):
    __tablename__ = "ace_inbond_movements"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "inbond_number", "bill_of_lading_number",
            name="uq_ace_inbond_org_inbond_bol",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)

    inbond_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    bill_of_lading_number: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    inbond_type_code: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    inbond_type_description: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_type_description: Mapped[str | None] = mapped_column(String(160), nullable=True)
    record_status: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)

    inbond_carrier_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    inbond_carrier_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    bonded_carrier_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    bonded_carrier_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    manifest_carrier_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    manifest_carrier_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    qp_filer_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    qp_filer_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    shipper_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    consignee_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    origination_port_name: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    destination_port_name: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)

    create_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    arrival_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    export_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    transfer_of_liability_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    days_late: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    days_overdue_for_export: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    late_in_transit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    overdue_for_export: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    penalty_indicator: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    authorization_status: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    authorization_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(String(40), nullable=False, default="clear", index=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    organization = relationship("Organization")
    events = relationship("AceInBondEvent", back_populates="movement", cascade="all, delete-orphan")


class AceInBondEvent(Base):
    __tablename__ = "ace_inbond_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    movement_id: Mapped[int] = mapped_column(Integer, ForeignKey("ace_inbond_movements.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    field_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)

    movement = relationship("AceInBondMovement", back_populates="events")


class AceImportRun(Base):
    __tablename__ = "ace_import_runs"
    __table_args__ = (UniqueConstraint("organization_id", "source_message_id", name="uq_ace_import_org_message"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    source_message_id: Mapped[str] = mapped_column(String(500), nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="processing", index=True)
    records_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exceptions_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
