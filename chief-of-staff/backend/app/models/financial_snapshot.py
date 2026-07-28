"""Durable QuickBooks financial snapshots owned by Polaris."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class FinancialAccount(Base):
    __tablename__ = "financial_accounts"
    __table_args__ = (UniqueConstraint("organization_slug", "qbo_id", name="uq_financial_account_org_qbo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_slug: Mapped[str] = mapped_column(String(120), index=True)
    qbo_id: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(255))
    fully_qualified_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    account_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    account_subtype: Mapped[str | None] = mapped_column(String(120), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    current_balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class FinancialSnapshot(Base):
    __tablename__ = "financial_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_slug: Mapped[str] = mapped_column(String(120), index=True)
    snapshot_type: Mapped[str] = mapped_column(String(50), index=True)
    period_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    period_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    accounting_method: Mapped[str] = mapped_column(String(20), default="Accrual")
    payload: Mapped[dict] = mapped_column(JSON)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class FinancialSyncHistory(Base):
    __tablename__ = "financial_sync_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_slug: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accounts_imported: Mapped[int] = mapped_column(Integer, default=0)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
