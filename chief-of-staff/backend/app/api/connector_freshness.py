"""Passive tenant-scoped freshness and recovery evidence for scheduled connectors.

This API never contacts a provider. It interprets durable Polaris scheduler,
sync-history, and checkpoint state against already-governed scheduling contracts.
Manual connectors are explicitly identified as operator-managed and receive no
invented stale-data SLA.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.motive import MotiveSyncCheckpoint, MotiveSyncHistory
from app.models.torqueai import TorqueAIDispatchSyncRun
from app.motive.vehicle_utilization_production_ingestion import (
    PRODUCTION_TIME_ZONE,
    RUN_MODE as MOTIVE_UTILIZATION_RUN_MODE,
    production_ingestion_enabled,
    production_scheduler_enabled,
)
from app.motive.vehicle_utilization_scheduler import (
    SCHEDULE_END_HOUR,
    SCHEDULE_START_HOUR,
    SCHEDULER_DISPATCH_RESOURCE,
)
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/api/v1/system/connector-freshness", tags=["system-connector-freshness"])

TORQUEAI_EXPECTED_CADENCE_MINUTES = 60
# Operational Polaris policy, not a TorqueAI SLA: two missed hourly opportunities
# are enough to mark scheduled ingestion stale and require operator attention.
TORQUEAI_STALE_AFTER_MINUTES = 120
MOTIVE_UTILIZATION_RESOURCE = "vehicle_utilization"


def _db() -> Session:
    with SessionLocal() as session:
        yield session


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@router.get("")
def connector_freshness(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Return passive freshness and recovery evidence for the active tenant."""
    now = _now_utc()
    return {
        "checked_at": now.isoformat(),
        "manual_connectors": {
            "quickbooks": {"mode": "manual", "stale_threshold_minutes": None},
            "outlook": {"mode": "manual", "stale_threshold_minutes": None},
            "motive_vehicles": {"mode": "manual", "stale_threshold_minutes": None},
            "motive_users": {"mode": "manual", "stale_threshold_minutes": None},
        },
        "torqueai": _torqueai_freshness(session, principal.organization_id, now),
        "motive_vehicle_utilization": _motive_vehicle_utilization_freshness(
            session,
            principal.organization_id,
            now,
        ),
        "provider_called": False,
        "tenant_scope_validated": True,
        "secrets_exposed": False,
    }


def _torqueai_freshness(session: Session, organization_id: str, now: datetime) -> dict[str, Any]:
    scheduled = session.query(TorqueAIDispatchSyncRun).filter(
        TorqueAIDispatchSyncRun.organization_id == organization_id,
        TorqueAIDispatchSyncRun.trigger_mode == "scheduled",
    )
    latest = scheduled.order_by(
        TorqueAIDispatchSyncRun.started_at.desc(),
        TorqueAIDispatchSyncRun.id.desc(),
    ).first()
    last_success = scheduled.filter(
        TorqueAIDispatchSyncRun.status == "success",
        TorqueAIDispatchSyncRun.completed_at.is_not(None),
    ).order_by(
        TorqueAIDispatchSyncRun.completed_at.desc(),
        TorqueAIDispatchSyncRun.id.desc(),
    ).first()

    last_success_at = _as_utc(last_success.completed_at) if last_success is not None else None
    age_minutes = _minutes_since(now, last_success_at)
    latest_started = _as_utc(latest.started_at) if latest is not None else None
    latest_age = _minutes_since(now, latest_started)

    if latest is None:
        freshness_status = "not_started"
        recovery = "Verify the hourly scheduled workflow and trigger configuration before relying on automatic TorqueAI freshness."
    elif latest.status == "claimed":
        if latest_age is not None and latest_age > TORQUEAI_STALE_AFTER_MINUTES:
            freshness_status = "stale"
            recovery = "The scheduled claim is older than two hourly opportunities. Check the workflow, Render availability, and sanitized backend logs before any manual intervention."
        else:
            freshness_status = "running"
            recovery = "Allow the claimed scheduled slot to complete; do not replay the same trigger slot."
    elif latest.status != "success":
        freshness_status = "failed"
        recovery = "Inspect the sanitized error code. The next hourly slot is the normal recovery opportunity; do not retry the same scheduled slot."
    elif age_minutes is None:
        freshness_status = "not_started"
        recovery = "No successful scheduled TorqueAI ingestion is recorded. Verify the scheduler and trigger configuration."
    elif age_minutes > TORQUEAI_STALE_AFTER_MINUTES:
        freshness_status = "stale"
        recovery = "No successful scheduled ingestion has completed within two hourly opportunities. Check the GitHub workflow, Render availability, and trigger configuration."
    else:
        freshness_status = "current"
        recovery = "No action required."

    return {
        "mode": "scheduled_hourly",
        "freshness_status": freshness_status,
        "expected_cadence_minutes": TORQUEAI_EXPECTED_CADENCE_MINUTES,
        "stale_after_minutes": TORQUEAI_STALE_AFTER_MINUTES,
        "freshness_age_minutes": age_minutes,
        "last_successful_at": last_success_at.isoformat() if last_success_at else None,
        "last_successful_trigger_slot": last_success.trigger_slot if last_success is not None else None,
        "latest_run_status": latest.status if latest is not None else None,
        "latest_run_trigger_slot": latest.trigger_slot if latest is not None else None,
        "latest_run_started_at": latest_started.isoformat() if latest_started else None,
        "latest_run_error_code": latest.error_code if latest is not None else None,
        "recovery": recovery,
        "policy_basis": "Polaris hourly scheduler contract; stale after two missed hourly opportunities. This is not a provider SLA.",
    }


