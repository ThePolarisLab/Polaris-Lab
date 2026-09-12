"""Tenant-owned durable maintenance issue memory derived from certified Motive signals."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MotiveMaintenanceIssueMemory(Base):
    __tablename__ = "motive_maintenance_issue_memory"
    __table_args__ = (
        UniqueConstraint("organization_id", "truck_number", "identity_key", name="uq_motive_maintenance_issue_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    organization_slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    truck_number: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    identity_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    part_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    part_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    part_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lifecycle_state: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    first_open_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    last_seen_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_odometer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    explicit_resolution_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    explicit_resolution_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    last_reopened_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    reopen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    disappearance_means_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    organization = relationship("Organization")
    events = relationship("MotiveMaintenanceIssueEvent", back_populates="issue", cascade="all, delete-orphan")


class MotiveMaintenanceIssueEvent(Base):
    __tablename__ = "motive_maintenance_issue_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "source_fingerprint", name="uq_motive_maintenance_event_fingerprint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    issue_id: Mapped[int] = mapped_column(Integer, ForeignKey("motive_maintenance_issue_memory.id"), nullable=False, index=True)
    truck_number: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    identity_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    structured_status: Mapped[str] = mapped_column(String(60), nullable=False)
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    report_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    odometer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_endpoint: Mapped[str] = mapped_column(String(120), nullable=False, default="/v2/inspection_reports")
    provider_write_performed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    organization = relationship("Organization")
    issue = relationship("MotiveMaintenanceIssueMemory", back_populates="events")
