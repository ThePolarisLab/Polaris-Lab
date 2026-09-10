"""Tenant-scoped durable TorqueAI dispatch persistence models."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TorqueAIDispatch(Base):
    """Minimized durable operational dispatch record from TorqueAI."""

    __tablename__ = "torqueai_dispatches"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider_load_number",
            "provider_order_number",
            name="uq_torqueai_dispatch_org_provider_identity",
        ),
        CheckConstraint("loaded_miles IS NULL OR loaded_miles >= 0", name="ck_torqueai_dispatch_loaded_miles_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id", name="fk_torqueai_dispatches_organization_id"), nullable=False, index=True)
    provider_load_number: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_order_number: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    order_date_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ship_date_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    delivery_date_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dispatcher_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    driver_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    carrier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    truck_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    trailer_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    loaded_miles: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    organization = relationship("Organization")
    operational_enrichment = relationship("TorqueAIDispatchOperational", back_populates="dispatch", uselist=False, cascade="all, delete-orphan")
    operational_stops = relationship("TorqueAIDispatchStop", back_populates="dispatch", cascade="all, delete-orphan", order_by="TorqueAIDispatchStop.stop_index")


class TorqueAIDispatchOperational(Base):
    """One-to-one enrichment for live-certified TorqueAI fields beyond the original gate."""

    __tablename__ = "torqueai_dispatch_operational"
    __table_args__ = (
        UniqueConstraint("dispatch_id", name="uq_torqueai_dispatch_operational_dispatch"),
        UniqueConstraint("organization_id", "dispatch_id", name="uq_torqueai_dispatch_operational_org_dispatch"),
        CheckConstraint("stop_count IS NULL OR stop_count >= 0", name="ck_torqueai_dispatch_operational_stop_count_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id", name="fk_torqueai_dispatch_operational_organization_id"), nullable=False, index=True)
    dispatch_id: Mapped[int] = mapped_column(Integer, ForeignKey("torqueai_dispatches.id", name="fk_torqueai_dispatch_operational_dispatch_id", ondelete="CASCADE"), nullable=False, index=True)
    currency: Mapped[str | None] = mapped_column(String(12), nullable=True)
    total_charge: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    billing_currency: Mapped[str | None] = mapped_column(String(12), nullable=True)
    billing_rate: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    billing_subtotal: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    billing_tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    billing_total: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    stop_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    organization = relationship("Organization")
    dispatch = relationship("TorqueAIDispatch", back_populates="operational_enrichment")


class TorqueAIDispatchStop(Base):
    """Normalized whitelist of production-certified TorqueAI stop fields."""

    __tablename__ = "torqueai_dispatch_stops"
    __table_args__ = (
        UniqueConstraint("organization_id", "dispatch_id", "stop_index", name="uq_torqueai_dispatch_stop_org_dispatch_index"),
        CheckConstraint("stop_index >= 0", name="ck_torqueai_dispatch_stop_index_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id", name="fk_torqueai_dispatch_stops_organization_id"), nullable=False, index=True)
    dispatch_id: Mapped[int] = mapped_column(Integer, ForeignKey("torqueai_dispatches.id", name="fk_torqueai_dispatch_stops_dispatch_id", ondelete="CASCADE"), nullable=False, index=True)
    stop_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    stop_no: Mapped[str | None] = mapped_column(String(120), nullable=True)
    job: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    province: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    zip_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    commodity: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    driver_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    co_driver_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    carrier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    truck_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    trailer_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    scheduled_is_window: Mapped[bool | None] = mapped_column(nullable=True)
    scheduled_pickup_date_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    scheduled_pickup_date2_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    scheduled_pickup_time_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    scheduled_pickup_time2_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    temperature_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    temperature_unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    organization = relationship("Organization")
    dispatch = relationship("TorqueAIDispatch", back_populates="operational_stops")


class TorqueAIDispatchSyncRun(Base):
    """Sanitized evidence for one explicit TorqueAI dispatch ingestion attempt."""

    __tablename__ = "torqueai_dispatch_sync_runs"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_torqueai_dispatch_sync_run_id"),
        UniqueConstraint("organization_id", "trigger_mode", "trigger_slot", name="uq_torqueai_dispatch_sync_scheduled_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(120), nullable=False)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id", name="fk_torqueai_dispatch_sync_runs_organization_id"), nullable=False, index=True)
    requested_from: Mapped[date] = mapped_column(Date, nullable=False)
    requested_to: Mapped[date] = mapped_column(Date, nullable=False)
    page_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    trigger_mode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    trigger_slot: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pages_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_total_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_validated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    organization = relationship("Organization")


class TorqueAIDispatchSyncState(Base):
    """Tenant-scoped evidence of the most recent successful requested window."""

    __tablename__ = "torqueai_dispatch_sync_state"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_torqueai_dispatch_sync_state_org"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id", name="fk_torqueai_dispatch_sync_state_organization_id"), nullable=False)
    last_successful_window_start: Mapped[date] = mapped_column(Date, nullable=False)
    last_successful_window_end: Mapped[date] = mapped_column(Date, nullable=False)
    last_successful_run_id: Mapped[str] = mapped_column(String(120), nullable=False)
    last_successful_completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    organization = relationship("Organization")
