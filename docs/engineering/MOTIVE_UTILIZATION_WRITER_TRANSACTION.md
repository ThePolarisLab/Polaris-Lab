# Motive Vehicle Utilization Writer Transaction

This gate adds the **internal, all-or-nothing database writer transaction
primitive** for validated Motive vehicle-utilization rollups. It is a scoped
transaction-primitive gate, not the production-enablement PR.

It does **not** enable a runtime provider-to-database sync. It does **not**
create `POST /api/v1/motive/sync/vehicle-utilization` or any other public
write route, make any live Motive provider call, enable checkpoint
advancement, write `MotiveSyncCheckpoint` or `MotiveSyncHistory`, enable the
scheduler, enable broad Motive sync, change pagination provider semantics,
change the canonical metric-unit policy, add unit conversion, add imperial
durable rows, or add a migration (database uniqueness is already merged — see
`MOTIVE_UTILIZATION_DATABASE_IDENTITY.md`).

## What This Gate Adds

`chief-of-staff/backend/app/motive/vehicle_utilization_writer.py`:

```python
def write_vehicle_utilization_transaction(
    session: Session,
    *,
    organization_id: str,
    organization_slug: str,
    selected_provider_vehicle_ids: Sequence[str],
    request_window_start: date,
    request_window_end: date,
    rollups: Sequence[MotiveVehicleUtilizationRollup],
) -> VehicleUtilizationWriteResult
```

This function:

- makes **zero** Motive HTTP calls;
- receives already-parsed, already-validated rollups (for example, the
  output of `read_vehicle_utilization_pages` in
  `motive_vehicle_utilization_pagination.py`);
- performs tenant-safe DB association against existing `MotiveVehicleRecord`
  rows only — it **never auto-creates a vehicle**;
- re-validates every writer precondition defensively, for the **entire
  batch**, before staging a single row;
- persists only provider-returned rollups;
- owns **exactly one commit** for the whole batch and **rolls back the
  entire transaction** on any failure;
- does **not** touch `MotiveSyncCheckpoint` or `MotiveSyncHistory`;
- never exposes provider vehicle IDs, VIN, unit numbers, or metric values in
  its result type, its errors, or its logging.

There is no caller anywhere in this PR. It is the primitive a later,
separately-authorized manual production validation route may call.

## Transaction Contract (All-Or-Nothing)

Validation order, conceptually:

1. validate caller/request context (`organization_id`, `organization_slug`
   non-empty; `request_window_start`/`request_window_end` are explicit
   `date` values with `start <= end`; `selected_provider_vehicle_ids`
   non-empty, no duplicates, no empty entries);
2. validate the selected vehicle set structure;
3. validate every rollup structurally, then its organization context
   (`rollup.organization_id`/`organization_slug` must match the caller),
   then its request window (`rollup.request_start_date`/`request_end_date`
   must both be present and exactly equal the caller's window) — for the
   **whole batch** before proceeding;
4. fail closed on any duplicate returned `provider_vehicle_id` within the
   incoming batch (no deduplication, no last-write-wins);
5. fail closed on any returned vehicle outside the selected set;
6. validate the canonical unit policy
   (`validate_vehicle_utilization_writer_metric_units`) — `True` accepted,
   `False`/`None`/unknown fail closed;
7. validate certified parser/source provenance — only
   `motive_vehicle_idle_rollup_v1` from `/v1/vehicle_utilization` is
   accepted; anything else fails closed;
8. resolve tenant-owned `MotiveVehicleRecord` associations for every
   returned vehicle, scoped to the authenticated `organization_id` — a
   vehicle that does not resolve (unknown, or belongs to another
   organization) fails the **whole batch** closed;
9. inspect existing durable identities for the certified key
   (`organization_id + motive_vehicle_id + request_window_start +
   request_window_end`);
10. fail closed on any conflicting replay;
11. only then stage new rows;
12. flush;
13. commit once;
14. return sanitized counts.

On **any** failure at any step: `session.rollback()`. No partial durable
writes, no checkpoint write, no sync-history write, no retry.

## Result Type

`VehicleUtilizationWriteResult` (frozen dataclass) carries only sanitized
counts:

```
committed, requested_vehicle_count, returned_rollup_count,
records_inserted, records_unchanged, records_updated,
missing_requested_vehicle_count
```

`records_updated` is **always `0`** in this gate — updates to an existing
row are not enabled (see Replay Policy below). The result never carries
provider vehicle IDs, VIN, unit numbers, metric values, raw row values, or
raw payload contents.

## Error Type

`MotiveVehicleUtilizationWriterError(code, message)` — a safe domain
exception. `str(error)` never includes provider IDs, metrics, VINs, unit
numbers, secrets, or payload contents. Codes used in this gate:

- `invalid_writer_request` — malformed request/selected-vehicle-set shape
  (empty/duplicate/blank IDs, missing selected set, malformed rollup)
- `organization_context_mismatch` — a rollup's organization context doesn't
  match the caller
- `request_window_missing` — a rollup is missing its explicit request
  window
- `request_window_invalid` — caller window invalid (`start > end`), or a
  rollup's window doesn't match the caller's window
- `duplicate_returned_rollup` — more than one rollup for the same vehicle in
  the batch
- `unexpected_returned_vehicle` — a returned vehicle wasn't in the selected
  set
- `unknown_vehicle` — a returned vehicle doesn't resolve to exactly one
  tenant-owned `MotiveVehicleRecord` for the caller's organization (this
  also covers cross-tenant vehicles, which are treated as unknown for the
  caller)
