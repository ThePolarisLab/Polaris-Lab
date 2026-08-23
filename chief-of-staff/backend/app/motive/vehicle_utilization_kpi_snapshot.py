"""Pure calculation and local upsert primitives for Motive utilization KPI history.

This module is intentionally not wired to production ingestion or scheduling in
this gate. It makes no Motive provider calls. Callers must supply the exact
provider vehicle-ID population selected by the successful production run.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.motive import MotiveSyncHistory, MotiveVehicleUtilizationRecord
from app.models.motive_kpi_snapshot import MotiveVehicleUtilizationKpiSnapshot
from app.motive.vehicle_utilization_production_ingestion import (
    PRODUCTION_FUEL_UNIT,
    PRODUCTION_HORIZON_DAYS,
    PRODUCTION_MAX_VEHICLES,
    PRODUCTION_TIME_ZONE,
    PRODUCTION_UNIT_REQUEST_MODE,
    RESOURCE,
    RUN_MODE,
)

KPI_NAME = "observed_7_day_vehicle_utilization"
KPI_VERSION = 1
STATUS_AVAILABLE = "available_observed"
STATUS_UNAVAILABLE = "unavailable"
_PERCENT_QUANTUM = Decimal("0.01")


class MotiveVehicleUtilizationKpiSnapshotError(RuntimeError):
    """Sanitized snapshot calculation or persistence-contract failure."""


@dataclass(frozen=True, slots=True)
class VehicleUtilizationKpiSnapshotComputation:
    organization_id: str
    organization_slug: str
    kpi: str
    kpi_version: int
    status: str
    window_start: date
    window_end: date
    request_timezone: str
    value_percent: Decimal | None
    selected_vehicle_count: int
    expected_requested_vehicle_days: int
    provider_rollup_vehicle_days: int
    metric_valid_vehicle_days: int
    missing_requested_vehicle_days: int
    provider_rollup_coverage_percent: Decimal
    utilization_metric_coverage_percent: Decimal
    fleet_representative: bool
    fuel_unit: str
    unit_request_mode: str


def normalize_selected_provider_vehicle_ids(values: Sequence[str]) -> tuple[str, ...]:
    """Validate the exact selected provider population without consulting fleet state."""
    selected: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise MotiveVehicleUtilizationKpiSnapshotError(
                "Snapshot calculation requires a non-empty provider vehicle identity for every selected vehicle."
            )
        selected.append(value.strip())
    if not selected:
        raise MotiveVehicleUtilizationKpiSnapshotError(
            "Snapshot calculation requires at least one selected vehicle."
        )
    if len(selected) > PRODUCTION_MAX_VEHICLES:
        raise MotiveVehicleUtilizationKpiSnapshotError(
            "Snapshot calculation exceeds the certified production vehicle bound."
        )
    if len(set(selected)) != len(selected):
        raise MotiveVehicleUtilizationKpiSnapshotError(
            "Snapshot calculation requires a unique selected vehicle population."
        )
    return tuple(selected)


def load_vehicle_utilization_snapshot_rows(
    session: Session,
    *,
    organization_id: str,
    selected_provider_vehicle_ids: Sequence[str],
    window_end: date,
) -> list[MotiveVehicleUtilizationRecord]:
    """Read only the candidate durable rows for the exact run selection and window."""
    selected = normalize_selected_provider_vehicle_ids(selected_provider_vehicle_ids)
    window_start = window_end - timedelta(days=PRODUCTION_HORIZON_DAYS - 1)
    days = tuple(window_start + timedelta(days=offset) for offset in range(PRODUCTION_HORIZON_DAYS))
    return (
        session.query(MotiveVehicleUtilizationRecord)
        .filter(
            MotiveVehicleUtilizationRecord.organization_id == organization_id,
            MotiveVehicleUtilizationRecord.provider == "motive",
            MotiveVehicleUtilizationRecord.provider_vehicle_id.in_(selected),
            MotiveVehicleUtilizationRecord.request_window_start.in_(days),
            MotiveVehicleUtilizationRecord.request_window_end.in_(days),
        )
        .all()
    )


def calculate_vehicle_utilization_kpi_snapshot(
    *,
    organization_id: str,
    organization_slug: str,
    selected_provider_vehicle_ids: Sequence[str],
    window_end: date,
    rows: Iterable[MotiveVehicleUtilizationRecord],
) -> VehicleUtilizationKpiSnapshotComputation:
    """Calculate one certified seven-day observation from durable rows only."""
    if not organization_id or not organization_slug:
        raise MotiveVehicleUtilizationKpiSnapshotError(
            "Snapshot calculation requires tenant identity."
        )
    if not isinstance(window_end, date):
        raise MotiveVehicleUtilizationKpiSnapshotError(
            "Snapshot calculation requires a valid completed window end date."
        )

    selected = normalize_selected_provider_vehicle_ids(selected_provider_vehicle_ids)
    selected_set = set(selected)
    window_start = window_end - timedelta(days=PRODUCTION_HORIZON_DAYS - 1)
    days = tuple(window_start + timedelta(days=offset) for offset in range(PRODUCTION_HORIZON_DAYS))
    day_set = set(days)

    by_identity: dict[tuple[str, date, date], MotiveVehicleUtilizationRecord] = {}
    for row in rows:
        if row.organization_id != organization_id or row.provider != "motive":
            continue
        provider_vehicle_id = row.provider_vehicle_id
        if not isinstance(provider_vehicle_id, str) or provider_vehicle_id not in selected_set:
            continue
        start = row.request_window_start
        end = row.request_window_end
        if start is None or end is None or start != end or start not in day_set:
            continue
        identity = (provider_vehicle_id, start, end)
        if identity in by_identity:
            raise MotiveVehicleUtilizationKpiSnapshotError(
                "Snapshot source rows contain a duplicate selected vehicle-day identity."
            )
        by_identity[identity] = row

    expected_vehicle_days = len(selected) * PRODUCTION_HORIZON_DAYS
    provider_rollup_vehicle_days = len(by_identity)
    if provider_rollup_vehicle_days > expected_vehicle_days:
        raise MotiveVehicleUtilizationKpiSnapshotError(
            "Snapshot source row count exceeds the certified denominator."
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

    if metric_values:
        status = STATUS_AVAILABLE
        value_percent = _quantize(sum(metric_values, Decimal("0")) / Decimal(metric_valid_vehicle_days))
    else:
        status = STATUS_UNAVAILABLE
        value_percent = None

    return VehicleUtilizationKpiSnapshotComputation(
        organization_id=organization_id,
        organization_slug=organization_slug,
        kpi=KPI_NAME,
        kpi_version=KPI_VERSION,
        status=status,
        window_start=window_start,
        window_end=window_end,
        request_timezone=PRODUCTION_TIME_ZONE,
        value_percent=value_percent,
        selected_vehicle_count=len(selected),
        expected_requested_vehicle_days=expected_vehicle_days,
        provider_rollup_vehicle_days=provider_rollup_vehicle_days,
        metric_valid_vehicle_days=metric_valid_vehicle_days,
        missing_requested_vehicle_days=missing_requested_vehicle_days,
        provider_rollup_coverage_percent=provider_coverage,
        utilization_metric_coverage_percent=metric_coverage,
        fleet_representative=fleet_representative,
        fuel_unit=PRODUCTION_FUEL_UNIT,
        unit_request_mode=PRODUCTION_UNIT_REQUEST_MODE.value,
    )


def upsert_vehicle_utilization_kpi_snapshot(
    session: Session,
    *,
    computation: VehicleUtilizationKpiSnapshotComputation,
    source_history_id: int,
    computed_at: datetime | None = None,
) -> MotiveVehicleUtilizationKpiSnapshot:
    """Upsert one canonical point without committing the caller's transaction."""
    history = (
        session.query(MotiveSyncHistory)
        .filter(
            MotiveSyncHistory.id == source_history_id,
            MotiveSyncHistory.organization_id == computation.organization_id,
            MotiveSyncHistory.provider == "motive",
            MotiveSyncHistory.provider_resource == RESOURCE,
            MotiveSyncHistory.mode == RUN_MODE,
            MotiveSyncHistory.status == "success",
        )
        .one_or_none()
    )
    if history is None:
        raise MotiveVehicleUtilizationKpiSnapshotError(
            "Snapshot source history is not a successful production utilization run for this tenant."
        )
    _validate_history_contract(history, computation)

    row = (
        session.query(MotiveVehicleUtilizationKpiSnapshot)
        .filter(
            MotiveVehicleUtilizationKpiSnapshot.organization_id == computation.organization_id,
            MotiveVehicleUtilizationKpiSnapshot.kpi == computation.kpi,
            MotiveVehicleUtilizationKpiSnapshot.window_start == computation.window_start,
            MotiveVehicleUtilizationKpiSnapshot.window_end == computation.window_end,
        )
        .one_or_none()
    )
    if row is None:
        row = MotiveVehicleUtilizationKpiSnapshot(
            organization_id=computation.organization_id,
            organization_slug=computation.organization_slug,
            kpi=computation.kpi,
            window_start=computation.window_start,
            window_end=computation.window_end,
        )
        session.add(row)

    resolved_computed_at = computed_at or datetime.now(timezone.utc)
    row.organization_slug = computation.organization_slug
    row.kpi_version = computation.kpi_version
    row.status = computation.status
    row.request_timezone = computation.request_timezone
    row.value_percent = computation.value_percent
    row.selected_vehicle_count = computation.selected_vehicle_count
    row.expected_requested_vehicle_days = computation.expected_requested_vehicle_days
    row.provider_rollup_vehicle_days = computation.provider_rollup_vehicle_days
    row.metric_valid_vehicle_days = computation.metric_valid_vehicle_days
    row.missing_requested_vehicle_days = computation.missing_requested_vehicle_days
    row.provider_rollup_coverage_percent = computation.provider_rollup_coverage_percent
    row.utilization_metric_coverage_percent = computation.utilization_metric_coverage_percent
    row.fleet_representative = computation.fleet_representative
    row.fuel_unit = computation.fuel_unit
    row.unit_request_mode = computation.unit_request_mode
    row.source_history_id = source_history_id
    row.computed_at = resolved_computed_at
    session.flush()
    return row


