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

--------------------------------------------------------------------------
2026-08-17 historical-rollup reconciliation gate (current)
--------------------------------------------------------------------------
Motive Support has confirmed that historical vehicle-utilization rollups may
legitimately change slightly as provider-side processing completes, and
recommended periodically rereading a recent rolling window. Prior to this
gate, ANY replay of an existing durable identity (``organization_id +
motive_vehicle_id + request_window_start + request_window_end``) whose
provider-derived values differed from the stored row was treated as a hard
conflict and rejected -- correct before the provider clarification, but not
compatible with safe rolling-window rereads.

This gate adds a narrow, field-by-field reconciliation policy (see
``docs/engineering/MOTIVE_UTILIZATION_HISTORICAL_RECONCILIATION.md`` for the
full field-level audit and matrix):

- durable identity (``organization_id``, ``motive_vehicle_id``,
  ``request_window_start``, ``request_window_end``) and every other
  identity/context/provenance field (``provider_vehicle_id``,
  ``source_endpoint``, ``parser_version``, ``metric_units``) remain
  IMMUTABLE. Any difference in these fields is still a hard conflict
  (``conflicting_existing_identity``) and never silently reconciled;
- exactly five provider-derived rollup metrics --
  :data:`MUTABLE_ON_PROVIDER_RECONCILIATION` -- may be updated in place when
  an existing, context-compatible row's value differs from a newly validated
  incoming rollup: ``utilization_percent``, ``idle_time``, ``driving_time``,
  ``idle_fuel``, ``driving_fuel``;
- reconciliation is an explicit, field-by-field comparison and controlled
  change set -- never a blind ORM ``merge()`` or broad column overwrite.
  Only fields that both (a) actually differ (Decimal-safe, no float
  coercion, no tolerance/epsilon) and (b) are in the approved mutable set are
  ever written; any unapproved field difference fails closed with
  :data:`RECONCILIATION_CONFLICT_ERROR_CODE` instead of being applied;
- whole-batch atomicity is preserved: every row's insert/unchanged/reconcile
  decision is computed BEFORE any row is staged or mutated, so a conflict on
  any single row in a batch still rolls back the entire batch, including
  otherwise-safe reconciliations for other rows in the same batch;
- a vehicle/window omitted from a later reread is never deleted, zeroed, or
  reclassified -- the writer only ever processes rows it is explicitly
  handed; absence is not represented here at all;
- this remains a pure, zero-HTTP-call transaction primitive with no
  checkpoint or scheduler interaction of any kind.

--------------------------------------------------------------------------
2026-08-17 account-default unit-request-mode audit gate (current)
--------------------------------------------------------------------------
This transaction gained an additive, optional ``unit_request_mode``
parameter (see ``app.motive.vehicle_utilization_unit_policy``). When omitted
(``None``, the default), behavior is byte-for-byte identical to before this
gate: the canonical metric policy is enforced and every persisted row's
``metric_units`` is the certified ``True``. When a caller explicitly passes
``MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT``, no unit system
was forced on the request, so the writer no longer requires the returned
indicator to equal a fixed Boolean -- both ``True`` and ``False`` are ready,
and whichever Boolean the provider actually returned is what gets durably
persisted on the row (never a hardcoded ``True``, never a silent
conversion). A missing or malformed returned indicator still fails closed
exactly as before, for every mode.

2026-08-17 controlled-route validation gate (current): the bounded controlled
vehicle-utilization write validation route
(``app/motive/vehicle_utilization_controlled_write.py``) now explicitly passes
``unit_request_mode=MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT``
into this transaction, so a returned rollup with ``metric_units=True`` OR
``metric_units=False`` can both persist for that route; a missing or
malformed indicator still fails closed exactly as before. This is still NOT a
live proof of account-default behavior for this endpoint -- the controlled
write route's feature flag remains disabled by default and no live provider
call has been made under this change.
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
from app.motive.vehicle_utilization_unit_policy import (
    MotiveVehicleUtilizationUnitRequestMode,
    validate_vehicle_utilization_unit_persistence_readiness,
)

logger = logging.getLogger(__name__)

# The only certified provenance a durable row may carry in this gate. A
# manually-constructed/incompatible rollup claiming another parser version or
# source endpoint fails closed rather than being accepted.
CERTIFIED_PARSER_VERSION = PARSER_VERSION
CERTIFIED_SOURCE_ENDPOINT = MOTIVE_VEHICLE_UTILIZATION_ENDPOINT

