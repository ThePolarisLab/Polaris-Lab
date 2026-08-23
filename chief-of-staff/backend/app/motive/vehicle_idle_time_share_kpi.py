"""Read-only observed Motive vehicle idle-time-share business KPI.

This KPI is descriptive only. It reads already-durable production utilization
rows, makes zero Motive provider calls, performs zero database writes, and does
not create alerts or executive-attention state. See
``docs/engineering/MOTIVE_IDLE_TIME_SHARE_SECOND_BUSINESS_KPI_DESIGN.md``.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.models.motive import MotiveVehicleRecord, MotiveVehicleUtilizationRecord
from app.motive.vehicle_utilization_operational_status import vehicle_utilization_operational_status
from app.motive.vehicle_utilization_production_ingestion import (
    PRODUCTION_FUEL_UNIT,
    PRODUCTION_HORIZON_DAYS,
    PRODUCTION_MAX_VEHICLES,
    PRODUCTION_TIME_ZONE,
    PRODUCTION_UNIT_REQUEST_MODE,
)

KPI_NAME = "observed_7_day_vehicle_idle_time_share"
_STATUS_AVAILABLE = "available_observed"
_STATUS_UNAVAILABLE = "unavailable"
_PERCENT_QUANTUM = Decimal("0.01")
_TIME_UNIT = "seconds"


def vehicle_idle_time_share_kpi(session: Session, organization_id: str) -> dict[str, Any]:
    """Return the sanitized tenant-scoped observed idle-time-share KPI.

    Any operational-contract inconsistency, historical-population ambiguity,
    duplicate durable identity, invalid time value, or read failure fails
    closed to ``status=unavailable`` without exposing exception details.
    """
    try:
        return _vehicle_idle_time_share_kpi(session, organization_id)
    except Exception:
        return _unavailable()


def _vehicle_idle_time_share_kpi(session: Session, organization_id: str) -> dict[str, Any]:
    operational = vehicle_utilization_operational_status(session, organization_id)
    if operational.get("operational_status") != "healthy":
        return _unavailable()

    production = _mapping(operational.get("production"))
    checkpoint = _mapping(operational.get("checkpoint"))
    counts = _mapping(production.get("counts"))

    if production.get("status") != "success" or checkpoint.get("status") != "success":
        return _unavailable()

    selected_vehicle_count = _positive_int(counts.get("selected_vehicle_count"))
    if selected_vehicle_count is None or selected_vehicle_count > PRODUCTION_MAX_VEHICLES:
        return _unavailable()

    if counts.get("horizon_days") != PRODUCTION_HORIZON_DAYS:
        return _unavailable()
    if counts.get("request_timezone") != PRODUCTION_TIME_ZONE:
        return _unavailable()
    if counts.get("unit_request_mode") != PRODUCTION_UNIT_REQUEST_MODE.value:
        return _unavailable()
    if counts.get("fuel_unit") != PRODUCTION_FUEL_UNIT:
        return _unavailable()
    if checkpoint.get("request_timezone") != PRODUCTION_TIME_ZONE:
        return _unavailable()
    if checkpoint.get("unit_request_mode") != PRODUCTION_UNIT_REQUEST_MODE.value:
        return _unavailable()
    if checkpoint.get("fuel_unit") != PRODUCTION_FUEL_UNIT:
        return _unavailable()

    window_end = _iso_date(checkpoint.get("completed_through"))
    if window_end is None:
        return _unavailable()
    window_start = window_end - timedelta(days=PRODUCTION_HORIZON_DAYS - 1)
    days = tuple(window_start + timedelta(days=offset) for offset in range(PRODUCTION_HORIZON_DAYS))
    day_set = set(days)

    # Production history persists only the selected count, not the historical
    # provider-ID population. Match the certified first KPI's conservative
    # guard: if today's tenant-owned stored population count differs, do not
    # guess which historical rows belonged to the successful run.
    current_vehicle_ids = [
        row[0]
        for row in (
            session.query(MotiveVehicleRecord.id)
            .filter(MotiveVehicleRecord.organization_id == organization_id)
            .order_by(MotiveVehicleRecord.id.asc())
            .all()
        )
    ]
    if len(current_vehicle_ids) != selected_vehicle_count:
        return _unavailable(
            window_start=window_start,
            window_end=window_end,
            selected_vehicle_count=selected_vehicle_count,
        )

    rows = (
        session.query(MotiveVehicleUtilizationRecord)
        .filter(
            MotiveVehicleUtilizationRecord.organization_id == organization_id,
            MotiveVehicleUtilizationRecord.provider == "motive",
            MotiveVehicleUtilizationRecord.motive_vehicle_id.in_(current_vehicle_ids),
            MotiveVehicleUtilizationRecord.request_window_start.in_(days),
            MotiveVehicleUtilizationRecord.request_window_end.in_(days),
        )
        .all()
    )

    by_identity: dict[tuple[int, date, date], MotiveVehicleUtilizationRecord] = {}
    for row in rows:
        if row.motive_vehicle_id is None:
            continue
        start = row.request_window_start
        end = row.request_window_end
        if start is None or end is None or start != end or start not in day_set:
            continue
        identity = (row.motive_vehicle_id, start, end)
        if identity in by_identity:
            return _unavailable(
                window_start=window_start,
                window_end=window_end,
                selected_vehicle_count=selected_vehicle_count,
            )
        by_identity[identity] = row

    expected_vehicle_days = selected_vehicle_count * PRODUCTION_HORIZON_DAYS
    provider_rollup_vehicle_days = len(by_identity)
    if provider_rollup_vehicle_days > expected_vehicle_days:
        return _unavailable(
            window_start=window_start,
            window_end=window_end,
            selected_vehicle_count=selected_vehicle_count,
        )

    missing_requested_vehicle_days = expected_vehicle_days - provider_rollup_vehicle_days
    provider_coverage = _percent(provider_rollup_vehicle_days, expected_vehicle_days)

    observed_idle_seconds = Decimal("0")
    observed_driving_seconds = Decimal("0")
    metric_valid_vehicle_days = 0

    for row in by_identity.values():
        # Retain the certified production provenance guard even though time is
        # always seconds; pre-production/non-current unit-context rows must not
        # silently enter this business KPI.
        if row.metric_units is not False:
            continue
        if row.idle_time is None or row.driving_time is None:
            continue

        idle_seconds = _decimal(row.idle_time)
        driving_seconds = _decimal(row.driving_time)
        if idle_seconds is None or driving_seconds is None:
            return _unavailable_with_provider_coverage(
                window_start=window_start,
                window_end=window_end,
                selected_vehicle_count=selected_vehicle_count,
                expected_requested_vehicle_days=expected_vehicle_days,
                provider_rollup_vehicle_days=provider_rollup_vehicle_days,
                missing_requested_vehicle_days=missing_requested_vehicle_days,
                provider_rollup_coverage_percent=provider_coverage,
            )
        if idle_seconds < 0 or driving_seconds < 0:
            return _unavailable_with_provider_coverage(
                window_start=window_start,
                window_end=window_end,
                selected_vehicle_count=selected_vehicle_count,
                expected_requested_vehicle_days=expected_vehicle_days,
                provider_rollup_vehicle_days=provider_rollup_vehicle_days,
                missing_requested_vehicle_days=missing_requested_vehicle_days,
                provider_rollup_coverage_percent=provider_coverage,
            )

        total_seconds = idle_seconds + driving_seconds
        if total_seconds <= 0:
            # A returned 0/0 row is real but has no positive denominator for a
            # share calculation, so it is incomplete for this KPI rather than
            # a synthetic 0% observation.
            continue

        observed_idle_seconds += idle_seconds
        observed_driving_seconds += driving_seconds
        metric_valid_vehicle_days += 1

    metric_coverage = _percent(metric_valid_vehicle_days, expected_vehicle_days)
    fleet_representative = metric_valid_vehicle_days == expected_vehicle_days
    observed_total_seconds = observed_idle_seconds + observed_driving_seconds

    if metric_valid_vehicle_days == 0 or observed_total_seconds <= 0:
        return _unavailable(
            window_start=window_start,
            window_end=window_end,
            selected_vehicle_count=selected_vehicle_count,
            expected_requested_vehicle_days=expected_vehicle_days,
            provider_rollup_vehicle_days=provider_rollup_vehicle_days,
            metric_valid_vehicle_days=metric_valid_vehicle_days,
            missing_requested_vehicle_days=missing_requested_vehicle_days,
            provider_rollup_coverage_percent=provider_coverage,
            idle_time_metric_coverage_percent=metric_coverage,
        )

    value_percent = _quantize((observed_idle_seconds * Decimal("100")) / observed_total_seconds)
    return _payload(
        status=_STATUS_AVAILABLE,
        window_start=window_start,
        window_end=window_end,
        value_percent=value_percent,
        selected_vehicle_count=selected_vehicle_count,
        expected_requested_vehicle_days=expected_vehicle_days,
        provider_rollup_vehicle_days=provider_rollup_vehicle_days,
        metric_valid_vehicle_days=metric_valid_vehicle_days,
        missing_requested_vehicle_days=missing_requested_vehicle_days,
        provider_rollup_coverage_percent=provider_coverage,
        idle_time_metric_coverage_percent=metric_coverage,
        fleet_representative=fleet_representative,
    )


def _unavailable_with_provider_coverage(
    *,
    window_start: date,
    window_end: date,
    selected_vehicle_count: int,
    expected_requested_vehicle_days: int,
    provider_rollup_vehicle_days: int,
    missing_requested_vehicle_days: int,
    provider_rollup_coverage_percent: float,
) -> dict[str, Any]:
    return _unavailable(
        window_start=window_start,
        window_end=window_end,
        selected_vehicle_count=selected_vehicle_count,
        expected_requested_vehicle_days=expected_requested_vehicle_days,
        provider_rollup_vehicle_days=provider_rollup_vehicle_days,
        metric_valid_vehicle_days=None,
        missing_requested_vehicle_days=missing_requested_vehicle_days,
        provider_rollup_coverage_percent=provider_rollup_coverage_percent,
        idle_time_metric_coverage_percent=None,
    )


def _payload(
    *,
    status: str,
    window_start: date | None,
    window_end: date | None,
    value_percent: float | None,
    selected_vehicle_count: int | None,
    expected_requested_vehicle_days: int | None,
    provider_rollup_vehicle_days: int | None,
    metric_valid_vehicle_days: int | None,
    missing_requested_vehicle_days: int | None,
    provider_rollup_coverage_percent: float | None,
    idle_time_metric_coverage_percent: float | None,
    fleet_representative: bool,
) -> dict[str, Any]:
    return {
        "status": status,
        "kpi": KPI_NAME,
        "window_start": window_start.isoformat() if window_start is not None else None,
        "window_end": window_end.isoformat() if window_end is not None else None,
        "request_timezone": PRODUCTION_TIME_ZONE,
        "value_percent": value_percent,
        "selected_vehicle_count": selected_vehicle_count,
        "expected_requested_vehicle_days": expected_requested_vehicle_days,
        "provider_rollup_vehicle_days": provider_rollup_vehicle_days,
        "metric_valid_vehicle_days": metric_valid_vehicle_days,
        "missing_requested_vehicle_days": missing_requested_vehicle_days,
        "provider_rollup_coverage_percent": provider_rollup_coverage_percent,
        "idle_time_metric_coverage_percent": idle_time_metric_coverage_percent,
        "fleet_representative": fleet_representative,
        "time_unit": _TIME_UNIT,
        "unit_request_mode": PRODUCTION_UNIT_REQUEST_MODE.value,
        "secrets_exposed": False,
    }


def _unavailable(
    *,
    window_start: date | None = None,
    window_end: date | None = None,
    selected_vehicle_count: int | None = None,
    expected_requested_vehicle_days: int | None = None,
    provider_rollup_vehicle_days: int | None = None,
    metric_valid_vehicle_days: int | None = None,
    missing_requested_vehicle_days: int | None = None,
    provider_rollup_coverage_percent: float | None = None,
    idle_time_metric_coverage_percent: float | None = None,
) -> dict[str, Any]:
    return _payload(
        status=_STATUS_UNAVAILABLE,
        window_start=window_start,
        window_end=window_end,
        value_percent=None,
        selected_vehicle_count=selected_vehicle_count,
        expected_requested_vehicle_days=expected_requested_vehicle_days,
        provider_rollup_vehicle_days=provider_rollup_vehicle_days,
        metric_valid_vehicle_days=metric_valid_vehicle_days,
        missing_requested_vehicle_days=missing_requested_vehicle_days,
        provider_rollup_coverage_percent=provider_rollup_coverage_percent,
        idle_time_metric_coverage_percent=idle_time_metric_coverage_percent,
        fleet_representative=False,
    )


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _decimal(value: Any) -> Decimal | None:
    try:
        resolved = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return resolved if resolved.is_finite() else None


def _quantize(value: Decimal) -> float:
    return float(value.quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_UP))


def _percent(numerator: int, denominator: int) -> float:
    return _quantize((Decimal(numerator) * Decimal("100")) / Decimal(denominator))
