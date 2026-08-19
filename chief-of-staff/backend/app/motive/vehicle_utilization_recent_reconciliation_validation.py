"""Controlled, feature-flagged ONE-DAY live-staging validation mechanism for
the Motive vehicle-utilization RECENT-WINDOW RECONCILIATION runner
(``app/motive/vehicle_utilization_recent_reconciliation.py``).

Scope of this module:

- exists ONLY to execute a single bounded manual validation of the newly
  merged recent-window reconciliation runner (PR #177), after separate
  operator authorization. It is NOT a general reconciliation endpoint, NOT a
  sync endpoint, NOT a scheduler trigger, and NOT a user-configurable broad
  backfill route;
- hardcodes ``horizon_days=1`` and calls the runner's real, unmodified
  signature (``run_recent_vehicle_utilization_reconciliation``) directly --
  this module never redefines the runner's day-window, batching,
  pagination, or writer logic;
- requires BOTH the runner's own feature gate
  (:func:`app.motive.vehicle_utilization_recent_reconciliation.recent_reconciliation_enabled`)
  AND this module's genuinely separate, additional gate
  (:func:`recent_reconciliation_validation_enabled`) to be enabled before
  doing anything. Both default to disabled and neither implies the other;
- independently enforces, BEFORE any provider HTTP request, that the
  tenant's eligible vehicle count does not exceed
  :data:`RECENT_RECONCILIATION_VALIDATION_MAX_SELECTED_VEHICLES` (100) --
  this is a stricter, route-owned bound than the runner's own much larger
  200-call safety budget, because this validation mechanism is a one-call
  proof, not a fleet-scale execution. A tenant with more than 100 eligible
  vehicles fails closed here, before the runner (and therefore before any
  provider call) is ever invoked;
- re-verifies, AFTER the runner returns, that at most one provider call was
  ever attempted -- an invariant that should already be structurally
  guaranteed by the hardcoded horizon and the pre-flight vehicle-count
  check above, but is independently asserted here as defense in depth;
- never touches ``MotiveSyncCheckpoint`` or ``MotiveSyncHistory``, never
  advances a checkpoint, and is never wired to a scheduler;
- never exposes provider vehicle IDs, DB IDs, VINs, driver PII, raw
  metrics, raw provider payloads, headers, API keys, or bearer tokens in
  its result type, its errors, or its logging.

This module makes NO live Motive provider call on its own -- it only reuses
the runner's own already-certified, already-tested call path. Both required
feature flags default to disabled and neither is enabled anywhere in this
change (no Render change, no environment change). Live execution is a
separate, later, explicitly human-authorized action.
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

_RESOURCE = "vehicle_utilization_recent_reconciliation_live_validation"
_VALIDATION_MODE = "controlled_manual_recent_reconciliation_live_validation"

# ---------------------------------------------------------------------------
# Second, genuinely separate feature gate. Never reused from, never implies,
# and is never implied by
# app.motive.vehicle_utilization_recent_reconciliation.RECENT_RECONCILIATION_ENABLED_ENV_VAR.
# Both must be explicitly, strictly truthy before this module's orchestration
# function may be invoked with real effect. Defaults to disabled. Never
# enabled anywhere in Render or repo configuration by this change.
# ---------------------------------------------------------------------------
RECENT_RECONCILIATION_VALIDATION_ENABLED_ENV_VAR = (
    "MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_VALIDATION_ENABLED"
)
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def recent_reconciliation_validation_enabled() -> bool:
    """Strict boolean parse of the live-validation kill switch.

    Defaults to False (disabled) whenever the environment variable is
    unset, empty, or holds an unrecognized value. Never enabled implicitly.
    This flag must never be enabled in Render by this change; it is
    exercised only via local environment variables or test monkeypatching.
    """
    value = os.getenv(RECENT_RECONCILIATION_VALIDATION_ENABLED_ENV_VAR)
    if value is None:
        return False
    return value.strip().lower() in _TRUTHY_ENV_VALUES


# ---------------------------------------------------------------------------
# Hard live bounds (spec Section 5). This validation route is a one-call
# proof, never a fleet-scale execution.
# ---------------------------------------------------------------------------
RECENT_RECONCILIATION_VALIDATION_HORIZON_DAYS = 1
RECENT_RECONCILIATION_VALIDATION_MAX_SELECTED_VEHICLES = 100
RECENT_RECONCILIATION_VALIDATION_MAX_WINDOWS = 1
RECENT_RECONCILIATION_VALIDATION_MAX_BATCHES = 1
RECENT_RECONCILIATION_VALIDATION_MAX_PAGES = 1
RECENT_RECONCILIATION_VALIDATION_MAX_PROVIDER_CALLS = 1


class MotiveVehicleUtilizationRecentReconciliationValidationError(ValueError):
    """Safe, fail-closed live-validation error, raised only by this module's
    own pre-flight/invariant checks (never by the runner itself).

    Carries only sanitized diagnostic counters (never a vehicle identity,
    provider payload, or raw metric) via ``sanitized_context``.
    """

    def __init__(self, code: str, message: str, **sanitized_context: Any) -> None:
        super().__init__(message)
        self.code = code
        self.sanitized_context = sanitized_context


def _sanitized_validation_response(result: VehicleUtilizationRecentReconciliationResult) -> dict[str, Any]:
    payload = asdict(result)
    return {
        "status": payload["status"],
        "resource": _RESOURCE,
        "validation_mode": _VALIDATION_MODE,
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


# ---------------------------------------------------------------------------
# Full controlled orchestration. Callers (the public route) MUST already
# have: authenticated the caller with CONNECTOR_WRITE, verified the caller's
# explicit confirm=true request body, and loaded the authenticated
# organization.
# ---------------------------------------------------------------------------
def run_recent_vehicle_utilization_reconciliation_live_validation(
    session: Session,
    *,
    organization_id: str,
    organization_slug: str,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Run one bounded, one-day, at-most-one-provider-call live validation
    of the recent-window reconciliation runner.

    Fails closed BEFORE any provider HTTP request if: either required
    feature gate is disabled, or the tenant's eligible vehicle count
    exceeds :data:`RECENT_RECONCILIATION_VALIDATION_MAX_SELECTED_VEHICLES`.

    Otherwise invokes the real, unmodified runner
    (:func:`~app.motive.vehicle_utilization_recent_reconciliation.run_recent_vehicle_utilization_reconciliation`)
    with ``horizon_days`` hardcoded to
    :data:`RECENT_RECONCILIATION_VALIDATION_HORIZON_DAYS` (1) -- never
    caller-supplied -- and independently re-verifies afterward that at most
    one provider call was ever attempted, raising a fail-closed invariant
    error if that structural guarantee is ever violated.

    Never mutates ``MotiveSyncCheckpoint``. Never writes
    ``MotiveSyncHistory``. Returns a sanitized dict that never includes
    provider vehicle IDs, DB IDs, VINs, driver PII, raw metrics, raw
    provider payloads, headers, API keys, or bearer tokens.
    """
    if not recent_reconciliation_enabled():
        raise MotiveVehicleUtilizationRecentReconciliationValidationError(
            "recent_reconciliation_disabled",
            "Motive vehicle utilization recent-window reconciliation live validation requires the "
            "runner's own feature gate to be enabled first.",
        )
    if not recent_reconciliation_validation_enabled():
        raise MotiveVehicleUtilizationRecentReconciliationValidationError(
            "recent_reconciliation_validation_disabled",
            "Motive vehicle utilization recent-window reconciliation live validation is disabled. "
            f"Set {RECENT_RECONCILIATION_VALIDATION_ENABLED_ENV_VAR} to enable it.",
        )

    eligible_vehicle_count = len(_select_tenant_vehicles(session, organization_id))
    if eligible_vehicle_count > RECENT_RECONCILIATION_VALIDATION_MAX_SELECTED_VEHICLES:
        raise MotiveVehicleUtilizationRecentReconciliationValidationError(
            "controlled_validation_vehicle_limit_exceeded",
            "Motive vehicle utilization recent-window reconciliation live validation requires no more "
            f"than {RECENT_RECONCILIATION_VALIDATION_MAX_SELECTED_VEHICLES} eligible tenant vehicles; "
            "this is a bounded one-call proof, not a fleet-scale execution.",
            eligible_vehicle_count=eligible_vehicle_count,
            max_selected_vehicles=RECENT_RECONCILIATION_VALIDATION_MAX_SELECTED_VEHICLES,
            provider_calls_attempted=0,
            provider_calls_completed=0,
        )

    result = run_recent_vehicle_utilization_reconciliation(
        session,
        organization_id=organization_id,
        organization_slug=organization_slug,
        horizon_days=RECENT_RECONCILIATION_VALIDATION_HORIZON_DAYS,
        http_client=http_client,
    )

    if result.provider_calls_attempted > RECENT_RECONCILIATION_VALIDATION_MAX_PROVIDER_CALLS:
        # Should be structurally impossible given the hardcoded one-day
        # horizon and the pre-flight <=100-vehicle (one batch) bound above --
        # this is a defense-in-depth invariant assertion, not a preventable
        # fail-closed check (the call(s) already happened by this point).
        raise MotiveVehicleUtilizationRecentReconciliationValidationError(
            "provider_call_budget_invariant_violated",
            "Motive vehicle utilization recent-window reconciliation live validation observed more "
            "than one provider call in a single run, violating this route's one-call invariant.",
            provider_calls_attempted=result.provider_calls_attempted,
            provider_calls_completed=result.provider_calls_completed,
        )

    logger.info(
        "MOTIVE VEHICLE UTILIZATION RECENT RECONCILIATION LIVE VALIDATION",
        extra={
            "motive_operation": "vehicle_utilization_recent_reconciliation_live_validation",
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
    return _sanitized_validation_response(result)