# ---------------------------------------------------------------------------
# 2026-08-17 historical-rollup reconciliation gate: the ONLY persisted
# columns a reread may update in place for an existing, context-compatible
# durable identity. Every other column (identity, request-window, unit
# indicator, provenance) is IMMUTABLE -- see
# docs/engineering/MOTIVE_UTILIZATION_HISTORICAL_RECONCILIATION.md for the
# complete field-by-field audit and classification of every persisted
# column on MotiveVehicleUtilizationRecord.
# ---------------------------------------------------------------------------
MUTABLE_ON_PROVIDER_RECONCILIATION: frozenset[str] = frozenset(
    {
        "utilization_percent",
        "idle_time",
        "driving_time",
        "idle_fuel",
        "driving_fuel",
    }
)

# Reserved for a genuine "found the right row, but an incoming difference is
# not in the approved mutable set" conflict -- distinct from
# ``conflicting_existing_identity`` (identity/context itself disagrees). With
# the current schema and parser, every non-approved field is already an
# identity/context field enforced by ``_existing_row_context_compatible``
# before reconciliation is even considered, so this code is currently
# unreachable through real provider data; it exists as a defensive guard
# (see ``_compute_mutable_field_changes``) against ever silently applying an
# unapproved field difference if the schema grows in the future.
RECONCILIATION_CONFLICT_ERROR_CODE = "provider_rollup_reconciliation_conflict"


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

    ``records_updated`` counts rows reconciled in place (see the
    2026-08-17 historical-rollup reconciliation gate module docstring): an
    existing, context-compatible row whose approved mutable field(s)
    differed from the incoming validated rollup. ``reconciled_fields_count``
    additionally sums how many individual approved fields were changed
    across all reconciled rows in the batch, for auditability without
    storing raw provider values.
    """

    committed: bool
    requested_vehicle_count: int
    returned_rollup_count: int
    records_inserted: int
    records_unchanged: int
    records_updated: int
    missing_requested_vehicle_count: int
    reconciled_fields_count: int = 0


@dataclass(frozen=True, slots=True)
class _WritePlan:
    rows_to_insert: list[MotiveVehicleUtilizationRecord]
    rows_to_reconcile: list[tuple[MotiveVehicleUtilizationRecord, dict[str, Decimal | None]]]
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
    unit_request_mode: MotiveVehicleUtilizationUnitRequestMode | None = None,
) -> VehicleUtilizationWriteResult:
    """Persist validated, already-parsed vehicle-utilization rollups.

    ALL OR NOTHING: the entire incoming batch is validated before any row is
    staged. This function owns exactly one commit and rolls back the whole
    transaction on any failure. It never mutates ``MotiveSyncCheckpoint`` or
    ``MotiveSyncHistory``.

    ``unit_request_mode`` defaults to ``None``, reproducing the exact
    pre-account-default-gate canonical-metric-only behavior. Pass
    ``MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT`` to persist
    rollups read without an ``X-Metric-Units`` header -- see the module
    docstring's 2026-08-17 account-default gate section.
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

        # 6. Canonical unit context (fail closed on False/None/unknown), or
        # -- when the caller explicitly opted into ACCOUNT_DEFAULT -- the
        # account-default readiness rule (fail closed only on None/unknown).
        for rollup in rollups_list:
            _validate_unit_context(rollup, unit_request_mode=unit_request_mode)

        # 7. Certified parser/source provenance only.
        for rollup in rollups_list:
            _validate_parser_and_source(rollup)

        # 8. Resolve tenant-owned MotiveVehicleRecord associations.
        vehicle_by_provider_id = _resolve_tenant_vehicles(
            session,
            organization_id=organization_id,
            provider_vehicle_ids=[rollup.provider_vehicle_id for rollup in rollups_list],
        )

        # 9/10. Inspect existing durable identities; decide insert / unchanged
        # / reconcile / conflict for the WHOLE batch before mutating
        # anything. Any conflict raises here, before any row is staged or any
        # existing row's attributes are touched -- see
        # _plan_writes/_existing_row_context_compatible/
        # _compute_mutable_field_changes below.
        plan = _plan_writes(
            session,
            organization_id=organization_id,
            organization_slug=organization_slug,
            rollups=rollups_list,
            vehicle_by_provider_id=vehicle_by_provider_id,
        )

        # 11. Only now -- once the ENTIRE batch is known to be safe -- stage
        # new rows and apply approved, field-by-field reconciliation changes
        # to existing rows. Never a blind ORM merge: only the specific
        # differing fields already identified as approved-mutable are set.
        for row in plan.rows_to_insert:
            session.add(row)
        reconciled_fields_count = 0
        for existing_row, changes in plan.rows_to_reconcile:
            for field_name, new_value in changes.items():
                setattr(existing_row, field_name, new_value)
            reconciled_fields_count += len(changes)

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
        records_updated=len(plan.rows_to_reconcile),
        missing_requested_vehicle_count=missing_requested_vehicle_count,
        reconciled_fields_count=reconciled_fields_count,
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
            "records_updated": result.records_updated,
            "reconciled_fields_count": result.reconciled_fields_count,
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
# Step 6 -- durable unit-context persistence readiness.
#
# This is deliberately NOT the same question as "did the parser accept this
# rollup" (see app.connectors.motive_vehicle_utilization). Motive API
# Support's 2026-08-17 written reply confirmed the returned
# vehicle.metric_units Boolean's meaning (true=metric, false=imperial) and
# directed integrations to fail closed whenever the requested and returned
# unit context disagree (see vehicle_utilization_unit_policy.py and
# docs/engineering/MOTIVE_UTILIZATION_UNIT_SEMANTICS_CERTIFICATION.md). The
# canonical writer always requests X-Metric-Units=true, so this call relies
# on validate_vehicle_utilization_unit_persistence_readiness's default
# requested_metric_units (the certified canonical policy): a returned True
# is now ready for durable persistence; a returned False is a
# provider-confirmed mismatch and fails closed; a missing or malformed
# returned value fails closed with its own distinct code.
# ---------------------------------------------------------------------------
def _validate_unit_context(
    rollup: MotiveVehicleUtilizationRollup,
    *,
    unit_request_mode: MotiveVehicleUtilizationUnitRequestMode | None = None,
) -> None:
    if unit_request_mode is None:
        # Exact pre-account-default-gate call shape: a single positional
        # argument, so tests/monkeypatches written against the old signature
        # keep working unmodified.
        readiness = validate_vehicle_utilization_unit_persistence_readiness(rollup.metric_units)
    else:
        readiness = validate_vehicle_utilization_unit_persistence_readiness(
            rollup.metric_units, requested_mode=unit_request_mode
        )
    if not readiness.ready_for_durable_persistence:
        raise MotiveVehicleUtilizationWriterError(
            readiness.error_code or "provider_unit_indicator_semantics_unresolved",
            "Vehicle utilization writer rollup did not carry a certified durable unit context.",
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
# Steps 9/10 -- idempotent replay + historical-rollup reconciliation policy
# against existing durable identities.
#
# For every returned rollup with an existing durable row on the certified
# identity key, this decides -- WITHOUT mutating anything yet -- exactly one
# of:
#   - CASE 2 (unchanged): the existing row is context-compatible and every
#     approved mutable field already matches -- no-op, no timestamp touch;
#   - CASE 3 (reconcile): the existing row is context-compatible but one or
#     more approved mutable fields differ -- a controlled, field-by-field
#     change set is computed (never a blind overwrite) for the caller to
#     apply only after the ENTIRE batch is known to be safe;
#   - CASE 4 (conflict): the existing row is NOT context-compatible (its
#     identity/provenance/unit context disagrees), or an unapproved field
#     differs -- fail closed, whole batch rolls back, existing row untouched.
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
        return _WritePlan(rows_to_insert=[], rows_to_reconcile=[], unchanged_count=0)

    identity_keys = {
        (vehicle_by_provider_id[rollup.provider_vehicle_id], rollup.request_start_date, rollup.request_end_date)
        for rollup in rollups
    }
    existing_by_key = _load_existing_identity_rows(session, organization_id=organization_id, identity_keys=identity_keys)

    rows_to_insert: list[MotiveVehicleUtilizationRecord] = []
    rows_to_reconcile: list[tuple[MotiveVehicleUtilizationRecord, dict[str, Decimal | None]]] = []
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
        if not _existing_row_context_compatible(existing, rollup):
            # Identity/provenance/unit-context disagreement (CASE 4). The
            # existing row lacks evidence it was created under the certified
            # writer contract, or a durable identity/context field
            # (provider_vehicle_id, request window, source_endpoint,
            # parser_version, metric_units) disagrees. Never reconciled --
            # fail closed instead of silently accepting or partially
            # applying anything.
            raise MotiveVehicleUtilizationWriterError(
                "conflicting_existing_identity",
                "An existing durable vehicle-utilization row conflicts with this replay.",
            )
        changes = _compute_mutable_field_changes(existing, rollup)
        if not changes:
            # CASE 2: context-compatible and every approved mutable field
            # already matches -- true no-op. Never touch timestamps merely
            # to record replay activity.
            unchanged_count += 1
            continue
        # CASE 3: context-compatible, and only approved mutable
        # provider-derived fields differ. Stage the controlled change set;
        # it is applied only after the caller confirms the whole batch is
        # safe.
        rows_to_reconcile.append((existing, changes))

    return _WritePlan(rows_to_insert=rows_to_insert, rows_to_reconcile=rows_to_reconcile, unchanged_count=unchanged_count)


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


def _existing_row_context_compatible(
    existing: MotiveVehicleUtilizationRecord, rollup: MotiveVehicleUtilizationRollup
) -> bool:
    """Is the existing row's IMMUTABLE identity/context/provenance state
    compatible with the incoming, already-validated rollup?

    This is the single gate for CASE 4 (identity/context conflict, section 4
    of the reconciliation policy): ``True`` only when the existing row
    carries evidence it was created under the certified writer contract
    (a well-formed ``metric_units`` Boolean that agrees with the incoming,
    already-validated rollup's own ``metric_units`` -- see the 2026-08-17
    account-default gate note below, certified ``source_endpoint``, certified
    ``parser_version``) AND its durable identity fields
    (``provider_vehicle_id``, ``request_window_start``,
    ``request_window_end``) agree with the incoming rollup. This function
    NEVER inspects the five provider-derived rollup metrics -- those are
    compared separately by :func:`_compute_mutable_field_changes` only after
    context compatibility is established, and only they may ever change on
    reconciliation.

    Mutable, non-identity metadata such as ``organization_slug`` is
    deliberately not compared here, since it may change without changing the
    durable identity.

    2026-08-17 account-default unit-request-mode audit gate: prior to this
    gate every persisted row's ``metric_units`` was always ``True`` (the
    canonical-only writer), so comparing the existing row's ``metric_units``
    against the fixed literal ``True`` was equivalent to comparing it against
    the incoming rollup's own (always-``True``) ``metric_units``. Now that
    ``ACCOUNT_DEFAULT`` rows may legitimately be persisted with
    ``metric_units=False``, this compares against the incoming rollup's
    ``metric_units`` directly -- identical behavior for every existing
    canonical-only caller (both sides are always ``True`` there), and correct
    for account-default replays of either unit context.
    """
    if existing.metric_units is not rollup.metric_units:
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
    return True


def _compute_mutable_field_changes(
    existing: MotiveVehicleUtilizationRecord, rollup: MotiveVehicleUtilizationRollup
) -> dict[str, Decimal | None]:
    """Compute the controlled, field-by-field reconciliation change set.

    Only called once :func:`_existing_row_context_compatible` has already
    confirmed the existing row's identity/context/provenance agrees with the
    incoming rollup. Compares each of the five approved provider-derived
    metrics (:data:`MUTABLE_ON_PROVIDER_RECONCILIATION`) using Decimal-safe
    (never float, never tolerance-based) equality, and returns a dict of
    only the fields that actually differ, mapped to the new (incoming)
    value. An empty dict means CASE 2 (identical replay, true no-op).

    This is never a blind ORM ``merge()``: the caller applies exactly these
    fields via explicit ``setattr`` calls, nothing else. As a defensive
    guard against ever silently applying an unapproved field difference (see
    :data:`RECONCILIATION_CONFLICT_ERROR_CODE`), this raises if a compared
    field name is not present in :data:`MUTABLE_ON_PROVIDER_RECONCILIATION`
    -- unreachable with the current fixed candidate list below, but kept as
    a real, testable safety net rather than only a comment.
    """
    candidate_fields: dict[str, Decimal | None] = {
        "utilization_percent": rollup.utilization_percent,
        "idle_time": rollup.idle_time,
        "driving_time": rollup.driving_time,
        "idle_fuel": rollup.idle_fuel,
        "driving_fuel": rollup.driving_fuel,
    }
    changes: dict[str, Decimal | None] = {}
    for field_name, incoming_value in candidate_fields.items():
        existing_value = getattr(existing, field_name)
        if not _decimal_differs(existing_value, incoming_value):
            continue
        if field_name not in MUTABLE_ON_PROVIDER_RECONCILIATION:
            raise MotiveVehicleUtilizationWriterError(
                RECONCILIATION_CONFLICT_ERROR_CODE,
                "A returned vehicle-utilization rollup differed in a field that is not approved for reconciliation.",
            )
        changes[field_name] = incoming_value
    return changes


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
    """Minimal, certified-only persistence. No inference, no raw payload.

    ``metric_units`` persists the rollup's own (already durable-persistence-
    validated by ``_validate_unit_context`` before this is ever called)
    returned value rather than a hardcoded ``True``. For every canonical
    (non-account-default) caller this is always ``True`` -- validation would
    already have failed closed on anything else -- so this is a no-behavior-
    change for existing callers. It is what makes ACCOUNT_DEFAULT rollups
    persist their actual observed unit context (``True`` or ``False``)
    instead of a silently-wrong hardcoded value.
    """
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
        metric_units=rollup.metric_units,
        distance=None,
        engine_hours=None,
        observed_at=None,
        parser_version=CERTIFIED_PARSER_VERSION,
        provider_payload_metadata={},
    )
