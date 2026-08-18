"""Bounded, manually-invoked Motive vehicle-utilization RECENT-WINDOW
RECONCILIATION runner.

Implements the design certified in
``docs/engineering/MOTIVE_UTILIZATION_RECENT_WINDOW_RECONCILIATION_DESIGN.md``
(PR #176). This module is the INTERNAL Python callable described in that
design's Section 15 "next gate" -- it is NOT:

- a scheduler or cron job;
- a public FastAPI route (no ``/sync/vehicle-utilization``, no
  ``/reconcile/vehicle-utilization``, nothing reachable over HTTP);
- a checkpoint implementation (``MotiveSyncCheckpoint`` is never imported,
  read, or written here -- see the design doc Section 10: a forward-moving
  ingestion checkpoint is the wrong primitive for reconciliation and is
  deliberately never wired to it);
- a sync-history writer (``MotiveSyncHistory`` is never imported, read, or
  written here);
- an API-key rotation, migration, or Render/environment change of any kind.

Scope of this module (the orchestration primitive only):

- generates one independent, one-calendar-day ``(start_date == end_date)``
  request window per trailing COMPLETED day in a bounded, configurable
  horizon (default 7, hard maximum 14 -- see
  :data:`DEFAULT_RECENT_RECONCILIATION_DAYS` /
  :data:`MAX_RECENT_RECONCILIATION_DAYS`), using the same non-certified
  Polaris request-window timezone convention every existing Motive
  utilization caller already uses
  (``MOTIVE_VEHICLE_UTILIZATION_REQUEST_WINDOW_TIME_ZONE``,
  ``app/api/motive.py``'s ``_completed_vehicle_utilization_contract_window``)
  and NEVER includes "today";
- selects only tenant-owned, deterministically ordered
  :class:`~app.models.motive.MotiveVehicleRecord` rows for the supplied
  ``organization_id`` (mirroring, not reusing, ``app.api.motive.
  _vehicles_for_utilization_contract``'s ``organization_id`` scope +
  ``MotiveVehicleRecord.id`` ascending ordering -- deliberately WITHOUT that
  helper's controlled-validation-specific 3-vehicle cap, which is unrelated
  to this runner's use case);
- batches selected vehicles into deterministic, stable-order groups of at
  most :data:`MAX_VEHICLES_PER_BATCH` (100, the provider's own documented
  page-size maximum -- NOT the controlled-write route's unrelated 3-vehicle
  cap);
- for each ``(day, batch)`` unit, reuses the existing GENERAL certified
  paginated reader
  (:func:`app.connectors.motive_vehicle_utilization_pagination.read_vehicle_utilization_pages`)
  unmodified, always with
  :attr:`~app.motive.vehicle_utilization_unit_policy.MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT`
  (no ``X-Metric-Units`` header, no unit system forced, no ``X-Time-Zone``
  invented), then reuses the existing merged all-or-nothing writer
  transaction
  (:func:`app.motive.vehicle_utilization_writer.write_vehicle_utilization_transaction`)
  unmodified, calling it EXACTLY ONCE per unit -- this runner owns no new
  persistence logic, no new reconciliation policy, and no new pagination
  code;
- computes a deterministic, runner-owned maximum provider-call budget
  BEFORE any provider HTTP request and fails closed if that budget exceeds
  a runner-owned safety cap (see Section "Call-budget safety" below);
- isolates failures at ``(day, batch)`` granularity: a known, already-typed,
  safe operational failure (:class:`~app.connectors.motive.
  MotiveConnectorError`, :class:`~app.connectors.
  motive_vehicle_utilization_pagination.MotiveVehicleUtilizationPaginationError`,
  or :class:`~app.motive.vehicle_utilization_writer.
  MotiveVehicleUtilizationWriterError`) is recorded as a sanitized failed
  unit and processing continues with the next independent unit -- already
  committed earlier units are never rolled back, and no unit is ever
  automatically retried. A genuinely UNEXPECTED exception (anything not in
  that certified taxonomy) is deliberately NOT caught here: it propagates
  and aborts the whole run rather than being silently treated as "just
  another failed unit" -- this is a deliberate, narrow exception boundary,
  never a blanket ``except Exception: continue``;
- returns a single sanitized, immutable
  :class:`VehicleUtilizationRecentReconciliationResult` that never includes
  provider vehicle IDs, VINs, driver info, raw metrics, raw provider
  payloads, headers, API keys, or bearer tokens -- matching the design doc's
  Section 13 sanitization contract exactly -- and that explicitly reports
  ``checkpoint_advanced = False``, ``sync_history_written = False``, and
  ``scheduled_ingestion_enabled = False`` on every outcome.

This runner is disabled by default behind its OWN, genuinely separate
feature gate (:data:`RECENT_RECONCILIATION_ENABLED_ENV_VAR`), which is never
reused from and never implies
``app.motive.vehicle_utilization_controlled_write.CONTROLLED_WRITE_ENABLED_ENV_VAR``.
The gate defaults to disabled and is checked -- and fails closed -- BEFORE
any vehicle selection, provider HTTP, or database write. Nothing in this PR
enables the gate anywhere in Render; it may only be enabled locally via
environment variable or test monkeypatching.

No live Motive provider call is made anywhere in this module or its tests.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging
import os
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from app.connectors.motive import MotiveConnectorError
from app.connectors.motive_vehicle_utilization_contract import (
    MOTIVE_VEHICLE_UTILIZATION_REQUEST_WINDOW_TIME_ZONE,
)
from app.connectors.motive_vehicle_utilization_pagination import (
    MOTIVE_VEHICLE_UTILIZATION_PAGINATION_CANONICAL_WRITER_PAGE_SIZE,
    MotiveVehicleUtilizationPaginationError,
    read_vehicle_utilization_pages,
)
from app.models.motive import MotiveVehicleRecord
from app.motive.vehicle_utilization_unit_policy import MotiveVehicleUtilizationUnitRequestMode
from app.motive.vehicle_utilization_writer import (
    MotiveVehicleUtilizationWriterError,
    write_vehicle_utilization_transaction,
)

logger = logging.getLogger(__name__)

_RESOURCE = "vehicle_utilization_recent_window_reconciliation"
_RUN_MODE = "bounded_manual_recent_window_reconciliation"

# ---------------------------------------------------------------------------
# Feature gate -- default OFF. Follows the EXACT strict-boolean-parse pattern
# already established by
# app.motive.vehicle_utilization_controlled_write.controlled_write_enabled,
# but this is a genuinely separate, new flag -- never reused, never implied
# by, and never conflated with CONTROLLED_WRITE_ENABLED_ENV_VAR.
# ---------------------------------------------------------------------------
RECENT_RECONCILIATION_ENABLED_ENV_VAR = "MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_ENABLED"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def recent_reconciliation_enabled() -> bool:
    """Strict boolean parse of the recent-window reconciliation kill switch.

    Defaults to False (disabled) whenever the environment variable is unset,
    empty, or holds an unrecognized value. Never enabled implicitly. This
    flag must never be enabled in Render by this change; it is exercised
    only via local environment variables or test monkeypatching.
    """
    value = os.getenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR)
    if value is None:
        return False
    return value.strip().lower() in _TRUTHY_ENV_VALUES


# ---------------------------------------------------------------------------
# Horizon (design doc Section 2 / "recent-day horizon"). Never includes
# "today" -- the horizon always ends at the most recent COMPLETED calendar
# day, exactly matching every existing Motive utilization caller's
# convention (app.api.motive._completed_vehicle_utilization_contract_window).
# ---------------------------------------------------------------------------
DEFAULT_RECENT_RECONCILIATION_DAYS = 7
MAX_RECENT_RECONCILIATION_DAYS = 14

# ---------------------------------------------------------------------------
# Vehicle batching (design doc Section 4). Deliberately the provider's own
# documented per_page maximum -- NOT
# app.connectors.motive_vehicle_utilization_contract.
# MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES (3), which is a
# controlled-validation-specific constant unrelated to this runner.
# ---------------------------------------------------------------------------
MAX_VEHICLES_PER_BATCH = MOTIVE_VEHICLE_UTILIZATION_PAGINATION_CANONICAL_WRITER_PAGE_SIZE  # 100
RECENT_RECONCILIATION_PAGE_SIZE = MOTIVE_VEHICLE_UTILIZATION_PAGINATION_CANONICAL_WRITER_PAGE_SIZE  # 100

# ---------------------------------------------------------------------------
# Call-budget safety (design doc Section 12 / spec Section 16).
#
# max_provider_calls = D x B x P
#   D = number of day-windows in the horizon (<= MAX_RECENT_RECONCILIATION_DAYS)
#   B = number of vehicle batches (<= ceil(selected_vehicle_count / 100))
#   P = RUNNER_MAX_PAGES_PER_UNIT (this runner's OWN safety bound, below --
#       deliberately NOT the general reader's much larger defensive guard,
#       MAX_VEHICLE_UTILIZATION_PAGES = 100).
#
# RUNNER_MAX_PAGES_PER_UNIT = 1
#
# Rationale: every (day, batch) unit requests at most MAX_VEHICLES_PER_BATCH
# (100) provider_vehicle_ids at RECENT_RECONCILIATION_PAGE_SIZE (100, the
# certified canonical per_page). The general reader itself already fails
# closed on any duplicate or unexpected returned vehicle (see
# app.connectors.motive_vehicle_utilization_pagination), so a well-formed
# response for a <=100-vehicle batch can never report a pagination total
# greater than 100 -- with per_page=100, expected_pages =
# ceil(pagination_total / 100) is therefore always exactly 1 for a
# well-formed response. The reader's own MAX_VEHICLE_UTILIZATION_PAGES = 100
# guard exists purely as a last-resort defensive bound against a
# hypothetically malformed provider pagination response looping
# unboundedly; it is not evidence that a bounded reconciliation run should
# routinely authorize up to 100 pages per unit. This runner's own
# call-budget formula therefore uses the smaller, use-case-appropriate P=1.
#
# RUNNER_MAX_AUTHORIZED_PROVIDER_CALLS = 200
#
# Rationale: at the maximum permitted horizon (14 days) and P=1, this
# ceiling authorizes up to 14 vehicle batches per day (up to ~1,400
# vehicles) before failing closed pre-flight -- many times the real
# fleet size (materially smaller than 100 vehicles per the design doc's
# Section 1 audit), while remaining nowhere near "hundreds/thousands of
# calls." At the recommended default horizon (7 days) and current fleet
# size (one batch/day), a full run costs exactly 7 provider calls, matching
# the design doc's Section 12 worked example exactly.
# ---------------------------------------------------------------------------
RUNNER_MAX_PAGES_PER_UNIT = 1
RUNNER_MAX_AUTHORIZED_PROVIDER_CALLS = 200


class MotiveVehicleUtilizationRecentReconciliationError(ValueError):
    """Safe, fail-closed recent-window reconciliation error.

    Raised only for whole-run setup failures (disabled feature gate,
    invalid horizon, computed call budget exceeding the runner safety cap)
    -- never for a single unit's known operational failure, which is
    instead recorded as a sanitized :class:`FailedReconciliationUnit` so the
    run can continue with later independent units. Never includes provider
    vehicle IDs, VINs, driver info, raw metrics, secrets, or raw payload
    contents in ``str(error)``.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class FailedReconciliationUnit:
    """Sanitized per-unit failure detail.

    Deliberately limited to day/window, batch ordinal, and a safe error
    code -- never a vehicle identity, provider payload, or raw metric.
    """

    window_start: str
    window_end: str
    batch_ordinal: int
    error_code: str


