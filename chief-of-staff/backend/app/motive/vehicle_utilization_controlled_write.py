"""Controlled, feature-flagged Motive vehicle-utilization WRITE validation.

Scope of this module:

- connects the certified Motive pagination read primitive
  (:mod:`app.connectors.motive_vehicle_utilization_pagination`) to the merged
  all-or-nothing durable writer transaction
  (:func:`app.motive.vehicle_utilization_writer.write_vehicle_utilization_transaction`)
  for exactly ONE fixed, previously-observed historical completed day
  (2026-08-13..2026-08-13);
- makes AT MOST ONE Motive provider HTTP request per invocation. This module
  never fetches a second page even if provider pagination metadata looks
  malformed -- it fails closed instead. It does not call, weaken, or modify
  the general certified paginated reader
  (:func:`app.connectors.motive_vehicle_utilization_pagination.read_vehicle_utilization_pages`);
- is disabled by default. The feature flag
  ``MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED`` must be explicitly
  set to a truthy value before this module's orchestration function may be
  invoked with real effect. Callers (the public route) are responsible for
  checking :func:`controlled_write_enabled` BEFORE calling
  :func:`run_controlled_vehicle_utilization_write` and must not call it at all
  when the flag is disabled;
- never touches ``MotiveSyncCheckpoint`` or ``MotiveSyncHistory``;
- never exposes provider vehicle IDs, VINs, unit numbers, or metric values in
  its result type, its errors, or its logging.

This is NOT broad vehicle-utilization ingestion, NOT scheduled sync, and NOT
checkpoint implementation. It is a tightly bounded, explicitly controlled
production write validation path for one fixed historical day.

2026-08-17 historical-rollup reconciliation gate: this module's read/validate
bounds (one page, one provider call, fixed day, at most
``CONTROLLED_WRITE_MAX_SELECTED_VEHICLES`` vehicles) are UNCHANGED. Only the
underlying writer transaction's replay policy changed: a repeat invocation
whose returned rollup differs from an already-persisted row in an approved
mutable field (see ``MUTABLE_ON_PROVIDER_RECONCILIATION`` in
``vehicle_utilization_writer.py``) now reconciles that row in place instead
of failing closed. This route still makes zero checkpoint or sync-history
writes either way.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
import logging
import os
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.connectors.motive import MotiveConnectorError
from app.connectors.motive_vehicle_utilization import (
    MotiveVehicleUtilizationParseError,
    MotiveVehicleUtilizationRequestContext,
    MotiveVehicleUtilizationRollup,
    parse_vehicle_utilization_rollups,
)
from app.connectors.motive_vehicle_utilization_contract import MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES
from app.connectors.motive_vehicle_utilization_pagination import (
    MOTIVE_VEHICLE_UTILIZATION_PAGINATION_CANONICAL_WRITER_PAGE_SIZE,
    MOTIVE_VEHICLE_UTILIZATION_PAGINATION_FIRST_PAGE,
    MotiveVehicleUtilizationPaginationError,
    parse_pagination_metadata,
    request_vehicle_utilization_page,
)
from app.motive.vehicle_utilization_unit_policy import MotiveVehicleUtilizationUnitRequestMode
from app.motive.vehicle_utilization_writer import (
    MotiveVehicleUtilizationWriterError,
    write_vehicle_utilization_transaction,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safety enable switch (section 6). Disabled unless explicitly, strictly true.
# ---------------------------------------------------------------------------
CONTROLLED_WRITE_ENABLED_ENV_VAR = "MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def controlled_write_enabled() -> bool:
    """Strict boolean parse of the controlled-write kill switch.

    Defaults to False (disabled) whenever the environment variable is unset,
    empty, or holds an unrecognized value. Never enabled implicitly.
    """
    value = os.getenv(CONTROLLED_WRITE_ENABLED_ENV_VAR)
    if value is None:
        return False
    return value.strip().lower() in _TRUTHY_ENV_VALUES


# ---------------------------------------------------------------------------
# Fixed controlled production window (section 2). NEVER computed at runtime;
# never accepted from the caller.
# ---------------------------------------------------------------------------
CONTROLLED_WRITE_WINDOW_START = date(2026, 8, 13)
CONTROLLED_WRITE_WINDOW_END = date(2026, 8, 13)

# ---------------------------------------------------------------------------
# One-page contract (sections 4/9). Certified writer page size, first page
# only. At most one provider call, ever.
#
# 2026-08-17 account-default validation gate: this route's provider request
# and writer transaction call now explicitly use
# MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT (see
# _execute_one_page_controlled_read and run_controlled_vehicle_utilization_write
# below) instead of the prior forced X-Metric-Units: true canonical policy.
# The X-Metric-Units header is therefore omitted entirely on this route's one
# provider request; the writer's account-default readiness rule accepts a
# returned metric_units of either True or False and persists it as observed,
# still failing closed on a missing or malformed indicator.
# ---------------------------------------------------------------------------
CONTROLLED_WRITE_PAGE_NO = MOTIVE_VEHICLE_UTILIZATION_PAGINATION_FIRST_PAGE
CONTROLLED_WRITE_PAGE_SIZE = MOTIVE_VEHICLE_UTILIZATION_PAGINATION_CANONICAL_WRITER_PAGE_SIZE
CONTROLLED_WRITE_MAX_SELECTED_VEHICLES = MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES
CONTROLLED_WRITE_MAX_PROVIDER_CALLS = 1


class MotiveVehicleUtilizationControlledWriteError(ValueError):
    """Safe, fail-closed controlled-write validation error.

    Carries only sanitized diagnostic counters (section 13). Never includes
    provider vehicle IDs, VINs, unit numbers, metric values, or raw payload
    contents in ``str(error)`` or its attributes.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        provider_calls_attempted: int = 0,
        provider_calls_completed: int = 0,
        selected_vehicle_count: int = 0,
        returned_rollup_count: int = 0,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.provider_calls_attempted = provider_calls_attempted
        self.provider_calls_completed = provider_calls_completed
        self.selected_vehicle_count = selected_vehicle_count
        self.returned_rollup_count = returned_rollup_count