- `provider_unit_policy_mismatch` / `provider_unit_context_missing` /
  `provider_unit_context_invalid_type` — from
  `validate_vehicle_utilization_writer_metric_units`
- `parser_version_not_certified` / `source_endpoint_not_certified` —
  uncertified provenance
- `conflicting_existing_identity` — an existing row on the certified
  identity key conflicts with the incoming replay (or lacks evidence it was
  created under the certified writer contract)
- `database_identity_conflict` — the database unique constraint
  (`uq_motive_vehicle_util_org_vehicle_request_window`) fired as the final
  concurrency guard despite the application-level preflight
- `database_persistence_error` — any other SQLAlchemy persistence failure

## Idempotent Replay Policy

Database identity: `organization_id + motive_vehicle_id +
request_window_start + request_window_end`.

- **No existing row** → INSERT.
- **Existing row, identical certified result** → NO-OP / UNCHANGED
  (`records_unchanged` increments; `records_inserted` does not).
- **Existing row, conflicting certified result** → FAIL CLOSED
  (`conflicting_existing_identity`); the existing row is left completely
  unchanged, no second row is created, and the whole transaction rolls back.

**Updates are disabled in this gate.** There is no last-write-wins, no
metric overwrite, no silent correction. A later explicit
correction/versioning policy can be designed separately if Motive
demonstrates mutable completed rollups.

### Same-Result Replay Equivalence (Exact Rule)

An existing row is treated as an identical replay **only when both** of the
following hold:

1. The existing row carries evidence it was created under the certified
   writer contract: `metric_units is True`, `source_endpoint` equals the
   certified `/v1/vehicle_utilization`, and `parser_version` equals the
   certified `motive_vehicle_idle_rollup_v1`. If the existing row lacks this
   evidence (for example a legacy/incompatible row happens to share the
   identity key), the replay is **not** treated as identical — it fails
   closed as a conflict instead of being silently accepted.
2. Every writer-owned measurement/provenance field matches the incoming
   rollup exactly, using **Decimal-safe** (never float) comparison with no
   tolerance: `provider_vehicle_id`, `request_window_start`,
   `request_window_end`, `utilization_percent`, `idle_time`,
   `driving_time`, `idle_fuel`, `driving_fuel`.

`organization_slug` is deliberately **not** part of the equivalence check —
it is mutable organization metadata and may change without changing the
durable identity, so a slug change alone must never create a spurious
conflict.

## Durable Row Content

For each validated, newly-inserted rollup, the writer persists only:

```
organization_id, organization_slug, provider = "motive", provider_vehicle_id,
motive_vehicle_id, source_endpoint, request_window_start, request_window_end,
utilization_percent, idle_time, driving_time, idle_fuel, driving_fuel,
metric_units = True, parser_version
```

It leaves `reporting_period_start`/`reporting_period_end` as `NULL`
(deferred — see `MOTIVE_UTILIZATION_DATABASE_IDENTITY.md`), `observed_at` as
`NULL` (no invented Motive observation timestamp), `distance` and
`engine_hours` as `NULL` (never inferred), and `provider_payload_metadata`
as an empty dict (no raw Motive payload is stored).

## Missing Requested Vehicles

A requested/selected vehicle not returned by Motive creates **no** durable
row. It is counted only via the sanitized
`missing_requested_vehicle_count`. It is never persisted as zero metrics,
"inactive," "no activity," or a placeholder/absence row — classification
remains `provider_rollup_absent`, unchanged from the writer-contract gate.

## Zero-Result Transactions

