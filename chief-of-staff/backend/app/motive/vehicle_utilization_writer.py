"""Internal, all-or-nothing database writer transaction for Motive
vehicle-utilization rollups.

Scope of this module (the durable *transaction primitive* only):

- makes ZERO Motive HTTP calls;
- receives already-parsed, already-validated
  :class:`~app.connectors.motive_vehicle_utilization.MotiveVehicleUtilizationRollup`
  values -- for example from
  :func:`app.connectors.motive_vehicle_utilization_pagination.read_vehicle_utilization_pages`
  -- and re-validates every writer precondition defensively before staging any
  row;
- persists only provider-returned rollups that resolve to an existing
  tenant-owned ``MotiveVehicleRecord``;
- owns exactly ONE commit for the whole batch and rolls back the entire
  transaction on any failure (whole-batch, all-or-nothing);
- never touches ``MotiveSyncCheckpoint`` or ``MotiveSyncHistory``;
- never exposes provider vehicle IDs, VINs, unit numbers, or metric values in
  its result type, its errors, or its logging.

This module does NOT enable a runtime provider-to-database sync. There is no
public route that calls it. It is the internal primitive that a later,
separately-authorized manual production validation route may call.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import logging

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.connectors.motive_contracts import MOTIVE_PROVIDER
from app.connectors.motive_vehicle_utilization import (
    PARSER_VERSION,
    MotiveVehicleUtilizationRollup,
)
from app.connectors.motive_vehicle_utilization_contract import MOTIVE_VEHICLE_UTILIZATION_ENDPOINT
from app.models.motive import MotiveVehicleRecord, MotiveVehicleUtilizationRecord
from app.motive.vehicle_utilization_unit_policy import validate_vehicle_utilization_writer_metric_units

logger = logging.getLogger(__name__)

# The only certified provenance a durable row may carry in this gate. A
# manually-constructed/incompatible rollup claiming another parser version or
# source endpoint fails closed rather than being accepted.
CERTIFIED_PARSER_VERSION = PARSER_VERSION
CERTIFIED_SOURCE_ENDPOINT = MOTIVE_VEHICLE_UTILIZATION_ENDPOINT


class MotiveVehicleUtilizationWriterError(ValueError):
    """Safe, fail-closed writer error.

    Never includes provider vehicle IDs, VINs, unit numbers, metric values,
    secrets, or raw payload contents in ``str(error)``.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class VehicleUtilizationWriteResult:
    """Sanitized, immutable result of one writer transaction attempt.

    Deliberately excludes provider vehicle IDs, VIN, unit numbers, metric
    values, raw row values, and raw payload contents.
    """

    committed: bool
    requested_vehicle_count: int
    returned_rollup_count: int
    records_inserted: int
    records_unchanged: int
    records_updated: int
    missing_requested_vehicle_count: int


@dataclass(frozen=True, slots=True)
class _WritePlan:
    rows_to_insert: list[MotiveVehicleUtilizationRecord]
    unchanged_count: int