@dataclass(frozen=True, slots=True)
class VehicleUtilizationRecentReconciliationResult:
    """Sanitized, immutable result of one bounded recent-window
    reconciliation run.

    Deliberately excludes provider vehicle IDs, VINs, driver info, raw
    metrics, raw provider payloads, headers, API keys, and bearer tokens --
    both here and in :attr:`failed_units`. ``checkpoint_advanced``,
    ``sync_history_written``, and ``scheduled_ingestion_enabled`` are always
    ``False``: this runner never mutates ``MotiveSyncCheckpoint``, never
    writes ``MotiveSyncHistory``, and is never wired to a scheduler.
    """

    status: str
    resource: str
    run_mode: str
    horizon_days: int
    windows_attempted: int
    windows_completed: int
    windows_failed: int
    selected_vehicle_count: int
    vehicle_batches_attempted: int
    vehicle_batches_completed: int
    vehicle_batches_failed: int
    provider_calls_attempted: int
    provider_calls_completed: int
    rollups_returned: int
    missing_requested_vehicle_count: int
    records_inserted: int
    records_unchanged: int
    records_updated: int
    reconciled_fields_count: int
    checkpoint_advanced: bool = False
    sync_history_written: bool = False
    scheduled_ingestion_enabled: bool = False
    secrets_exposed: bool = False
    failed_units: tuple[FailedReconciliationUnit, ...] = ()


