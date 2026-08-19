"""Controlled seven-day live-staging validation for Motive utilization reconciliation.

This module is intentionally narrower than the general recent-window runner:
exactly seven completed daily windows, at most 100 eligible tenant vehicles,
one batch/page per day, at most seven provider calls total, no retries, no
checkpoint advancement, no sync-history writes, and no scheduler.

It is disabled by default behind a dedicated feature flag and makes no Motive
provider call merely by existing in the codebase.
"""

from __future__ import annotations

from dataclasses import asdict
import logging
import os
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.motive.vehicle_utilization_recent_reconciliation import (
    VehicleUtilizationRecentReconciliationResult,
    _select_tenant_vehicles,
    recent_reconciliation_enabled,
    run_recent_vehicle_utilization_reconciliation,
)

logger = logging.getLogger(__name__)

RESOURCE = "vehicle_utilization_recent_reconciliation_seven_day_live_validation"
VALIDATION_MODE = "controlled_manual_seven_day_recent_reconciliation_live_validation"

SEVEN_DAY_RECONCILIATION_VALIDATION_ENABLED_ENV_VAR = (
    "MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_SEVEN_DAY_VALIDATION_ENABLED"
)
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}

SEVEN_DAY_RECONCILIATION_VALIDATION_HORIZON_DAYS = 7
SEVEN_DAY_RECONCILIATION_VALIDATION_MAX_SELECTED_VEHICLES = 100
SEVEN_DAY_RECONCILIATION_VALIDATION_MAX_WINDOWS = 7
SEVEN_DAY_RECONCILIATION_VALIDATION_MAX_BATCHES_PER_DAY = 1
SEVEN_DAY_RECONCILIATION_VALIDATION_MAX_PAGES_PER_DAY = 1
SEVEN_DAY_RECONCILIATION_VALIDATION_MAX_PROVIDER_CALLS = 7


class MotiveVehicleUtilizationSevenDayReconciliationValidationError(ValueError):
    """Safe fail-closed pre-flight/invariant error with sanitized context."""

    def __init__(self, code: str, message: str, **sanitized_context: Any) -> None:
        super().__init__(message)
        self.code = code
        self.sanitized_context = sanitized_context


def seven_day_reconciliation_validation_enabled() -> bool:
    value = os.getenv(SEVEN_DAY_RECONCILIATION_VALIDATION_ENABLED_ENV_VAR)
    if value is None:
        return False
    return value.strip().lower() in _TRUTHY_ENV_VALUES


def _sanitized_response(result: VehicleUtilizationRecentReconciliationResult) -> dict[str, Any]:
    payload = asdict(result)
    return {
        "status": payload["status"],
        "resource": RESOURCE,
        "validation_mode": VALIDATION_MODE,
        "horizon_days": payload["horizon_days"],
        "windows_attempted": payload["windows_attempted"],
        "windows_completed": payload["windows_completed"],
        "windows_failed": payload["windows_failed"],
        "selected_vehicle_count": payload["selected_vehicle_count"],
        "vehicle_batches_attempted": payload["vehicle_batches_attempted"],
        "vehicle_batches_completed": payload["vehicle_batches_completed"],
        "vehicle_batches_failed": payload["vehicle_batches_failed"],
        "provider_calls_attempted": payload["provider_calls_attempted"],
        "provider_calls_completed": payload["provider_calls_completed"],
        "rollups_returned": payload["rollups_returned"],
        "missing_requested_vehicle_count": payload["missing_requested_vehicle_count"],
        "records_inserted": payload["records_inserted"],
        "records_unchanged": payload["records_unchanged"],
        "records_updated": payload["records_updated"],
        "reconciled_fields_count": payload["reconciled_fields_count"],
        "checkpoint_advanced": payload["checkpoint_advanced"],
        "sync_history_written": payload["sync_history_written"],
        "scheduled_ingestion_enabled": payload["scheduled_ingestion_enabled"],
        "secrets_exposed": payload["secrets_exposed"],
        "failed_units": [
            {
                "window_start": unit["window_start"],
                "window_end": unit["window_end"],
                "batch_ordinal": unit["batch_ordinal"],
                "error_code": unit["error_code"],
            }
            for unit in payload["failed_units"]
        ],
    }


