"""Read-only aggregate history for certified Motive utilization KPI snapshots."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.motive_kpi_snapshot import MotiveVehicleUtilizationKpiSnapshot
from app.motive.vehicle_utilization_kpi_snapshot import KPI_NAME
from app.motive.vehicle_utilization_production_ingestion import PRODUCTION_TIME_ZONE

DEFAULT_HISTORY_DAYS = 30
MAX_HISTORY_DAYS = 90


class MotiveVehicleUtilizationKpiHistoryError(RuntimeError):
    """Sanitized read-contract validation failure."""


def latest_completed_day() -> date:
    """Return the latest fully completed America/Chicago calendar day."""
    return datetime.now(ZoneInfo(PRODUCTION_TIME_ZONE)).date() - timedelta(days=1)


def vehicle_utilization_kpi_history(
    session: Session,
    organization_id: str,
    *,
    days: int = DEFAULT_HISTORY_DAYS,
    end_date: date | None = None,
) -> dict[str, object]:
    """Read a bounded calendar-day history horizon from aggregate snapshots only."""
    if not isinstance(organization_id, str) or not organization_id.strip():
        raise MotiveVehicleUtilizationKpiHistoryError(
            "Utilization KPI history requires a tenant organization context."
        )
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= MAX_HISTORY_DAYS:
        raise MotiveVehicleUtilizationKpiHistoryError(
            f"Utilization KPI history days must be between 1 and {MAX_HISTORY_DAYS}."
        )

    resolved_end = end_date or latest_completed_day()
    if not isinstance(resolved_end, date):
        raise MotiveVehicleUtilizationKpiHistoryError(
            "Utilization KPI history requires a valid completed end date."
        )
    resolved_start = resolved_end - timedelta(days=days - 1)

    rows = (
        session.query(MotiveVehicleUtilizationKpiSnapshot)
        .filter(
            MotiveVehicleUtilizationKpiSnapshot.organization_id == organization_id,
            MotiveVehicleUtilizationKpiSnapshot.kpi == KPI_NAME,
            MotiveVehicleUtilizationKpiSnapshot.window_end >= resolved_start,
            MotiveVehicleUtilizationKpiSnapshot.window_end <= resolved_end,
        )
        .order_by(
            MotiveVehicleUtilizationKpiSnapshot.window_end.asc(),
            MotiveVehicleUtilizationKpiSnapshot.window_start.asc(),
        )
        .all()
    )

    points = [
        {
            "window_start": row.window_start.isoformat(),
            "window_end": row.window_end.isoformat(),
            "status": row.status,
            "value_percent": _number(row.value_percent),
            "utilization_metric_coverage_percent": _number(row.utilization_metric_coverage_percent),
            "metric_valid_vehicle_days": row.metric_valid_vehicle_days,
            "expected_requested_vehicle_days": row.expected_requested_vehicle_days,
            "fleet_representative": bool(row.fleet_representative),
        }
        for row in rows
    ]

    return {
        "kpi": KPI_NAME,
        "requested_history_days": days,
        "history_start": resolved_start.isoformat(),
        "history_end": resolved_end.isoformat(),
        "request_timezone": PRODUCTION_TIME_ZONE,
        "snapshot_count": len(points),
        "points": points,
        "secrets_exposed": False,
    }


def _number(value: Decimal | int | float | None) -> float | None:
    if value is None:
        return None
    return float(value)
