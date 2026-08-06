"""Normalized internal Motive contracts for Polaris.

These dataclasses are the production boundary shape used inside chief-of-staff.
Raw Motive provider payloads must stay inside connector/client code and must not
be returned through executive APIs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

MOTIVE_PROVIDER = "motive"


@dataclass(frozen=True, slots=True)
class MotiveVehicle:
    organization_id: str
    organization_slug: str
    provider_vehicle_id: str
    source_endpoint: str
    unit_number: str | None = None
    vin: str | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    license_plate: str | None = None
    status: str | None = None
    observed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MotiveDriver:
    organization_id: str
    organization_slug: str
    provider_driver_id: str | None
    source_endpoint: str | None = None
    name: str | None = None
    email: str | None = None
    status: str | None = None
    observed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MotiveVehicleUtilization:
    organization_id: str
    organization_slug: str
    provider_vehicle_id: str | None
    source_endpoint: str
    reporting_period_start: date | None = None
    reporting_period_end: date | None = None
    utilization_percent: Decimal | None = None
    distance: Decimal | None = None
    engine_hours: Decimal | None = None
    observed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MotiveDriverUtilization:
    organization_id: str
    organization_slug: str
    provider_driver_id: str | None
    source_endpoint: str
    reporting_period_start: date | None = None
    reporting_period_end: date | None = None
    utilization_percent: Decimal | None = None
    distance: Decimal | None = None
    driving_time_seconds: int | None = None
    observed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MotiveIftaSummary:
    organization_id: str
    organization_slug: str
    provider_vehicle_id: str | None
    jurisdiction: str | None
    source_endpoint: str
    reporting_period_start: date | None = None
    reporting_period_end: date | None = None
    distance: Decimal | None = None
    fuel_volume: Decimal | None = None
    observed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
