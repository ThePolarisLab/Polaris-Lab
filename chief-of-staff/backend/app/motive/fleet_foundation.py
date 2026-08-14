"""Read-only Motive Fleet V1 foundation contract.

This module summarizes what Polaris can safely use today from existing Motive
production tables. It does not call Motive, persist records, advance
checkpoints, or create executive attention.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.motive import MOTIVE_USERS_ENDPOINT, MOTIVE_VEHICLES_ENDPOINT
from app.models.motive import MotiveDriverRecord, MotiveSyncCheckpoint, MotiveSyncHistory, MotiveVehicleRecord


CONFIRMED_CONTRACTS = (
    {
        "name": "company_api_key_authentication",
        "classification": "CONFIRMED",
        "evidence": "backend X-API-Key provider boundary with sanitized status; OAuth production path disabled",
    },
    {
        "name": "vehicle_identity_persistence",
        "classification": "CONFIRMED",
        "evidence": "motive_vehicles unique organization_id + provider_vehicle_id",
    },
    {
        "name": "vehicle_manual_ingestion",
        "classification": "CONFIRMED",
        "evidence": f"manual {MOTIVE_VEHICLES_ENDPOINT} sync with one-based page_no and per_page=100",
    },
    {
        "name": "company_user_manual_ingestion",
        "classification": "CONFIRMED",
        "evidence": f"manual {MOTIVE_USERS_ENDPOINT} sync with one-based page_no and per_page=100",
    },
)

DERIVED_METRICS = (
    {
        "name": "total_known_vehicles",
        "classification": "DERIVED",
        "source": "count of organization-scoped motive_vehicles rows",
        "safe_for_dashboard": True,
    },
    {
        "name": "total_known_company_users",
        "classification": "DERIVED",
        "source": "count of organization-scoped /v1/users rows stored in motive_drivers",
        "safe_for_dashboard": True,
    },
)

DEFERRED_SEMANTICS = (
    "vehicle_active_inactive_business_state",
    "driver_classification",
    "vehicle_driver_association",
    "vehicle_utilization_reporting_period",
    "vehicle_utilization_cardinality",
    "driver_utilization",
    "ifta_summary",
    "fleet_operational_exceptions",
    "fleet_daily_brief_attention",
    "broad_or_automatic_motive_sync",
)


def motive_fleet_foundation_status(db: Session, organization_id: str) -> dict[str, Any]:
    vehicle_count = db.query(MotiveVehicleRecord).filter(MotiveVehicleRecord.organization_id == organization_id).count()
    user_count = (
        db.query(MotiveDriverRecord)
        .filter(MotiveDriverRecord.organization_id == organization_id, MotiveDriverRecord.source_endpoint == MOTIVE_USERS_ENDPOINT)
        .count()
    )
    latest_vehicle = _latest_history(db, organization_id, mode="vehicle_sync")
    latest_user = _latest_history(db, organization_id, mode="user_sync")
    latest_verification = _latest_history(db, organization_id, mode="verification")
    vehicle_checkpoint = _checkpoint(db, organization_id, "vehicles")
    user_checkpoint = _checkpoint(db, organization_id, "users")
    health = _feed_health(latest_vehicle=latest_vehicle, latest_user=latest_user, latest_verification=latest_verification)

    return {
        "provider": "motive",
        "resource": "fleet_operations_v1_foundation",
        "status": health["status"],
        "message": health["message"],
        "confirmed_contracts": list(CONFIRMED_CONTRACTS),
        "derived_metrics": [
            {**DERIVED_METRICS[0], "value": vehicle_count},
            {**DERIVED_METRICS[1], "value": user_count},
        ],
        "deferred_semantics": list(DEFERRED_SEMANTICS),
        "persistence": {
            "vehicles": _resource_state(latest_vehicle, vehicle_checkpoint, records_stored=vehicle_count),
            "company_users": _resource_state(latest_user, user_checkpoint, records_stored=user_count),
            "vehicle_utilization": {
                "enabled": False,
                "classification": "DEFERRED",
                "reason": "Production schema is partially observed, but reporting-period/cardinality semantics are not certified.",
            },
        },
        "checkpoint_safety": {
            "vehicles": _checkpoint_safety(vehicle_checkpoint),
            "company_users": _checkpoint_safety(user_checkpoint),
            "utilization": "not_enabled",
        },
        "dashboard_daily_brief_boundary": {
            "normal_state_creates_attention": False,
            "fleet_attention_enabled": False,
            "reason": "Fleet exceptions are deferred until provider semantics are reliable.",
        },
        "security": {
            "organization_scoped": True,
            "provider_ids_exposed": False,
            "raw_provider_payload_exposed": False,
            "secrets_exposed": False,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _latest_history(db: Session, organization_id: str, *, mode: str) -> MotiveSyncHistory | None:
    return (
        db.query(MotiveSyncHistory)
        .filter(MotiveSyncHistory.organization_id == organization_id, MotiveSyncHistory.provider == "motive", MotiveSyncHistory.mode == mode)
        .order_by(MotiveSyncHistory.completed_at.desc().nullslast(), MotiveSyncHistory.started_at.desc(), MotiveSyncHistory.id.desc())
        .first()
    )


def _checkpoint(db: Session, organization_id: str, resource: str) -> MotiveSyncCheckpoint | None:
    return (
        db.query(MotiveSyncCheckpoint)
        .filter(MotiveSyncCheckpoint.organization_id == organization_id, MotiveSyncCheckpoint.provider_resource == resource)
        .one_or_none()
    )


def _feed_health(
    *,
    latest_vehicle: MotiveSyncHistory | None,
    latest_user: MotiveSyncHistory | None,
    latest_verification: MotiveSyncHistory | None,
) -> dict[str, str]:
    latest = _latest_completed(latest_vehicle, latest_user, latest_verification)
    if latest is None:
        return {"status": "not_started", "message": "Motive Fleet V1 persistence gate has not run vehicle or user ingestion yet."}
    if latest.status == "success":
        return {"status": "ready", "message": "Motive Fleet V1 foundation has successful persisted source data."}
    if latest.status in {"authorization_required", "rate_limited"}:
        return {"status": latest.status, "message": f"Motive latest source run ended with {latest.status}."}
    return {"status": "degraded", "message": f"Motive latest source run ended with {latest.status}."}


def _latest_completed(*rows: MotiveSyncHistory | None) -> MotiveSyncHistory | None:
    candidates = [row for row in rows if row is not None]
    return max(candidates, key=lambda row: (row.completed_at or row.started_at, row.id or 0)) if candidates else None


def _resource_state(history: MotiveSyncHistory | None, checkpoint: MotiveSyncCheckpoint | None, *, records_stored: int) -> dict[str, Any]:
    return {
        "enabled": True,
        "records_stored": records_stored,
        "latest_status": history.status if history else "not_started",
        "latest_completed_at": history.completed_at.isoformat() if history and history.completed_at else None,
        "records_read": history.records_read if history else 0,
        "records_written": history.records_written if history else 0,
        "checkpoint_status": checkpoint.checkpoint_status if checkpoint else "not_started",
        "checkpoint_advances_after_successful_persistence": True,
    }


def _checkpoint_safety(checkpoint: MotiveSyncCheckpoint | None) -> str:
    if checkpoint is None:
        return "not_started"
    if checkpoint.checkpoint_status == "success":
        return "last_successful_position_recorded"
    return checkpoint.checkpoint_status