def _validate_history_contract(
    history: MotiveSyncHistory,
    computation: VehicleUtilizationKpiSnapshotComputation,
) -> None:
    counts = history.resource_counts if isinstance(history.resource_counts, dict) else {}
    checkpoint_after = history.checkpoint_after if isinstance(history.checkpoint_after, dict) else {}
    expected = {
        "horizon_days": PRODUCTION_HORIZON_DAYS,
        "request_timezone": PRODUCTION_TIME_ZONE,
        "unit_request_mode": PRODUCTION_UNIT_REQUEST_MODE.value,
        "fuel_unit": PRODUCTION_FUEL_UNIT,
        "selected_vehicle_count": computation.selected_vehicle_count,
    }
    for key, value in expected.items():
        if counts.get(key) != value:
            raise MotiveVehicleUtilizationKpiSnapshotError(
                "Snapshot source history does not match the certified KPI computation contract."
            )
    if counts.get("x_metric_units") is not False:
        raise MotiveVehicleUtilizationKpiSnapshotError(
            "Snapshot source history does not match the certified KPI unit contract."
        )
    if checkpoint_after.get("completed_through") != computation.window_end.isoformat():
        raise MotiveVehicleUtilizationKpiSnapshotError(
            "Snapshot source history does not match the computed completed window."
        )


def _decimal(value: object) -> Decimal | None:
    try:
        resolved = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return resolved if resolved.is_finite() else None


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def _percent(numerator: int, denominator: int) -> Decimal:
    return _quantize((Decimal(numerator) * Decimal("100")) / Decimal(denominator))
