"""Post-success production persistence for the Motive utilization KPI snapshot.

This module performs only local database work. It makes no Motive provider calls
and is intentionally invoked only after the primary production ingestion and
checkpoint transaction has committed successfully.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date

from sqlalchemy.orm import Session

from app.motive.vehicle_utilization_kpi_snapshot import (
    calculate_vehicle_utilization_kpi_snapshot,
    load_vehicle_utilization_snapshot_rows,
    upsert_vehicle_utilization_kpi_snapshot,
)


class MotiveVehicleUtilizationKpiSnapshotProductionError(RuntimeError):
    """Sanitized failure for the secondary production snapshot transaction."""


def persist_vehicle_utilization_kpi_snapshot_after_success(
    *,
    session_factory: Callable[[], Session],
    organization_id: str,
    organization_slug: str,
    selected_provider_vehicle_ids: Sequence[str],
    window_end: date,
    source_history_id: int,
) -> None:
    """Persist one canonical snapshot in a separate short local transaction."""
    snapshot_session = session_factory()
    try:
        rows = load_vehicle_utilization_snapshot_rows(
            snapshot_session,
            organization_id=organization_id,
            selected_provider_vehicle_ids=selected_provider_vehicle_ids,
            window_end=window_end,
        )
        computation = calculate_vehicle_utilization_kpi_snapshot(
            organization_id=organization_id,
            organization_slug=organization_slug,
            selected_provider_vehicle_ids=selected_provider_vehicle_ids,
            window_end=window_end,
            rows=rows,
        )
        upsert_vehicle_utilization_kpi_snapshot(
            snapshot_session,
            computation=computation,
            source_history_id=source_history_id,
        )
        snapshot_session.commit()
    except Exception as exc:
        snapshot_session.rollback()
        raise MotiveVehicleUtilizationKpiSnapshotProductionError(
            "Motive vehicle-utilization KPI snapshot persistence failed."
        ) from exc
    finally:
        snapshot_session.close()