# ---------------------------------------------------------------------------
# Day-window generation (design doc Section 3 / spec Section 5).
# ---------------------------------------------------------------------------
def _completed_recent_reconciliation_window() -> date:
    """The most recent COMPLETED calendar day ("yesterday").

    Mirrors ``app.api.motive._completed_vehicle_utilization_contract_window``'s
    exact convention: the same non-certified Polaris request-window
    timezone (``MOTIVE_VEHICLE_UTILIZATION_REQUEST_WINDOW_TIME_ZONE`` --
    "not asserted to equal Motive's company-configured rollup timezone"),
    and "today" is never included because it is still accumulating and not
    a completed day.
    """
    company_today = datetime.now(ZoneInfo(MOTIVE_VEHICLE_UTILIZATION_REQUEST_WINDOW_TIME_ZONE)).date()
    return company_today - timedelta(days=1)


def _generate_day_windows(horizon_days: int, *, end_date: date | None = None) -> list[tuple[date, date]]:
    """Generate one independent ``(start_date == end_date)`` window per
    trailing completed calendar day, oldest -> newest, deterministic.

    ``end_date`` defaults to :func:`_completed_recent_reconciliation_window`
    (real "yesterday"); tests may pass an explicit ``end_date`` for
    deterministic day-window assertions without needing to freeze real time.
    """
    resolved_end_date = end_date if end_date is not None else _completed_recent_reconciliation_window()
    return [
        (resolved_end_date - timedelta(days=offset), resolved_end_date - timedelta(days=offset))
        for offset in range(horizon_days - 1, -1, -1)
    ]


