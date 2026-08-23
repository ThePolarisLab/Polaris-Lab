"""Tenant-owned aggregate history for certified Motive utilization KPI observations."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MotiveVehicleUtilizationKpiSnapshot(Base):
    """One canonical aggregate observation per tenant/KPI/seven-day window."""

    __tablename__ = "motive_vehicle_utilization_kpi_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "kpi",
            "window_start",
            "window_end",
            name="uq_motive_vehicle_util_kpi_snapshot_org_window",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    organization_slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    kpi: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    kpi_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    window_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    window_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    request_timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    value_percent: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    selected_vehicle_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_requested_vehicle_days: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_rollup_vehicle_days: Mapped[int] = mapped_column(Integer, nullable=False)
    metric_valid_vehicle_days: Mapped[int] = mapped_column(Integer, nullable=False)
    missing_requested_vehicle_days: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_rollup_coverage_percent: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    utilization_metric_coverage_percent: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    fleet_representative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fuel_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    unit_request_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    source_history_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("motive_sync_history.id"),
        nullable=False,
        index=True,
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    organization = relationship("Organization")
    source_history = relationship("MotiveSyncHistory")