def write_vehicle_utilization_transaction(
    session: Session,
    *,
    organization_id: str,
    organization_slug: str,
    selected_provider_vehicle_ids: Sequence[str],
    request_window_start: date,
    request_window_end: date,
    rollups: Sequence[MotiveVehicleUtilizationRollup],
) -> VehicleUtilizationWriteResult:
    """Persist validated, already-parsed vehicle-utilization rollups.

    ALL OR NOTHING: the entire incoming batch is validated before any row is
    staged. This function owns exactly one commit and rolls back the whole
    transaction on any failure. It never mutates ``MotiveSyncCheckpoint`` or
    ``MotiveSyncHistory``.
    """
    rollups_list = list(rollups)
    selected_vehicle_set: set[str] = set()

    try:
        # 1. Validate caller/request context.
        _validate_request_context(
            organization_id=organization_id,
            organization_slug=organization_slug,
            request_window_start=request_window_start,
            request_window_end=request_window_end,
        )

        # 2. Validate the selected vehicle set structure.
        normalized_selected_ids = _validate_selected_vehicle_ids(selected_provider_vehicle_ids)
        selected_vehicle_set = set(normalized_selected_ids)

        # 3. Validate every rollup structurally, then organization context,
        #    then request window -- for the WHOLE batch before proceeding.
        for rollup in rollups_list:
            _validate_rollup_structure(rollup)
        for rollup in rollups_list:
            _validate_rollup_organization_context(
                rollup, organization_id=organization_id, organization_slug=organization_slug
            )
        for rollup in rollups_list:
            _validate_rollup_request_window(
                rollup, request_window_start=request_window_start, request_window_end=request_window_end
            )

        # 4. No duplicate returned vehicle within the incoming batch.
        _validate_no_duplicate_returned_rollups(rollups_list)

        # 5. Every returned vehicle must be within the selected set.
        _validate_returned_vehicles_within_selected_set(rollups_list, selected_vehicle_set=selected_vehicle_set)

        # 6. Canonical unit context (fail closed on False/None/unknown).
        for rollup in rollups_list:
            _validate_unit_context(rollup)

        # 7. Certified parser/source provenance only.
        for rollup in rollups_list:
            _validate_parser_and_source(rollup)

        # 8. Resolve tenant-owned MotiveVehicleRecord associations.
        vehicle_by_provider_id = _resolve_tenant_vehicles(
            session,
            organization_id=organization_id,
            provider_vehicle_ids=[rollup.provider_vehicle_id for rollup in rollups_list],
        )

        # 9/10. Inspect existing durable identities; fail closed on conflict.
        plan = _plan_writes(
            session,
            organization_id=organization_id,
            organization_slug=organization_slug,
            rollups=rollups_list,
            vehicle_by_provider_id=vehicle_by_provider_id,
        )

        # 11. Stage new rows only after the whole batch has been validated.
        for row in plan.rows_to_insert:
            session.add(row)

        # 12. Flush.
        session.flush()

        # 13. Commit once.
        session.commit()
    except MotiveVehicleUtilizationWriterError:
        session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        raise MotiveVehicleUtilizationWriterError(
            "database_identity_conflict",
            "A durable vehicle-utilization row already exists for this identity.",
        ) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        raise MotiveVehicleUtilizationWriterError(
            "database_persistence_error",
            "A database error occurred while writing vehicle-utilization rows.",
        ) from exc

    returned_provider_vehicle_ids = {rollup.provider_vehicle_id for rollup in rollups_list}
    missing_requested_vehicle_count = len(selected_vehicle_set - returned_provider_vehicle_ids)

    result = VehicleUtilizationWriteResult(
        committed=True,
        requested_vehicle_count=len(selected_vehicle_set),
        returned_rollup_count=len(rollups_list),
        records_inserted=len(plan.rows_to_insert),
        records_unchanged=plan.unchanged_count,
        records_updated=0,
        missing_requested_vehicle_count=missing_requested_vehicle_count,
    )

    logger.info(
        "MOTIVE VEHICLE UTILIZATION WRITE",
        extra={
            "motive_operation": "vehicle_utilization_write",
            "organization_id": organization_id,
            "request_window_start": request_window_start.isoformat(),
            "request_window_end": request_window_end.isoformat(),
            "requested_vehicle_count": result.requested_vehicle_count,
            "returned_rollup_count": result.returned_rollup_count,
            "records_inserted": result.records_inserted,
            "records_unchanged": result.records_unchanged,
            "status": "committed",
        },
    )
    return result


# ---------------------------------------------------------------------------
# Step 1 -- caller/request context.
# ---------------------------------------------------------------------------
def _validate_request_context(
    *,
    organization_id: str,
    organization_slug: str,
    request_window_start: date,
    request_window_end: date,
) -> None:
    if not isinstance(organization_id, str) or not organization_id.strip():
        raise MotiveVehicleUtilizationWriterError(
            "invalid_writer_request", "Vehicle utilization writer requires a non-empty organization_id."
        )
    if not isinstance(organization_slug, str) or not organization_slug.strip():
        raise MotiveVehicleUtilizationWriterError(
            "invalid_writer_request", "Vehicle utilization writer requires a non-empty organization_slug."
        )
    if isinstance(request_window_start, datetime) or not isinstance(request_window_start, date):
        raise MotiveVehicleUtilizationWriterError(
            "request_window_invalid", "Vehicle utilization writer requires an explicit request_window_start date."
        )
    if isinstance(request_window_end, datetime) or not isinstance(request_window_end, date):
        raise MotiveVehicleUtilizationWriterError(
            "request_window_invalid", "Vehicle utilization writer requires an explicit request_window_end date."
        )
    if request_window_start > request_window_end:
        raise MotiveVehicleUtilizationWriterError(
            "request_window_invalid",
            "Vehicle utilization writer request_window_start must not be after request_window_end.",
        )