@dataclass(frozen=True, slots=True)
class _OnePageControlledRead:
    rollups: list[MotiveVehicleUtilizationRollup]
    pagination_total: int
    provider_calls_attempted: int
    provider_calls_completed: int


# ---------------------------------------------------------------------------
# Section 4/9 -- narrow, bounded, ONE-PAGE-ONLY controlled reader. Does not
# call or modify the general certified paginated reader
# (app.connectors.motive_vehicle_utilization_pagination.read_vehicle_utilization_pages).
# ---------------------------------------------------------------------------
def _execute_one_page_controlled_read(
    *,
    organization_id: str,
    organization_slug: str,
    selected_provider_vehicle_ids: Sequence[str],
    start_date: date,
    end_date: date,
    http_client: httpx.Client | None,
) -> _OnePageControlledRead:
    selected_vehicle_set = set(selected_provider_vehicle_ids)
    selected_vehicle_count = len(selected_vehicle_set)

    provider_calls_attempted = 1
    try:
        payload, _http_status = request_vehicle_utilization_page(
            organization_id=organization_id,
            provider_vehicle_ids=selected_provider_vehicle_ids,
            start_date=start_date,
            end_date=end_date,
            page_no=CONTROLLED_WRITE_PAGE_NO,
            per_page=CONTROLLED_WRITE_PAGE_SIZE,
            unit_request_mode=MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT,
            http_client=http_client,
        )
    except MotiveConnectorError as exc:
        raise MotiveVehicleUtilizationControlledWriteError(
            exc.code or "provider_request_failed",
            "Motive vehicle utilization controlled write provider request failed.",
            provider_calls_attempted=provider_calls_attempted,
            provider_calls_completed=0,
            selected_vehicle_count=selected_vehicle_count,
            returned_rollup_count=0,
        ) from exc
    provider_calls_completed = 1

    try:
        metadata = parse_pagination_metadata(
            payload,
            expected_page_no=CONTROLLED_WRITE_PAGE_NO,
            expected_per_page=CONTROLLED_WRITE_PAGE_SIZE,
        )
    except MotiveVehicleUtilizationPaginationError as exc:
        raise MotiveVehicleUtilizationControlledWriteError(
            exc.code,
            "Motive vehicle utilization controlled write pagination metadata failed strict validation.",
            provider_calls_attempted=provider_calls_attempted,
            provider_calls_completed=provider_calls_completed,
            selected_vehicle_count=selected_vehicle_count,
            returned_rollup_count=0,
        ) from exc

    # Section 9: legitimate pagination total must never exceed the selected
    # vehicle count for this bounded, one-page-per-vehicle-set contract.
    if metadata.total > selected_vehicle_count:
        raise MotiveVehicleUtilizationControlledWriteError(
            "pagination_total_exceeds_selected_vehicles",
            "Motive vehicle utilization controlled write pagination total exceeded the selected vehicle count.",
            provider_calls_attempted=provider_calls_attempted,
            provider_calls_completed=provider_calls_completed,
            selected_vehicle_count=selected_vehicle_count,
            returned_rollup_count=0,
        )

    try:
        rollups = parse_vehicle_utilization_rollups(
            payload,
            organization_id=organization_id,
            organization_slug=organization_slug,
            request_context=MotiveVehicleUtilizationRequestContext(
                request_start_date=start_date,
                request_end_date=end_date,
            ),
        )
    except MotiveVehicleUtilizationParseError as exc:
        raise MotiveVehicleUtilizationControlledWriteError(
            exc.code,
            "Motive vehicle utilization controlled write response did not match the certified provider schema.",
            provider_calls_attempted=provider_calls_attempted,
            provider_calls_completed=provider_calls_completed,
            selected_vehicle_count=selected_vehicle_count,
            returned_rollup_count=0,
        ) from exc

    if len(rollups) != metadata.total:
        raise MotiveVehicleUtilizationControlledWriteError(
            "returned_item_count_mismatch",
            "Motive vehicle utilization controlled write returned item count did not equal the pagination total.",
            provider_calls_attempted=provider_calls_attempted,
            provider_calls_completed=provider_calls_completed,
            selected_vehicle_count=selected_vehicle_count,
            returned_rollup_count=len(rollups),
        )

    seen_provider_vehicle_ids: set[str] = set()
    for rollup in rollups:
        if rollup.provider_vehicle_id in seen_provider_vehicle_ids:
            raise MotiveVehicleUtilizationControlledWriteError(
                "duplicate_returned_rollup",
                "Motive vehicle utilization controlled write returned a duplicate vehicle rollup.",
                provider_calls_attempted=provider_calls_attempted,
                provider_calls_completed=provider_calls_completed,
                selected_vehicle_count=selected_vehicle_count,
                returned_rollup_count=len(rollups),
            )
        seen_provider_vehicle_ids.add(rollup.provider_vehicle_id)

        if rollup.provider_vehicle_id not in selected_vehicle_set:
            raise MotiveVehicleUtilizationControlledWriteError(
                "unexpected_returned_vehicle",
                "Motive vehicle utilization controlled write returned a vehicle outside the selected vehicle set.",
                provider_calls_attempted=provider_calls_attempted,
                provider_calls_completed=provider_calls_completed,
                selected_vehicle_count=selected_vehicle_count,
                returned_rollup_count=len(rollups),
            )

        # Deliberately no unit-readiness check here. Provider schema parse
        # success is distinct from durable persistence readiness (see
        # vehicle_utilization_unit_policy.py): the returned metric_units
        # Boolean is preserved as observed context by the parser, and the
        # writer transaction below is the single place that fails closed on
        # unresolved returned unit-indicator semantics, before any commit.

    return _OnePageControlledRead(
        rollups=rollups,
        pagination_total=metadata.total,
        provider_calls_attempted=provider_calls_attempted,
        provider_calls_completed=provider_calls_completed,
    )