def _motive_vehicle_utilization_freshness(
    session: Session,
    organization_id: str,
    now: datetime,
) -> dict[str, Any]:
    local_now = now.astimezone(ZoneInfo(PRODUCTION_TIME_ZONE))
    expected_completed_through = local_now.date() - timedelta(days=1)

    latest = (
        session.query(MotiveSyncHistory)
        .filter(
            MotiveSyncHistory.organization_id == organization_id,
            MotiveSyncHistory.provider == "motive",
            MotiveSyncHistory.provider_resource == MOTIVE_UTILIZATION_RESOURCE,
            MotiveSyncHistory.mode == MOTIVE_UTILIZATION_RUN_MODE,
        )
        .order_by(MotiveSyncHistory.started_at.desc(), MotiveSyncHistory.id.desc())
        .first()
    )
    checkpoint = (
        session.query(MotiveSyncCheckpoint)
        .filter(
            MotiveSyncCheckpoint.organization_id == organization_id,
            MotiveSyncCheckpoint.provider_resource == MOTIVE_UTILIZATION_RESOURCE,
        )
        .one_or_none()
    )
    scheduler_claim = (
        session.query(MotiveSyncCheckpoint)
        .filter(
            MotiveSyncCheckpoint.organization_id == organization_id,
            MotiveSyncCheckpoint.provider_resource == SCHEDULER_DISPATCH_RESOURCE,
        )
        .one_or_none()
    )

    checkpoint_position = checkpoint.last_successful_position if checkpoint is not None and isinstance(checkpoint.last_successful_position, dict) else {}
    completed_through = _safe_date(checkpoint_position.get("completed_through"))
    claim_position = scheduler_claim.last_successful_position if scheduler_claim is not None and isinstance(scheduler_claim.last_successful_position, dict) else {}
    claimed_local_date = _safe_date(claim_position.get("claimed_local_date"))

    scheduler_enabled = production_scheduler_enabled()
    ingestion_enabled = production_ingestion_enabled()
    latest_started = _as_utc(latest.started_at) if latest is not None else None
    latest_local_date = latest_started.astimezone(ZoneInfo(PRODUCTION_TIME_ZONE)).date() if latest_started else None
    latest_failed_today = bool(
        latest is not None
        and latest.status != "success"
        and latest_local_date == local_now.date()
    )

    lag_days = None
    if completed_through is not None:
        lag_days = max(0, (expected_completed_through - completed_through).days)

    if not scheduler_enabled or not ingestion_enabled:
        freshness_status = "disabled"
        recovery = "Scheduled Motive vehicle-utilization ingestion is disabled by configuration. Enable it only through the governed production configuration if this is not intentional."
    elif latest_failed_today:
        freshness_status = "failed"
        recovery = "Inspect the sanitized production error. The same local-day dispatch claim must not be replayed automatically; the next local-day schedule is the normal recovery opportunity."
    elif completed_through is not None and completed_through >= expected_completed_through:
        freshness_status = "current"
        recovery = "No action required."
    elif local_now.hour < SCHEDULE_START_HOUR:
        freshness_status = "waiting"
        recovery = "No action required yet; today's governed scheduler acceptance window has not started."
    elif local_now.hour <= SCHEDULE_END_HOUR:
        freshness_status = "checking"
        if claimed_local_date == local_now.date():
            recovery = "Today's scheduler dispatch has been claimed. Allow the production run to finish; do not create a duplicate same-day run."
        else:
            recovery = "The daily acceptance window is open. Allow the scheduled workflow to claim and execute before intervening."
    else:
        freshness_status = "stale"
        recovery = "The daily acceptance window has ended without a checkpoint through the latest completed Chicago day. Check the GitHub workflow, scheduler/ingestion configuration, and sanitized latest error before intervention."

    return {
        "mode": "scheduled_daily",
        "freshness_status": freshness_status,
        "request_timezone": PRODUCTION_TIME_ZONE,
        "schedule_window_local": f"{SCHEDULE_START_HOUR:02d}:00-{SCHEDULE_END_HOUR:02d}:59",
        "scheduler_enabled": scheduler_enabled,
        "production_ingestion_enabled": ingestion_enabled,
        "expected_completed_through": expected_completed_through.isoformat(),
        "completed_through": completed_through.isoformat() if completed_through else None,
        "freshness_lag_days": lag_days,
        "last_successful_at": _iso(checkpoint.last_successful_sync_at) if checkpoint is not None else None,
        "latest_attempt_status": latest.status if latest is not None else None,
        "latest_attempt_started_at": latest_started.isoformat() if latest_started else None,
        "latest_attempt_completed_at": _iso(latest.completed_at) if latest is not None else None,
        "latest_attempt_error_code": latest.error_code if latest is not None else None,
        "scheduler_claimed_local_date": claimed_local_date.isoformat() if claimed_local_date else None,
        "recovery": recovery,
        "policy_basis": "Daily Motive production contract: latest seven completed America/Chicago days, with a 06:00-13:59 local acceptance window. This is not a provider SLA.",
    }


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    resolved = _as_utc(value)
    return resolved.isoformat() if resolved else None


def _minutes_since(now: datetime, value: datetime | None) -> int | None:
    if value is None:
        return None
    delta = _as_utc(now) - _as_utc(value)
    return max(0, int(delta.total_seconds() // 60))


def _safe_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