# ---------------------------------------------------------------------------
# Step 2 -- selected vehicle set structure.
# ---------------------------------------------------------------------------
def _validate_selected_vehicle_ids(selected_provider_vehicle_ids: Sequence[str] | None) -> tuple[str, ...]:
    if selected_provider_vehicle_ids is None:
        raise MotiveVehicleUtilizationWriterError(
            "invalid_writer_request", "Vehicle utilization writer requires a selected vehicle set."
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_id in selected_provider_vehicle_ids:
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise MotiveVehicleUtilizationWriterError(
                "invalid_writer_request", "Vehicle utilization writer selected vehicle ids must be non-empty strings."
            )
        if raw_id in seen:
            raise MotiveVehicleUtilizationWriterError(
                "invalid_writer_request", "Vehicle utilization writer selected vehicle ids must not contain duplicates."
            )
        seen.add(raw_id)
        normalized.append(raw_id)
    if not normalized:
        raise MotiveVehicleUtilizationWriterError(
            "invalid_writer_request", "Vehicle utilization writer requires at least one selected vehicle id."
        )
    return tuple(normalized)


# ---------------------------------------------------------------------------
# Step 3 -- per-rollup structural / organization / request-window validation.
# ---------------------------------------------------------------------------
def _validate_rollup_structure(rollup: MotiveVehicleUtilizationRollup) -> None:
    if not isinstance(rollup, MotiveVehicleUtilizationRollup):
        raise MotiveVehicleUtilizationWriterError(
            "invalid_writer_request", "Vehicle utilization writer requires certified rollup values."
        )
    if not isinstance(rollup.provider_vehicle_id, str) or not rollup.provider_vehicle_id.strip():
        raise MotiveVehicleUtilizationWriterError(
            "invalid_writer_request", "Vehicle utilization writer rollup requires a non-empty provider vehicle id."
        )


def _validate_rollup_organization_context(
    rollup: MotiveVehicleUtilizationRollup, *, organization_id: str, organization_slug: str
) -> None:
    if rollup.organization_id != organization_id or rollup.organization_slug != organization_slug:
        raise MotiveVehicleUtilizationWriterError(
            "organization_context_mismatch",
            "Vehicle utilization writer rollup did not match the authenticated organization context.",
        )


def _validate_rollup_request_window(
    rollup: MotiveVehicleUtilizationRollup, *, request_window_start: date, request_window_end: date
) -> None:
    if rollup.request_start_date is None or rollup.request_end_date is None:
        raise MotiveVehicleUtilizationWriterError(
            "request_window_missing", "Vehicle utilization writer rollup did not include an explicit request window."
        )
    if rollup.request_start_date != request_window_start or rollup.request_end_date != request_window_end:
        raise MotiveVehicleUtilizationWriterError(
            "request_window_invalid",
            "Vehicle utilization writer rollup request window did not match the caller request window.",
        )


# ---------------------------------------------------------------------------
# Steps 4/5 -- duplicate and unexpected-vehicle batch checks.
# ---------------------------------------------------------------------------
def _validate_no_duplicate_returned_rollups(rollups: Sequence[MotiveVehicleUtilizationRollup]) -> None:
    seen: set[str] = set()
    for rollup in rollups:
        if rollup.provider_vehicle_id in seen:
            raise MotiveVehicleUtilizationWriterError(
                "duplicate_returned_rollup",
                "Vehicle utilization writer received more than one rollup for the same vehicle and request window.",
            )
        seen.add(rollup.provider_vehicle_id)


def _validate_returned_vehicles_within_selected_set(
    rollups: Sequence[MotiveVehicleUtilizationRollup], *, selected_vehicle_set: set[str]
) -> None:
    for rollup in rollups:
        if rollup.provider_vehicle_id not in selected_vehicle_set:
            raise MotiveVehicleUtilizationWriterError(
                "unexpected_returned_vehicle",
                "Vehicle utilization writer received a rollup for a vehicle outside the selected vehicle set.",
            )


# ---------------------------------------------------------------------------
# Step 6 -- canonical unit context.
# ---------------------------------------------------------------------------
def _validate_unit_context(rollup: MotiveVehicleUtilizationRollup) -> None:
    validation = validate_vehicle_utilization_writer_metric_units(rollup.metric_units)
    if not validation.valid:
        raise MotiveVehicleUtilizationWriterError(
            validation.error_code or "provider_unit_context_missing",
            "Vehicle utilization writer rollup did not use the certified canonical metric unit policy.",
        )


# ---------------------------------------------------------------------------
# Step 7 -- certified parser/source provenance.
# ---------------------------------------------------------------------------
def _validate_parser_and_source(rollup: MotiveVehicleUtilizationRollup) -> None:
    if rollup.parser_version != CERTIFIED_PARSER_VERSION:
        raise MotiveVehicleUtilizationWriterError(
            "parser_version_not_certified", "Vehicle utilization writer rollup used an uncertified parser version."
        )
    if rollup.source_endpoint != CERTIFIED_SOURCE_ENDPOINT:
        raise MotiveVehicleUtilizationWriterError(
            "source_endpoint_not_certified", "Vehicle utilization writer rollup used an uncertified source endpoint."
        )


# ---------------------------------------------------------------------------
# Step 8 -- tenant-owned vehicle association. Never auto-creates a vehicle.
# A vehicle belonging to another organization is treated as unknown for this
# organization; the failure never reveals which provider ID caused it.
# ---------------------------------------------------------------------------
def _resolve_tenant_vehicles(
    session: Session, *, organization_id: str, provider_vehicle_ids: Sequence[str]
) -> dict[str, int]:
    unique_ids = set(provider_vehicle_ids)
    if not unique_ids:
        return {}
    with session.no_autoflush:
        vehicles = (
            session.query(MotiveVehicleRecord)
            .filter(
                MotiveVehicleRecord.organization_id == organization_id,
                MotiveVehicleRecord.provider_vehicle_id.in_(unique_ids),
            )
            .all()
        )
    resolved = {vehicle.provider_vehicle_id: vehicle.id for vehicle in vehicles}
    if unique_ids - resolved.keys():
        raise MotiveVehicleUtilizationWriterError(
            "unknown_vehicle",
            "A returned vehicle-utilization rollup did not resolve to exactly one stored tenant-owned vehicle.",
        )
    return resolved


# ---------------------------------------------------------------------------
# Steps 9/10 -- idempotent replay policy against existing durable identities.
# ---------------------------------------------------------------------------
def _plan_writes(
    session: Session,
    *,
    organization_id: str,
    organization_slug: str,
    rollups: Sequence[MotiveVehicleUtilizationRollup],
    vehicle_by_provider_id: dict[str, int],
) -> _WritePlan:
    if not rollups:
        return _WritePlan(rows_to_insert=[], unchanged_count=0)

    identity_keys = {
        (vehicle_by_provider_id[rollup.provider_vehicle_id], rollup.request_start_date, rollup.request_end_date)
        for rollup in rollups
    }
    existing_by_key = _load_existing_identity_rows(session, organization_id=organization_id, identity_keys=identity_keys)

    rows_to_insert: list[MotiveVehicleUtilizationRecord] = []
    unchanged_count = 0
    for rollup in rollups:
        motive_vehicle_id = vehicle_by_provider_id[rollup.provider_vehicle_id]
        key = (motive_vehicle_id, rollup.request_start_date, rollup.request_end_date)
        existing = existing_by_key.get(key)
        if existing is None:
            rows_to_insert.append(
                _build_new_row(
                    organization_id=organization_id,
                    organization_slug=organization_slug,
                    rollup=rollup,
                    motive_vehicle_id=motive_vehicle_id,
                )
            )
            continue
        if _is_identical_replay(existing, rollup):
            unchanged_count += 1
            continue
        # Conflicting replay OR the existing row lacks evidence it was
        # created under the certified writer contract -- fail closed either
        # way rather than silently treating it as an identical replay.
        raise MotiveVehicleUtilizationWriterError(
            "conflicting_existing_identity",
            "An existing durable vehicle-utilization row conflicts with this replay.",
        )

    return _WritePlan(rows_to_insert=rows_to_insert, unchanged_count=unchanged_count)


def _load_existing_identity_rows(
    session: Session,
    *,
    organization_id: str,
    identity_keys: set[tuple[int, date, date]],
) -> dict[tuple[int, date, date], MotiveVehicleUtilizationRecord]:
    """Load existing rows for the certified identity key.

    Kept as a separate, monkeypatch-friendly helper so tests can exercise the
    database unique constraint as the final concurrency guard (section 22/43
    of the writer transaction gate) without needing real concurrent sessions.
    """
    motive_vehicle_ids = {key[0] for key in identity_keys}
    if not motive_vehicle_ids:
        return {}
    with session.no_autoflush:
        rows = (
            session.query(MotiveVehicleUtilizationRecord)
            .filter(
                MotiveVehicleUtilizationRecord.organization_id == organization_id,
                MotiveVehicleUtilizationRecord.motive_vehicle_id.in_(motive_vehicle_ids),
                MotiveVehicleUtilizationRecord.request_window_start.isnot(None),
                MotiveVehicleUtilizationRecord.request_window_end.isnot(None),
            )
            .all()
        )
    return {
        (row.motive_vehicle_id, row.request_window_start, row.request_window_end): row
        for row in rows
        if (row.motive_vehicle_id, row.request_window_start, row.request_window_end) in identity_keys
    }


def _is_identical_replay(existing: MotiveVehicleUtilizationRecord, rollup: MotiveVehicleUtilizationRollup) -> bool:
    """Define exact same-result replay equivalence for the certified identity.

    An existing row is treated as an identical replay only when it carries
    evidence that it was created under the certified writer contract
    (canonical metric units, certified source endpoint, certified parser
    version) AND every writer-owned measurement/provenance field matches the
    incoming rollup using Decimal-safe (non-float) equality. Mutable,
    non-identity metadata such as ``organization_slug`` is deliberately not
    compared, since it may change without changing the durable identity.
    """
    if existing.metric_units is not True:
        return False
    if existing.source_endpoint != CERTIFIED_SOURCE_ENDPOINT:
        return False
    if existing.parser_version != CERTIFIED_PARSER_VERSION:
        return False
    if existing.provider_vehicle_id != rollup.provider_vehicle_id:
        return False
    if existing.request_window_start != rollup.request_start_date:
        return False
    if existing.request_window_end != rollup.request_end_date:
        return False
    if _decimal_differs(existing.utilization_percent, rollup.utilization_percent):
        return False
    if _decimal_differs(existing.idle_time, rollup.idle_time):
        return False
    if _decimal_differs(existing.driving_time, rollup.driving_time):
        return False
    if _decimal_differs(existing.idle_fuel, rollup.idle_fuel):
        return False
    if _decimal_differs(existing.driving_fuel, rollup.driving_fuel):
        return False
    return True


def _decimal_differs(existing_value: Decimal | None, incoming_value: Decimal | None) -> bool:
    """Decimal-safe (never float) comparison. No tolerance is applied."""
    if existing_value is None and incoming_value is None:
        return False
    if existing_value is None or incoming_value is None:
        return True
    return Decimal(existing_value) != Decimal(incoming_value)


def _build_new_row(
    *,
    organization_id: str,
    organization_slug: str,
    rollup: MotiveVehicleUtilizationRollup,
    motive_vehicle_id: int,
) -> MotiveVehicleUtilizationRecord:
    """Minimal, certified-only persistence. No inference, no raw payload."""
    return MotiveVehicleUtilizationRecord(
        organization_id=organization_id,
        organization_slug=organization_slug,
        provider=MOTIVE_PROVIDER,
        provider_vehicle_id=rollup.provider_vehicle_id,
        motive_vehicle_id=motive_vehicle_id,
        source_endpoint=CERTIFIED_SOURCE_ENDPOINT,
        request_window_start=rollup.request_start_date,
        request_window_end=rollup.request_end_date,
        reporting_period_start=None,
        reporting_period_end=None,
        utilization_percent=rollup.utilization_percent,
        idle_time=rollup.idle_time,
        driving_time=rollup.driving_time,
        idle_fuel=rollup.idle_fuel,
        driving_fuel=rollup.driving_fuel,
        metric_units=True,
        distance=None,
        engine_hours=None,
        observed_at=None,
        parser_version=CERTIFIED_PARSER_VERSION,
        provider_payload_metadata={},
    )