# ---------------------------------------------------------------------------
# Sections 8/10/11/12 -- full controlled read-to-write orchestration.
#
# Callers MUST already have: authenticated the caller with CONNECTOR_WRITE,
# verified controlled_write_enabled() is True, verified any required
# execution confirmation, loaded the authenticated organization, and selected
# up to CONTROLLED_WRITE_MAX_SELECTED_VEHICLES deterministic stored
# organization-owned vehicles (organization_id + MotiveVehicleRecord.id
# ascending). This function performs the fixed-window provider read, strict
# validation, and the durable writer transaction only.
# ---------------------------------------------------------------------------
def run_controlled_vehicle_utilization_write(
    session: Session,
    *,
    organization_id: str,
    organization_slug: str,
    selected_provider_vehicle_ids: Sequence[str],
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    normalized_selected = [
        provider_vehicle_id for provider_vehicle_id in selected_provider_vehicle_ids if provider_vehicle_id
    ][:CONTROLLED_WRITE_MAX_SELECTED_VEHICLES]
    if not normalized_selected:
        raise MotiveVehicleUtilizationControlledWriteError(
            "no_stored_vehicle",
            "Motive vehicle utilization controlled write validation requires at least one selected vehicle.",
        )

    read_result = _execute_one_page_controlled_read(
        organization_id=organization_id,
        organization_slug=organization_slug,
        selected_provider_vehicle_ids=normalized_selected,
        start_date=CONTROLLED_WRITE_WINDOW_START,
        end_date=CONTROLLED_WRITE_WINDOW_END,
        http_client=http_client,
    )

    try:
        write_result = write_vehicle_utilization_transaction(
            session,
            organization_id=organization_id,
            organization_slug=organization_slug,
            selected_provider_vehicle_ids=normalized_selected,
            request_window_start=CONTROLLED_WRITE_WINDOW_START,
            request_window_end=CONTROLLED_WRITE_WINDOW_END,
            rollups=read_result.rollups,
            unit_request_mode=MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT,
        )
    except MotiveVehicleUtilizationWriterError as exc:
        raise MotiveVehicleUtilizationControlledWriteError(
            exc.code,
            "Motive vehicle utilization controlled write transaction failed and was rolled back.",
            provider_calls_attempted=read_result.provider_calls_attempted,
            provider_calls_completed=read_result.provider_calls_completed,
            selected_vehicle_count=len(normalized_selected),
            returned_rollup_count=len(read_result.rollups),
        ) from exc

    logger.info(
        "MOTIVE VEHICLE UTILIZATION CONTROLLED WRITE VALIDATION",
        extra={
            "motive_operation": "vehicle_utilization_controlled_write_validation",
            "organization_id": organization_id,
            "request_window_start": CONTROLLED_WRITE_WINDOW_START.isoformat(),
            "request_window_end": CONTROLLED_WRITE_WINDOW_END.isoformat(),
            "selected_vehicle_count": len(normalized_selected),
            "provider_calls_attempted": read_result.provider_calls_attempted,
            "provider_calls_completed": read_result.provider_calls_completed,
            "pagination_total": read_result.pagination_total,
            "returned_rollup_count": len(read_result.rollups),
            "records_inserted": write_result.records_inserted,
            "records_unchanged": write_result.records_unchanged,
            "records_updated": write_result.records_updated,
            "reconciled_fields_count": write_result.reconciled_fields_count,
            "status": "committed",
        },
    )

    return {
        "status": "success",
        "resource": "vehicle_utilization_controlled_write_validation",
        "validation_mode": "controlled_manual_write_validation",
        "request_window_start": CONTROLLED_WRITE_WINDOW_START.isoformat(),
        "request_window_end": CONTROLLED_WRITE_WINDOW_END.isoformat(),
        "selected_vehicle_count": len(normalized_selected),
        "provider_calls_attempted": read_result.provider_calls_attempted,
        "provider_calls_completed": read_result.provider_calls_completed,
        "pagination_total": read_result.pagination_total,
        "returned_rollup_count": write_result.returned_rollup_count,
        "missing_requested_vehicle_count": write_result.missing_requested_vehicle_count,
        "records_inserted": write_result.records_inserted,
        "records_unchanged": write_result.records_unchanged,
        "records_updated": write_result.records_updated,
        "reconciled_fields_count": write_result.reconciled_fields_count,
        "committed": write_result.committed,
        "checkpoint_advanced": False,
        "sync_history_written": False,
        "scheduled_ingestion_enabled": False,
        "secrets_exposed": False,
    }