def _validate_horizon_days(horizon_days: int) -> None:
    if isinstance(horizon_days, bool) or not isinstance(horizon_days, int):
        raise MotiveVehicleUtilizationRecentReconciliationError(
            "invalid_horizon_days",
            "Motive vehicle utilization recent-window reconciliation horizon_days must be an exact integer.",
        )
    if horizon_days < 1:
        raise MotiveVehicleUtilizationRecentReconciliationError(
            "horizon_days_not_positive",
            "Motive vehicle utilization recent-window reconciliation horizon_days must be a positive integer.",
        )
    if horizon_days > MAX_RECENT_RECONCILIATION_DAYS:
        raise MotiveVehicleUtilizationRecentReconciliationError(
            "horizon_days_exceeds_maximum",
            f"Motive vehicle utilization recent-window reconciliation horizon_days must not exceed {MAX_RECENT_RECONCILIATION_DAYS}.",
        )


# ---------------------------------------------------------------------------
# Tenant-safe vehicle selection (design doc Section 4 / spec Section 6).
# ---------------------------------------------------------------------------
def _select_tenant_vehicles(session: Session, organization_id: str) -> list[MotiveVehicleRecord]:
    """Tenant-scoped, deterministically ordered vehicle selection.

    Mirrors ``app.api.motive._vehicles_for_utilization_contract``'s
    ``organization_id`` scope and ``MotiveVehicleRecord.id`` ascending
    ordering convention, WITHOUT that helper's controlled-validation-specific
    ``MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES = 3`` cap --
    reconciliation batching (:func:`_batch_provider_vehicle_ids`), not
    vehicle selection, is the correct place to bound request size here.
    Never auto-creates a vehicle; never returns another organization's rows.
    """
    return (
        session.query(MotiveVehicleRecord)
        .filter(MotiveVehicleRecord.organization_id == organization_id)
        .order_by(MotiveVehicleRecord.id.asc())
        .all()
    )