def run_seven_day_vehicle_utilization_reconciliation_live_validation(
    session: Session,
    *,
    organization_id: str,
    organization_slug: str,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Run exactly seven trailing completed daily reconciliation windows."""
    if not recent_reconciliation_enabled():
        raise MotiveVehicleUtilizationSevenDayReconciliationValidationError(
            "recent_reconciliation_disabled",
            "Seven-day Motive utilization reconciliation validation requires the runner feature gate.",
        )
    if not seven_day_reconciliation_validation_enabled():
        raise MotiveVehicleUtilizationSevenDayReconciliationValidationError(
            "seven_day_reconciliation_validation_disabled",
            "Seven-day Motive utilization reconciliation validation is disabled.",
        )

    eligible_vehicle_count = len(_select_tenant_vehicles(session, organization_id))
    if eligible_vehicle_count > SEVEN_DAY_RECONCILIATION_VALIDATION_MAX_SELECTED_VEHICLES:
        raise MotiveVehicleUtilizationSevenDayReconciliationValidationError(
            "seven_day_validation_vehicle_limit_exceeded",
            "Seven-day Motive utilization reconciliation validation requires no more than 100 eligible tenant vehicles.",
            eligible_vehicle_count=eligible_vehicle_count,
            max_selected_vehicles=SEVEN_DAY_RECONCILIATION_VALIDATION_MAX_SELECTED_VEHICLES,
            provider_calls_attempted=0,
            provider_calls_completed=0,
        )

    theoretical_max_calls = (
        SEVEN_DAY_RECONCILIATION_VALIDATION_HORIZON_DAYS
        * (1 if eligible_vehicle_count else 0)
        * SEVEN_DAY_RECONCILIATION_VALIDATION_MAX_PAGES_PER_DAY
    )
    if theoretical_max_calls > SEVEN_DAY_RECONCILIATION_VALIDATION_MAX_PROVIDER_CALLS:
        raise MotiveVehicleUtilizationSevenDayReconciliationValidationError(
            "seven_day_provider_call_budget_preflight_failed",
            "Seven-day Motive utilization reconciliation validation call budget exceeds the route safety bound.",
            theoretical_max_provider_calls=theoretical_max_calls,
            max_provider_calls=SEVEN_DAY_RECONCILIATION_VALIDATION_MAX_PROVIDER_CALLS,
            provider_calls_attempted=0,
            provider_calls_completed=0,
        )

    result = run_recent_vehicle_utilization_reconciliation(
        session,
        organization_id=organization_id,
        organization_slug=organization_slug,
        horizon_days=SEVEN_DAY_RECONCILIATION_VALIDATION_HORIZON_DAYS,
        http_client=http_client,
    )

    if result.provider_calls_attempted > SEVEN_DAY_RECONCILIATION_VALIDATION_MAX_PROVIDER_CALLS:
        raise MotiveVehicleUtilizationSevenDayReconciliationValidationError(
            "seven_day_provider_call_budget_invariant_violated",
            "Seven-day Motive utilization reconciliation validation exceeded its seven-call invariant.",
            provider_calls_attempted=result.provider_calls_attempted,
            provider_calls_completed=result.provider_calls_completed,
        )

    logger.info(
        "MOTIVE VEHICLE UTILIZATION SEVEN DAY RECONCILIATION LIVE VALIDATION",
        extra={
            "motive_operation": "vehicle_utilization_seven_day_reconciliation_live_validation",
            "organization_id": organization_id,
            "selected_vehicle_count": result.selected_vehicle_count,
            "provider_calls_attempted": result.provider_calls_attempted,
            "provider_calls_completed": result.provider_calls_completed,
            "records_inserted": result.records_inserted,
            "records_unchanged": result.records_unchanged,
            "records_updated": result.records_updated,
            "status": result.status,
        },
    )
    return _sanitized_response(result)
