"""Tenant-owned Motive persistence for the production OAuth foundation gate."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MotiveCredential(Base):
    __tablename__ = "motive_credentials"
    __table_args__ = (
        UniqueConstraint("organization_id", "authentication_method", name="uq_motive_credential_org_method"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    organization_slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False, default="motive", index=True)
    authentication_method: Mapped[str] = mapped_column(String(40), nullable=False, default="oauth2", index=True)
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    granted_scopes: Mapped[str] = mapped_column(Text, nullable=False)
    token_type: Mapped[str] = mapped_column(String(40), nullable=False, default="Bearer")
    provider_company_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    provider_company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    connection_status: Mapped[str] = mapped_column(String(60), nullable=False, default="configured_unverified", index=True)
    authorization_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_error_message_sanitized: Mapped[str | None] = mapped_column(Text, nullable=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    organization = relationship("Organization")


class MotiveOAuthState(Base):
    __tablename__ = "motive_oauth_states"

    state: Mapped[str] = mapped_column(String(255), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    identity_id: Mapped[str] = mapped_column(String, ForeignKey("identities.id"), nullable=False, index=True)
    nonce: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    organization = relationship("Organization")
    identity = relationship("Identity")


class MotiveSyncHistory(Base):
    __tablename__ = "motive_sync_history"
    __table_args__ = (UniqueConstraint("run_id", name="uq_motive_sync_history_run_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    organization_slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False, default="motive", index=True)
    provider_resource: Mapped[str] = mapped_column(String(80), nullable=False, default="verification")
    mode: Mapped[str] = mapped_column(String(40), nullable=False, default="verification")
    status: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message_sanitized: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkpoint_before: Mapped[dict] = mapped_column(JSON, default=dict)
    checkpoint_after: Mapped[dict] = mapped_column(JSON, default=dict)
    resource_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    organization = relationship("Organization")


class MotiveSyncCheckpoint(Base):
    __tablename__ = "motive_sync_checkpoints"
    __table_args__ = (UniqueConstraint("organization_id", "provider_resource", name="uq_motive_checkpoint_org_resource"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    organization_slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False, default="motive", index=True)
    provider_resource: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_after_watermark: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_successful_position: Mapped[dict] = mapped_column(JSON, default=dict)
    checkpoint_status: Mapped[str] = mapped_column(String(60), nullable=False, default="not_started")
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    organization = relationship("Organization")


class MotiveVehicleRecord(Base):
    __tablename__ = "motive_vehicles"
    __table_args__ = (UniqueConstraint("organization_id", "provider_vehicle_id", name="uq_motive_vehicle_org_provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    organization_slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False, default="motive", index=True)
    provider_vehicle_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    source_endpoint: Mapped[str] = mapped_column(String(120), nullable=False, default="/v1/vehicles")
    unit_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vin: Mapped[str | None] = mapped_column(String(80), nullable=True)
    make: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    license_plate: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_payload_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    organization = relationship("Organization")


class MotiveDriverRecord(Base):
    __tablename__ = "motive_drivers"
    __table_args__ = (UniqueConstraint("organization_id", "provider_driver_id", name="uq_motive_driver_org_provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    organization_slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False, default="motive", index=True)
    provider_driver_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    source_endpoint: Mapped[str | None] = mapped_column(String(120), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_payload_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    organization = relationship("Organization")


class MotiveVehicleUtilizationRecord(Base):
    __tablename__ = "motive_vehicle_utilization"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "provider_vehicle_id", "reporting_period_start", "reporting_period_end",
            name="uq_motive_vehicle_util_org_period",
        ),
        UniqueConstraint(
            "organization_id", "motive_vehicle_id", "request_window_start", "request_window_end",
            name="uq_motive_vehicle_util_org_vehicle_request_window",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    organization_slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False, default="motive", index=True)
    provider_vehicle_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    motive_vehicle_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("motive_vehicles.id"), nullable=True, index=True)
    source_endpoint: Mapped[str] = mapped_column(String(120), nullable=False, default="/v1/vehicle_utilization")
    request_window_start: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    request_window_end: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    reporting_period_start: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    reporting_period_end: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    utilization_percent: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    idle_time: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    driving_time: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    idle_fuel: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    driving_fuel: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    # 2026-08-16 unit-semantics-certification gate audit (section 11),
    # updated 2026-08-17 (authentication + unit-mismatch certification
    # gate): this column stores the RAW PROVIDER-OBSERVED
    # `vehicle_idle_rollups[].vehicle_idle_rollup.vehicle.metric_units`
    # Boolean from GET /v1/vehicle_utilization -- Motive's returned unit
    # INDICATOR (see app.motive.vehicle_utilization_unit_policy). Motive API
    # Support's 2026-08-17 written reply confirmed this Boolean's meaning:
    # `true` = metric, `false` = imperial. Every row this writer has ever
    # inserted (and will insert while the writer stays gated to the
    # canonical X-Metric-Units=true request policy) has -- and must have --
    # `metric_units = True`, because a returned `False` for a `true` request
    # is a provider-confirmed mismatch that fails closed before any commit
    # (`validate_vehicle_utilization_unit_persistence_readiness`). So for
    # every row that exists, or ever will exist, in this table today, this
    # column IS now trustworthy fuel-unit provenance for that row's
    # `idle_fuel`/`driving_fuel` values (liters), not merely a raw,
    # unrelated vehicle-configuration echo.
    #
    # It still conceptually conflates two ideas that happen to coincide
    # under the current canonical-request-only writer: "the provider's
    # returned unit indicator for this response" and "the certified
    # measurement-system provenance of this row's persisted fuel values."
    # They stay numerically identical only because the writer never accepts
    # a mismatched or non-canonical request/response pair. If a future gate
    # ever allows requesting X-Metric-Units=false (imperial) rows, or
    # otherwise decouples the two ideas, a distinct, explicitly-named
    # provenance/measurement-system column would be needed instead of
    # redefining this one -- see docs/engineering/MOTIVE_AUTHENTICATION_CERTIFICATION.md
    # and docs/engineering/MOTIVE_UTILIZATION_UNIT_SEMANTICS_CERTIFICATION.md.
    # NO migration is made in this gate.
    metric_units: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    distance: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    engine_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provider_payload_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    organization = relationship("Organization")
    motive_vehicle = relationship("MotiveVehicleRecord")


class MotiveDriverUtilizationRecord(Base):
    __tablename__ = "motive_driver_utilization"
    __table_args__ = (UniqueConstraint("organization_id", "provider_driver_id", "reporting_period_start", "reporting_period_end", name="uq_motive_driver_util_org_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    organization_slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False, default="motive", index=True)
    provider_driver_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    source_endpoint: Mapped[str] = mapped_column(String(120), nullable=False, default="/v2/driver_utilization")
    reporting_period_start: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    reporting_period_end: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    utilization_percent: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    distance: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    driving_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_payload_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    organization = relationship("Organization")


class MotiveIftaSummaryRecord(Base):
    __tablename__ = "motive_ifta_summaries"
    __table_args__ = (UniqueConstraint("organization_id", "provider_vehicle_id", "jurisdiction", "reporting_period_start", "reporting_period_end", name="uq_motive_ifta_org_vehicle_jurisdiction_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    organization_slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False, default="motive", index=True)
    provider_vehicle_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    source_endpoint: Mapped[str] = mapped_column(String(120), nullable=False, default="/v1/ifta/summary")
    reporting_period_start: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    reporting_period_end: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    distance: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    fuel_volume: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_payload_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    organization = relationship("Organization")