def _batch_provider_vehicle_ids(provider_vehicle_ids: Sequence[str], batch_size: int) -> list[tuple[str, ...]]:
    """Deterministic, stable-order batching.

    Every id appears exactly once, in exactly one batch. Batch order and
    within-batch order both follow the input order, so this is safe to call
    with an already deterministically ordered vehicle-id sequence.
    """
    return [tuple(provider_vehicle_ids[index : index + batch_size]) for index in range(0, len(provider_vehicle_ids), batch_size)]


def _max_authorized_provider_calls(window_count: int, batch_count: int) -> int:
    return window_count * batch_count * RUNNER_MAX_PAGES_PER_UNIT


def _failed_unit(start_date: date, end_date: date, batch_ordinal: int, error_code: str) -> FailedReconciliationUnit:
    return FailedReconciliationUnit(
        window_start=start_date.isoformat(),
        window_end=end_date.isoformat(),
        batch_ordinal=batch_ordinal,
        error_code=error_code,
    )


def _overall_status(*, vehicle_batches_attempted: int, vehicle_batches_completed: int) -> str:
    if vehicle_batches_completed == vehicle_batches_attempted:
        return "success"
    if vehicle_batches_completed > 0:
        return "partial_success"
    return "failed"


def _no_op_result(horizon_days: int) -> VehicleUtilizationRecentReconciliationResult:
    return VehicleUtilizationRecentReconciliationResult(
        status="no_op",
        resource=_RESOURCE,
        run_mode=_RUN_MODE,
        horizon_days=horizon_days,
        windows_attempted=0,
        windows_completed=0,
        windows_failed=0,
        selected_vehicle_count=0,
        vehicle_batches_attempted=0,
        vehicle_batches_completed=0,
        vehicle_batches_failed=0,
        provider_calls_attempted=0,
        provider_calls_completed=0,
        rollups_returned=0,
        missing_requested_vehicle_count=0,
        records_inserted=0,
        records_unchanged=0,
        records_updated=0,
        reconciled_fields_count=0,
    )