A completed provider read may legitimately return zero rollups. The writer
succeeds with `records_inserted = 0`, `records_unchanged = 0`,
`records_updated = 0`, and `missing_requested_vehicle_count` equal to the
selected vehicle count. No synthetic rows are created and no error is
raised merely because every selected vehicle was absent.

## Database Uniqueness As Final Guard

Even after application-level preflight, the database constraint
`uq_motive_vehicle_util_org_vehicle_request_window` remains the final
concurrency guard. If flush/commit raises `IntegrityError` for the certified
identity, the writer rolls back the entire transaction and raises the
sanitized `database_identity_conflict` domain error — never the raw
SQLAlchemy/SQL error text, and never an automatic retry. The
application-level preflight (same-result / conflicting-result comparison)
is not removed in favor of this guard; both layers are enforced.

## No Checkpoint, No History, No Public Route

Unlike the existing `/sync/vehicles` and `/sync/users` runtime paths, this
writer transaction never calls `_resource_checkpoint`,
`_ensure_resource_checkpoint`, `_mark_checkpoint_success`,
`_create_running_history`, or `_mark_history_success`, and never mutates
`MotiveSyncCheckpoint` or `MotiveSyncHistory`. Those remain later,
separately-authorized gates. There is still no
`POST /api/v1/motive/sync/vehicle-utilization` or equivalent route; the only
public utilization-writer-related endpoint remains the read-only
`GET /api/v1/motive/fleet/vehicle-utilization-writer-contract` status route,
unchanged and still making zero provider calls and zero utilization writes.

## Writer Contract Status Update

`app/motive/vehicle_utilization_writer_contract.py` now reports
(alongside the unchanged `writer_enabled = false`,
`persistence_enabled = false`, `checkpoint_advancement_enabled = false`,
`scheduled_ingestion_enabled = false`, `broad_sync_enabled = false`):

```
writer_transaction_implemented: true
database_enforced: true
runtime_writer_enabled: false
public_manual_write_route_enabled: false
provider_to_database_runtime_enabled: false
writer_transaction:
  implemented: true
  internal_only: true
  module: "app.motive.vehicle_utilization_writer"
  function: "write_vehicle_utilization_transaction"
  commits_once: true
  all_or_nothing: true
  conflicting_replay_policy: "fail_closed"
  identical_replay_policy: "unchanged"
  update_existing_row_enabled: false
  zero_result_supported: true
  provider_calls: 0
  checkpoint_writes: 0
  sync_history_writes: 0
  public_route_enabled: false
```

`remaining_blockers` no longer lists "utilization writer transaction
implementation remains disabled." It now lists:

1. controlled/manual provider-to-database write validation remains disabled
   and requires separate authorization
2. checkpoint advancement implementation remains disabled
3. exact company-configured Motive rollup timezone must be confirmed before
   scheduled daily ingestion

## Tests

`tests/test_motive_vehicle_utilization_writer_transaction.py` proves,
against a synthetic (never live) SQLite database:

- successful single-row and multi-row atomic inserts, with exact persisted
  field values and `reporting_period_*`/`observed_at`/`distance`/
  `engine_hours` all `None`, and zero checkpoint/history rows created;
- the writer commits exactly once per successful call;
- identical replay is a no-op (`records_unchanged` increments, no second
  row, no `IntegrityError` surfaced);
- conflicting replay fails closed across multiple dimensions (metric value
  change, incompatible existing unit context, incompatible existing
  source/parser provenance) with the existing row left completely
  unchanged;
- unknown vehicle, cross-tenant vehicle, and unexpected (non-selected)
  vehicle all fail closed with zero rows written and no leaked provider ID;
- duplicate returned rollups fail closed with no deduplication;
- unit policy: `True` accepted, `False`/`None` fail closed;
- request-window validation: missing rollup start/end, mismatched rollup
  window, and `caller start > end` all fail before any write;
- uncertified parser version / source endpoint fail closed;
- a zero-rollup batch succeeds as a no-op with the full selected count
  reported as missing;
- whole-batch rollback: a batch with one valid rollup and one rollup that
  fails late (unknown vehicle at the tenant-resolution step, or a
  conflicting replay at the identity-check step) commits **zero** rows,
  including the otherwise-valid one;
- the database uniqueness constraint as final guard: with the
  application-level preflight helper monkeypatched to simulate a race
  window (so it reports no existing row even though one was already
  committed), the real `IntegrityError` is caught and translated into the
  sanitized `database_identity_conflict` error, the transaction rolls back,
  and the pre-existing row count stays at `1`;
- synthetic unsafe payloads (deliberately unsafe-looking provider vehicle
  IDs and metric values) never appear in raised error messages, the result
  object's representation, or sanitized log records.

