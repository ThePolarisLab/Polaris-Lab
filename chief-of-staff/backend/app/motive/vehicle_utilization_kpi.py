"""Read-only business KPI over durable Motive vehicle-utilization rows.

The KPI is intentionally observational. It never calls Motive, never writes to
the database, never changes operational health, and never creates executive
attention. See docs/engineering/MOTIVE_UTILIZATION_FIRST_BUSINESS_KPI_DESIGN.md.
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

KPI_NAME = "observed_7_day_vehicle_utilization"
_STATUS_AVAILABLE = "available_observed"
_STATUS_UNAVAILABLE = "unavailable"
_PERCENT_QUANTUM = Decimal("0.01")


def vehicle_utilization_kpi(session: Session, organization_id: str) -> dict[str, Any]:
    """Return the sanitized tenant-scoped first Motive utilization KPI.

    This function is fail-closed: any operational-contract inconsistency,
    historical-population ambiguity, malformed persisted value, or read error
    returns ``status=unavailable`` without exposing an exception string.
    """
    try:
        return _vehicle_utilization_kpi(session, organization_id)
    except Exception:
        return _unavailable()


def _vehicle_utilization_kpi(session: Session, organization_id: str) -> dict[str, Any]:
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

    # Production ingestion selects every tenant-owned stored Motive vehicle and
    # refuses to run above PRODUCTION_MAX_VEHICLES. The history stores only the
    # count, not the selected IDs. If the current stored population count has
    # changed since that run, the historical selected population cannot be
    # reconstructed safely, so the KPI is unavailable rather than guessed.
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

    metric_values: list[Decimal] = []
    for row in by_identity.values():
        if row.metric_units is not False or row.utilization_percent is None:
            continue
        value = _decimal(row.utilization_percent)
        if value is not None:
            metric_values.append(value)

    metric_valid_vehicle_days = len(metric_values)
    missing_requested_vehicle_days = expected_vehicle_days - provider_rollup_vehicle_days
    provider_coverage = _percent(provider_rollup_vehicle_days, expected_vehicle_days)
    metric_coverage = _percent(metric_valid_vehicle_days, expected_vehicle_days)
    fleet_representative = metric_valid_vehicle_days == expected_vehicle_days

    if not metric_values:
        return _unavailable(
            window_start=window_start,
            window_end=window_end,
            selected_vehicle_count=selected_vehicle_count,
            expected_requested_vehicle_days=expected_vehicle_days,
            provider_rollup_vehicle_days=provider_rollup_vehicle_days,
            metric_valid_vehicle_days=0,
            missing_requested_vehicle_days=missing_requested_vehicle_days,
            provider_rollup_coverage_percent=provider_coverage,
            utilization_metric_coverage_percent=metric_coverage,
        )

    value_percent = _quantize(sum(metric_values, Decimal("0")) / Decimal(metric_valid_vehicle_days))
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
        utilization_metric_coverage_percent=metric_coverage,
        fleet_representative=fleet_representative,
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
    utilization_metric_coverage_percent: float | None,
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
        "utilization_metric_coverage_percent": utilization_metric_coverage_percent,
        "fleet_representative": fleet_representative,
        "fuel_unit": PRODUCTION_FUEL_UNIT,
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
    utilization_metric_coverage_percent: float | None = None,
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
        utilization_metric_coverage_percent=utilization_metric_coverage_percent,
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