# ---------------------------------------------------------------------------
# Section 8/10/11/12 -- full bounded orchestration.
#
# Callers must already have: authenticated the caller and loaded the
# authenticated organization. This is an INTERNAL runtime primitive with no
# public route; a separately authorized future gate decides the safest
# manual invocation mechanism.
# ---------------------------------------------------------------------------
def run_recent_vehicle_utilization_reconciliation(
    session: Session,
    *,
    organization_id: str,
    organization_slug: str,
    horizon_days: int = DEFAULT_RECENT_RECONCILIATION_DAYS,
    http_client: httpx.Client | None = None,
) -> VehicleUtilizationRecentReconciliationResult:
    """Run one bounded, bidirectional-safe recent-window reconciliation.

    Fails closed BEFORE any provider HTTP request if: the feature gate
    (:func:`recent_reconciliation_enabled`) is disabled; ``horizon_days`` is
    not a strictly positive integer within :data:`MAX_RECENT_RECONCILIATION_DAYS`;
    or the deterministic maximum authorized call budget (``D x B x P``, see
    the module-level "Call-budget safety" documentation) exceeds
    :data:`RUNNER_MAX_AUTHORIZED_PROVIDER_CALLS`.

    Selects tenant-owned vehicles (:func:`_select_tenant_vehicles`) and, if
    none are found, makes ZERO provider calls and ZERO writes, returning a
    sanitized ``status="no_op"`` result.

    Otherwise generates one independent ``(day, vehicle batch)`` unit of
    work per calendar day in the horizon x vehicle batch, and for each unit:
    reads every provider page via the general certified reader
    (:func:`~app.connectors.motive_vehicle_utilization_pagination.read_vehicle_utilization_pages`,
    unmodified, ``ACCOUNT_DEFAULT`` unit mode, no retry), then calls the
    existing merged writer transaction
    (:func:`~app.motive.vehicle_utilization_writer.write_vehicle_utilization_transaction`,
    unmodified) EXACTLY ONCE, which owns its own single commit / whole-unit
    rollback. A known, already-typed, safe operational failure at either
    stage is recorded as a sanitized :class:`FailedReconciliationUnit` and
    processing continues with the next unit; already-committed earlier
    units are never rolled back, and no unit is ever automatically retried.
    A genuinely unexpected exception is NOT caught here and propagates,
    aborting the whole run.

    Never mutates ``MotiveSyncCheckpoint``. Never writes
    ``MotiveSyncHistory``. The returned result always reports
    ``checkpoint_advanced = False``, ``sync_history_written = False``, and
    ``scheduled_ingestion_enabled = False``.
    """
    if not recent_reconciliation_enabled():
        raise MotiveVehicleUtilizationRecentReconciliationError(
            "recent_reconciliation_disabled",
            "Motive vehicle utilization recent-window reconciliation is disabled. "
            f"Set {RECENT_RECONCILIATION_ENABLED_ENV_VAR} to enable it.",
        )
    _validate_horizon_days(horizon_days)

    windows = _generate_day_windows(horizon_days)

    selected_vehicles = _select_tenant_vehicles(session, organization_id)
    provider_vehicle_ids = [vehicle.provider_vehicle_id for vehicle in selected_vehicles]
    selected_vehicle_count = len(provider_vehicle_ids)

    if selected_vehicle_count == 0:
        logger.info(
            "MOTIVE VEHICLE UTILIZATION RECENT RECONCILIATION",
            extra={
                "motive_operation": "vehicle_utilization_recent_reconciliation",
                "organization_id": organization_id,
                "horizon_days": horizon_days,
                "selected_vehicle_count": 0,
                "status": "no_op",
            },
        )
        return _no_op_result(horizon_days)

    batches = _batch_provider_vehicle_ids(provider_vehicle_ids, MAX_VEHICLES_PER_BATCH)

    max_authorized_provider_calls = _max_authorized_provider_calls(len(windows), len(batches))
    if max_authorized_provider_calls > RUNNER_MAX_AUTHORIZED_PROVIDER_CALLS:
        raise MotiveVehicleUtilizationRecentReconciliationError(
            "call_budget_exceeded",
            "Motive vehicle utilization recent-window reconciliation computed call budget "
            f"({max_authorized_provider_calls}) exceeded the runner safety cap "
            f"({RUNNER_MAX_AUTHORIZED_PROVIDER_CALLS}).",
        )

    windows_attempted = len(windows)
    windows_completed = 0
    windows_failed = 0
    vehicle_batches_attempted = 0
    vehicle_batches_completed = 0
    vehicle_batches_failed = 0
    provider_calls_attempted = 0
    provider_calls_completed = 0
    rollups_returned = 0
    missing_requested_vehicle_count = 0
    records_inserted = 0
    records_unchanged = 0
    records_updated = 0
    reconciled_fields_count = 0
    failed_units: list[FailedReconciliationUnit] = []

    for start_date, end_date in windows:
        window_had_failure = False
        for batch_ordinal, batch in enumerate(batches, start=1):
            vehicle_batches_attempted += 1

            try:
                read_result = read_vehicle_utilization_pages(
                    organization_id=organization_id,
                    organization_slug=organization_slug,
                    provider_vehicle_ids=batch,
                    start_date=start_date,
                    end_date=end_date,
                    per_page=RECENT_RECONCILIATION_PAGE_SIZE,
                    unit_request_mode=MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT,
                    http_client=http_client,
                )
            except (MotiveConnectorError, MotiveVehicleUtilizationPaginationError) as exc:
                # Known, already-typed, safe operational read-stage failure.
                # At least one provider call was attempted before this
                # failure surfaced; the reader does not expose a partial
                # page count on failure, so this is a sanitized, conservative
                # lower bound, never a raw provider value.
                provider_calls_attempted += 1
                window_had_failure = True
                vehicle_batches_failed += 1
                failed_units.append(_failed_unit(start_date, end_date, batch_ordinal, exc.code))
                continue

            provider_calls_attempted += read_result.provider_calls
            provider_calls_completed += read_result.provider_calls
            rollups_returned += len(read_result.rollups)

            try:
                write_result = write_vehicle_utilization_transaction(
                    session,
                    organization_id=organization_id,
                    organization_slug=organization_slug,
                    selected_provider_vehicle_ids=batch,
                    request_window_start=start_date,
                    request_window_end=end_date,
                    rollups=read_result.rollups,
                    unit_request_mode=MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT,
                )
            except MotiveVehicleUtilizationWriterError as exc:
                # Known, already-typed, safe operational write-stage
                # failure. The writer already rolled back this unit's own
                # transaction internally before raising -- no additional
                # rollback is needed or performed here.
                window_had_failure = True
                vehicle_batches_failed += 1
                failed_units.append(_failed_unit(start_date, end_date, batch_ordinal, exc.code))
                continue

            vehicle_batches_completed += 1
            missing_requested_vehicle_count += write_result.missing_requested_vehicle_count
            records_inserted += write_result.records_inserted
            records_unchanged += write_result.records_unchanged
            records_updated += write_result.records_updated
            reconciled_fields_count += write_result.reconciled_fields_count

        if window_had_failure:
            windows_failed += 1
        else:
            windows_completed += 1

    status = _overall_status(
        vehicle_batches_attempted=vehicle_batches_attempted,
        vehicle_batches_completed=vehicle_batches_completed,
    )

    result = VehicleUtilizationRecentReconciliationResult(
        status=status,
        resource=_RESOURCE,
        run_mode=_RUN_MODE,
        horizon_days=horizon_days,
        windows_attempted=windows_attempted,
        windows_completed=windows_completed,
        windows_failed=windows_failed,
        selected_vehicle_count=selected_vehicle_count,
        vehicle_batches_attempted=vehicle_batches_attempted,
        vehicle_batches_completed=vehicle_batches_completed,
        vehicle_batches_failed=vehicle_batches_failed,
        provider_calls_attempted=provider_calls_attempted,
        provider_calls_completed=provider_calls_completed,
        rollups_returned=rollups_returned,
        missing_requested_vehicle_count=missing_requested_vehicle_count,
        records_inserted=records_inserted,
        records_unchanged=records_unchanged,
        records_updated=records_updated,
        reconciled_fields_count=reconciled_fields_count,
        failed_units=tuple(failed_units),
    )

    logger.info(
        "MOTIVE VEHICLE UTILIZATION RECENT RECONCILIATION",
        extra={
            "motive_operation": "vehicle_utilization_recent_reconciliation",
            "organization_id": organization_id,
            "horizon_days": horizon_days,
            "selected_vehicle_count": selected_vehicle_count,
            "windows_attempted": windows_attempted,
            "windows_completed": windows_completed,
            "windows_failed": windows_failed,
            "vehicle_batches_attempted": vehicle_batches_attempted,
            "vehicle_batches_completed": vehicle_batches_completed,
            "vehicle_batches_failed": vehicle_batches_failed,
            "provider_calls_attempted": provider_calls_attempted,
            "provider_calls_completed": provider_calls_completed,
            "records_inserted": records_inserted,
            "records_unchanged": records_unchanged,
            "records_updated": records_updated,
            "reconciled_fields_count": reconciled_fields_count,
            "status": status,
        },
    )
    return result