`tests/test_motive_vehicle_utilization_writer_contract.py` was updated to
assert the new `writer_transaction_implemented`, `database_enforced`,
`runtime_writer_enabled`, `public_manual_write_route_enabled`,
`provider_to_database_runtime_enabled`, and `writer_transaction` fields, and
the updated `remaining_blockers` content.

## No Live Provider Calls

This gate makes zero Motive provider calls. It is a pure internal
transaction-primitive gate operating only on already-parsed, in-memory
rollup values and a synthetic test database.

## Update: Controlled Write Validation Gate

A subsequent gate (`MOTIVE_UTILIZATION_CONTROLLED_WRITE_VALIDATION.md`) adds
the first — and, deliberately, only — caller of
`write_vehicle_utilization_transaction`: the feature-flagged (default
disabled) `POST /api/v1/motive/verify/vehicle-utilization-write` route. That
gate reuses this transaction **unchanged** for one fixed historical day
(`2026-08-13`), with at most one Motive provider call per invocation. It does
not modify anything documented above; see that document for the full
controlled-route contract.

## Update: Unit-Context Reconciliation Gate (2026-08-16)

A real controlled production execution of the route above failed safely:
Motive returned one rollup whose `vehicle.metric_units` did not equal the
requested `True`. See `MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md` for the
full sanitized evidence.

Step 6 of the transaction contract above ("validate the canonical unit
policy ... `True` accepted, `False`/`None`/unknown fail closed") is now:

> validate durable unit-context **persistence readiness**
> (`validate_vehicle_utilization_unit_persistence_readiness` in
> `vehicle_utilization_unit_policy.py`) — until Motive's returned
> `vehicle.metric_units` Boolean semantics are explicitly certified,
> **every** returned value fails closed, `True` included, with the neutral
> code `provider_unit_indicator_semantics_unresolved`. A malformed
> (non-Boolean, non-`None`) value fails closed separately with
> `provider_unit_context_invalid_type`.

This means `write_vehicle_utilization_transaction` currently rejects every
incoming rollup at step 6 regardless of its `metric_units` value — this is
intentional hardening, not a defect: no fuel-bearing rollup may be durably
persisted while the returned unit-indicator semantics remain unresolved.
The transaction's other validation steps (batching, tenancy, replay,
provenance) are otherwise unchanged; `tests/test_motive_vehicle_utilization_writer_transaction.py`
exercises them in isolation from the unit-readiness gate via an explicit,
marker-controlled bypass fixture, and separately proves the real
fail-closed unit-readiness behavior for `True`, `False`, `None`, and
malformed returned values.

The error-code list above is superseded for the unit-context codes:
`provider_unit_policy_mismatch` / `provider_unit_context_missing` are
retired from new writer output (they remain in the sanitized, static,
already-executed production evidence record only — see
`PRODUCTION_WRITE_VALIDATION_EVIDENCE` in
`vehicle_utilization_writer_contract.py`) in favor of the single neutral
`provider_unit_indicator_semantics_unresolved` code plus
`provider_unit_context_invalid_type` for malformed values.

The replay/mutability contract classification also changes: conflicting
historical values are no longer classified as inherently invalid, because
Motive has confirmed completed rollups may later differ slightly. The
**runtime** replay behavior documented above (identical → unchanged,
conflicting → fail closed, updates disabled) is unchanged in this gate; only
the contract classification is now
`TEMPORARY_FAIL_CLOSED_PENDING_RECONCILIATION_POLICY`
(`historical_rollup_mutability` in `vehicle_utilization_writer_contract.py`).
A future, separately-authorized gate must design controlled historical
refresh/upsert semantics before broad scheduled ingestion; this gate adds no
version table, no audit-history schema, and changes no existing durable row.

See `MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md` for the full reconciliation.

## Update: Unit Semantics Certification Gate (2026-08-16)

A follow-up documentation-review gate (see
`MOTIVE_UTILIZATION_UNIT_SEMANTICS_CERTIFICATION.md`) found no official
Motive documentation statement reconciling `X-Metric-Units` with the
returned `vehicle.metric_units` field for this endpoint. **No behavior
change** to this module or its transaction contract: step 6 above still
fails closed on every returned value, `True` included, via
`validate_vehicle_utilization_unit_persistence_readiness`. The writer
contract's status output (`vehicle_utilization_writer_contract.py`) gains an
additive `unit_semantics` block that names the request-vs-response
distinction explicitly; the existing `unit_policy` block, and every field
inside it, is unchanged.
