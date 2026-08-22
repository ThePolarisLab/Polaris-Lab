"""Read-only operational status for Motive vehicle-utilization production ingestion."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.motive import MotiveSyncCheckpoint, MotiveSyncHistory
from app.motive.vehicle_utilization_production_ingestion import (
    RESOURCE,
    RUN_MODE,
    production_ingestion_enabled,
    production_scheduler_enabled,
)
from app.motive.vehicle_utilization_scheduler import (
    SCHEDULER_DISPATCH_RESOURCE,
    controlled_validation_window_enabled,
)

_PRODUCTION_COUNT_KEYS = (
    "horizon_days",
    "request_timezone",
    "unit_request_mode",
    "fuel_unit",
    "selected_vehicle_count",
    "windows_attempted",
    "windows_completed",
    "windows_failed",
    "provider_calls_attempted",
    "provider_calls_completed",
    "rollups_returned",
    "missing_requested_vehicle_count",
    "records_inserted",
    "records_unchanged",
    "records_updated",
    "reconciled_fields_count",
    "checkpoint_advanced",
)


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _latest_production_history(session: Session, organization_id: str) -> MotiveSyncHistory | None:
    return (
        session.query(MotiveSyncHistory)
        .filter(
            MotiveSyncHistory.organization_id == organization_id,
            MotiveSyncHistory.provider == "motive",
            MotiveSyncHistory.provider_resource == RESOURCE,
            MotiveSyncHistory.mode == RUN_MODE,
        )
        .order_by(MotiveSyncHistory.started_at.desc(), MotiveSyncHistory.id.desc())
        .first()
    )


def _checkpoint(session: Session, organization_id: str, resource: str) -> MotiveSyncCheckpoint | None:
    return (
        session.query(MotiveSyncCheckpoint)
        .filter(
            MotiveSyncCheckpoint.organization_id == organization_id,
            MotiveSyncCheckpoint.provider_resource == resource,
        )
        .one_or_none()
    )


def _production_payload(history: MotiveSyncHistory | None) -> dict[str, Any]:
    if history is None:
        return {
            "status": "not_started",
            "started_at": None,
            "completed_at": None,
            "records_read": 0,
            "records_written": 0,
            "error_code": None,
            "counts": {},
        }
    counts = _mapping(history.resource_counts)
    return {
        "status": history.status,
        "started_at": _iso(history.started_at),
        "completed_at": _iso(history.completed_at),
        "records_read": history.records_read,
        "records_written": history.records_written,
        "error_code": history.error_code,
        "counts": {key: counts.get(key) for key in _PRODUCTION_COUNT_KEYS if key in counts},
    }


def _production_checkpoint_payload(row: MotiveSyncCheckpoint | None) -> dict[str, Any]:
    if row is None:
        return {
            "status": "not_started",
            "last_successful_sync_at": None,
            "completed_through": None,
            "request_timezone": None,
            "unit_request_mode": None,
            "fuel_unit": None,
        }
    position = _mapping(row.last_successful_position)
    return {
        "status": row.checkpoint_status,
        "last_successful_sync_at": _iso(row.last_successful_sync_at),
        "completed_through": position.get("completed_through"),
        "request_timezone": position.get("request_timezone"),
        "unit_request_mode": position.get("unit_request_mode"),
        "fuel_unit": position.get("fuel_unit"),
    }


def _scheduler_payload(row: MotiveSyncCheckpoint | None) -> dict[str, Any]:
    if row is None:
        return {
            "claim_status": "not_claimed",
            "claimed_local_date": None,
            "claim_recorded_at": None,
            "request_timezone": None,
            "scheduler_mode": None,
        }
    position = _mapping(row.last_successful_position)
    return {
        "claim_status": row.checkpoint_status,
        "claimed_local_date": position.get("claimed_local_date"),
        "claim_recorded_at": _iso(row.last_successful_sync_at),
        "request_timezone": position.get("request_timezone"),
        "scheduler_mode": position.get("scheduler_mode"),
    }


def _operational_status(
    history: MotiveSyncHistory | None,
    checkpoint: MotiveSyncCheckpoint | None,
) -> str:
    if history is None and checkpoint is None:
        return "not_started"
    if history is None or checkpoint is None:
        return "degraded"
    if history.status != "success" or checkpoint.checkpoint_status != "success":
        return "degraded"

    checkpoint_position = _mapping(checkpoint.last_successful_position)
    history_checkpoint_after = _mapping(history.checkpoint_after)
    persisted_completed_through = checkpoint_position.get("completed_through")
    history_completed_through = history_checkpoint_after.get("completed_through")
    if history_completed_through is not None and persisted_completed_through != history_completed_through:
        return "degraded"
    return "healthy"


def vehicle_utilization_operational_status(session: Session, organization_id: str) -> dict[str, Any]:
    """Build a sanitized tenant-scoped status snapshot with zero writes/provider calls."""
    history = _latest_production_history(session, organization_id)
    production_checkpoint = _checkpoint(session, organization_id, RESOURCE)
    scheduler_checkpoint = _checkpoint(session, organization_id, SCHEDULER_DISPATCH_RESOURCE)

    return {
        "operational_status": _operational_status(history, production_checkpoint),
        "production": _production_payload(history),
        "checkpoint": _production_checkpoint_payload(production_checkpoint),
        "scheduler": _scheduler_payload(scheduler_checkpoint),
        "configuration": {
            "production_ingestion_enabled": production_ingestion_enabled(),
            "production_scheduler_enabled": production_scheduler_enabled(),
            "controlled_validation_window_enabled": controlled_validation_window_enabled(),
        },
        "secrets_exposed": False,
    }
