# Motive Vehicle Utilization Controlled Write Validation

This gate adds a **tightly bounded, explicitly controlled production write
validation route** that connects the certified Motive pagination reader to
the certified parser/unit validation and the merged all-or-nothing
utilization writer transaction, for **one fixed, previously-observed
historical completed day**.

It is **not** broad vehicle-utilization ingestion, **not** scheduled sync,
and **not** checkpoint implementation. Its only purpose is to prove, in
production, that the certified provider read and the certified durable
writer transaction work together safely — under an explicit kill switch that
defaults to disabled, with at most one Motive provider call ever attempted
per invocation.

It does **not** create `POST /api/v1/motive/sync/vehicle-utilization` or any
other general-purpose route, does **not** enable the scheduler, does **not**
add automatic date progression, does **not** write `MotiveSyncCheckpoint` or
`MotiveSyncHistory`, and does **not** add a database migration (the
`uq_motive_vehicle_util_org_vehicle_request_window` constraint this gate
relies on was already added by the database-identity gate; see
`MOTIVE_UTILIZATION_DATABASE_IDENTITY.md`).

## What This Gate Adds

`chief-of-staff/backend/app/motive/vehicle_utilization_controlled_write.py`:

- `controlled_write_enabled() -> bool` — strict boolean read of the kill
  switch environment variable
  `MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED`. Unset, empty, or any
  value other than `1`/`true`/`yes`/`on` (case-insensitive) is treated as
  **disabled**. There is no code path that enables this flag implicitly, in
  test defaults, or in development defaults.
- `run_controlled_vehicle_utilization_write(session, *, organization_id,
  organization_slug, selected_provider_vehicle_ids, http_client=None) ->
  dict` — the read-to-write orchestration for the fixed window. Callers
  (the public route) must already have authenticated the caller with
  `CONNECTOR_WRITE`, verified `controlled_write_enabled()`, verified explicit
  execution confirmation, loaded the authenticated organization, and selected
  up to three deterministic stored organization vehicles before calling this
  function.
- a narrow, **one-page-only** controlled provider reader
  (`_execute_one_page_controlled_read`) that reuses the certified page
  request primitive (`request_vehicle_utilization_page`) and the certified
  pagination-metadata parser (`parse_pagination_metadata`) from
  `motive_vehicle_utilization_pagination.py`, plus the certified rollup
  parser (`parse_vehicle_utilization_rollups`) and canonical unit-policy
  validator. It does **not** call, weaken, or modify the general certified
  paginated reader (`read_vehicle_utilization_pages`) — it never fetches a
  second page, even if pagination metadata looks malformed; it fails closed
  instead.

`chief-of-staff/backend/app/api/motive.py`:

- `POST /api/v1/motive/verify/vehicle-utilization-write` —
  `Permission.CONNECTOR_WRITE`, authenticated organization only. This is the
  only write-capable Motive vehicle-utilization route in the repository. Its
  name deliberately signals controlled validation, not normal sync.

## Safety Enable Switch

`MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED` — **default `false`**.
Parsed with the same strict-boolean convention used elsewhere in this
backend (`app/database/schema_guard.py`): only `1`, `true`, `yes`, or `on`
(case-insensitive, surrounding whitespace stripped) enable it. When disabled,
the route makes **zero** Motive calls, **zero** utilization writes, **zero**
checkpoint changes, and **zero** sync-history writes, and returns a sanitized
`503` disabled response before touching the database or the network.

## Execution Confirmation

The request body requires an explicit `{"confirm": true}`. Missing or
`false` confirmation is rejected with a sanitized `400` before any provider
call, org lookup, or vehicle selection. The request body accepts **no other
fields** — no dates, vehicle IDs, page size, `metric_units`, or
`organization_id` may be supplied by the caller. The authenticated tenant and
certified constants control all of those.

## Fixed Controlled Production Window

For this validation gate only: `start_date = end_date = 2026-08-13`. This is
the same fixed historical single-day window already used in the prior
bounded read-only production evidence (`MOTIVE_UTILIZATION_BOUNDED_EVIDENCE.md`).
The window is a module-level constant; it is never computed at runtime, never
inferred from a company timezone, and never accepted from the caller. This
route cannot become an accidental general-purpose utilization sync — a
different, separately-authorized gate would be required to accept an
arbitrary window.

## Controlled Vehicle Set

Reuses the existing deterministic utilization vehicle-selection behavior
(`_vehicles_for_utilization_contract` in `app/api/motive.py`):
organization-owned `MotiveVehicleRecord` rows, ordered by internal
`MotiveVehicleRecord.id` ascending, limited to
`MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES` (currently `3`). Provider
vehicle IDs are never accepted from the HTTP caller. If zero stored Motive
vehicles exist for the organization, the route fails safely (`404`) before
any provider call.

## One-Page, One-Call Contract

At most **one** Motive provider request is attempted per invocation:
`per_page = 100` (the canonical writer page size), `page_no = 1`, for the
fixed window above. **Superseded 2026-08-17 (see "Update: Controlled-Route
Account-Default Validation Gate" below):** this route now requests
`unit_request_mode = ACCOUNT_DEFAULT`, so `X-Metric-Units` is omitted
entirely — it no longer sends `X-Metric-Units: true`. Because the selected
vehicle set is capped at three, one legitimate Motive rollup per selected
vehicle fits entirely in one page — there is never a legitimate reason for
this bounded validation to need page 2.

Strict, fail-closed validation before any write is attempted:

- pagination metadata must be present and well-formed (`page_no`, `per_page`,
  `total` all present, `int`, not `bool`);
- `page_no` must equal `1`, `per_page` must equal `100`;
- `pagination.total` must not exceed the selected vehicle count (at most 3);
- the returned, certified-parser-validated item count must equal
  `pagination.total`;
- no duplicate returned vehicle;
- no vehicle outside the selected set.

> **2026-08-16 update:** the read stage no longer performs its own
> returned-`metric_units` check here (see "Update: Unit-Context
> Reconciliation Gate" below) — that is now the writer transaction's
> persistence-readiness gate, which fails closed on every returned value
> (`True` included) until Motive's semantics are explicitly certified.

Any violation fails the whole invocation closed with **zero** durable writes,
**zero** checkpoint writes, and **zero** sync-history writes. No page 2 is
ever fetched. No automatic retry is ever attempted.

## Write Behavior

Validated rollups that pass every check above are handed unchanged to the
existing merged writer transaction
(`app.motive.vehicle_utilization_writer.write_vehicle_utilization_transaction`;
see `MOTIVE_UTILIZATION_WRITER_TRANSACTION.md`) for the same fixed window.
The writer transaction's existing all-or-nothing, returned-only,
no-checkpoint, no-sync-history behavior is reused **unmodified**:

- only provider-returned rollups are persisted;
- a requested/selected vehicle that Motive does not return creates **no**
  durable row, no zero row, no inactive/no-activity classification — only
  the sanitized `missing_requested_vehicle_count`;
- a `pagination.total = 0` / empty-rollups response is a **successful**
  no-op commit (`records_inserted = records_unchanged = records_updated =
  0`, `missing_requested_vehicle_count = selected_vehicle_count`) — not an
  error, and not "no activity";
- identical replay is a no-op (`records_unchanged` increments); conflicting
  replay (a returned rollup with a different completed-day metric value for
  the same durable identity) fails closed via the writer's existing
  `conflicting_existing_identity` policy and never updates the existing row;
- if the writer transaction itself fails after a successful provider read
  (for example a database persistence error), it rolls back the whole
  transaction; there is no partial write, no checkpoint write, no
  sync-history write, and no automatic retry — the provider call count for
  that invocation still never exceeds one.

## Response Shape (Sanitized Only)

Successful responses contain only:

```
status, resource, validation_mode, request_window_start, request_window_end,
selected_vehicle_count, provider_calls_attempted, provider_calls_completed,
pagination_total, returned_rollup_count, missing_requested_vehicle_count,
records_inserted, records_unchanged, records_updated, committed,
checkpoint_advanced, sync_history_written, scheduled_ingestion_enabled,
secrets_exposed
```

`checkpoint_advanced`, `sync_history_written`, and
`scheduled_ingestion_enabled` are always `false`; `records_updated` is always
`0`. Error responses are similarly sanitized (`status`, `resource`,
`error_code`, `message`, `provider_calls_attempted`,
`provider_calls_completed`, `selected_vehicle_count`,
`returned_rollup_count`, `records_inserted = 0`, `checkpoint_advanced =
false`, `secrets_exposed = false`). Neither ever includes provider vehicle
IDs, internal `motive_vehicle_id`, VIN, unit number, metric values, fuel
values, time values, utilization percentage, raw provider payload, request
headers, the API key, or database row IDs.

## No Checkpoint, No Sync History, No Normal Runtime Sync

This gate never calls or modifies `MotiveSyncCheckpoint`,
`_resource_checkpoint`, `_ensure_resource_checkpoint`,
`_mark_checkpoint_success`, `_checkpoint_after`, `MotiveSyncHistory`, or any
sync-history helper. No checkpoint row and no sync-history row is ever
created or changed by this route. After this gate, normal utilization
runtime sync remains fully disabled: there is still no
`/sync/vehicle-utilization` route, no scheduler, no daily job, no broad sync
hook, and no automatic date progression. The controlled validation route is
the **only** write-capable utilization endpoint, and it remains
feature-flagged off by default.

## Writer Contract Status Update

`app/motive/vehicle_utilization_writer_contract.py` now reports an
additional `controlled_manual_write_validation` block:

```
controlled_manual_write_validation:
  implementation_present: true
  route_present: true
  manual_route: "/api/v1/motive/verify/vehicle-utilization-write"
  feature_flag: "MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED"
  feature_flag_default_enabled: false
  production_validation_executed: false
  provider_calls_allowed_per_execution: 1
  selected_vehicle_limit: 3
  fixed_validation_window: {start_date: "2026-08-13", end_date: "2026-08-13"}
  checkpoint_writes: 0
  sync_history_writes: 0
  scheduled_ingestion_enabled: false
```

> **Superseded 2026-08-16.** `production_validation_executed` is no longer
> `false` — the route was actually run against production and failed
> safely. See "Update: Unit-Context Reconciliation Gate" below for the
> current, precise, sanitized shape of this block.

`production_validation_executed` stays `false` until this route is actually
run against production and evidence is captured — implementation and tests
existing is not sufficient to flip it. The top-level `writer_enabled` and
`persistence_enabled` fields continue to describe normal runtime sync and
remain `false`.

## Tests

`tests/test_motive_vehicle_utilization_controlled_write.py` proves, against
synthetic SQLite databases and `httpx.MockTransport` (never a live Motive
call):

- disabled-by-default (flag absent and flag explicitly `false`): zero
  provider calls, zero writes, zero checkpoint/history changes, sanitized
  `503`;
- strict boolean parsing of the kill switch (`true`/`1`/`yes`/`on` enable it;
  everything else, including malformed values, keeps it disabled);
- missing/`false` confirmation is rejected before any provider call;
- no-stored-vehicle fails safely (`404`) before any provider call;
- exact request bounds: date exactly `2026-08-13`, `page_no=1`,
  `per_page=100`, `unit_request_mode=ACCOUNT_DEFAULT` explicitly selected,
  `X-Metric-Units` header absent (not empty-string, not `None`-valued —
  genuinely absent from the outgoing headers dict), exactly one provider
  call, no `X-Time-Zone`/`X-User-Id` headers, selected-vehicle count capped
  at three even when more are stored;
- successful insert with exact sanitized counts and exact certified durable
  row fields;
- second identical execution is a no-op (`records_unchanged` increments, DB
  count unchanged);
- conflicting replay fails closed, existing row unchanged, no second row, no
  checkpoint/history writes;
- zero-result response is a successful no-op;
- the full bad-pagination matrix (total exceeds selected count, total !=
  returned count, `page_no`/`per_page` mismatch, missing pagination,
  non-integer/boolean pagination fields, duplicate rollup, unexpected
  vehicle) all fail closed with exactly one provider call and zero writes;
- unit/parser failures (`metric_units` missing/`None` or malformed,
  malformed provider schema) fail closed at the writer transaction's
  account-default readiness gate — **superseded 2026-08-17**: a returned
  `metric_units = False` is no longer a failure for this route (it persists
  successfully, same as `True`); see "Update: Controlled-Route
  Account-Default Validation Gate" below;
- provider failure (timeout, network failure, non-success HTTP status) fails
  closed with exactly one attempt, no retry, zero writes;
- a writer-transaction failure after a successful provider read rolls back
  with zero partial writes and zero checkpoint/history changes;
- tenant isolation: the route selects only the authenticated organization's
  vehicles (a cross-tenant vehicle is never selected, never leaked, and
  never persisted for the requesting organization);
- public output security: synthetic obviously-unsafe provider vehicle IDs,
  VINs, unit numbers, and metric values never appear in the success
  response, the error response, or any Polaris application log record.

## No Live Provider Calls

This gate makes zero live Motive provider calls anywhere in its
implementation or test suite. All provider interaction in tests is mocked
via `httpx.MockTransport`. The production validation run itself is
explicitly deferred to a separate, later step after this PR merges.

## Update: Unit-Context Reconciliation Gate (2026-08-16)

A real, controlled production validation was executed against this exact
route after this gate merged. It failed safely: `provider_calls_completed
= 1`, `returned_rollup_count = 1`, `records_inserted = 0`. See
`MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md` for the full sanitized
evidence and the resulting policy downgrade.

As a result:

- `production_validation_executed` is no longer `false`. It is now a
  precise, sanitized, static state
  (`production_validation_succeeded`, `production_validation_persisted_rows`,
  `production_validation_failure_stage`, `production_validation_provider_calls`,
  `production_validation_returned_rollups`, `production_validation_error_code`,
  `production_validation_safe_failure`) recorded in
  `app/motive/vehicle_utilization_writer_contract.py`.
- The read stage's own `every returned rollup's metric_units must be
  exactly True` pre-check (formerly the last bullet in the "One-Page,
  One-Call Contract" strict-validation list above) has been **removed**.
  Provider schema parse success is now explicitly distinct from durable
  persistence readiness: the parser preserves the returned Boolean as
  observed context, and the merged writer transaction's persistence-
  readiness gate is the single place that fails closed on unresolved
  returned unit-indicator semantics, before any commit. The controlled
  route's net behavior is unchanged (zero durable writes when the unit
  context is not ready) -- only which step raises, and under which code,
  changed.
- Every returned unit-indicator value -- `True`, `False`, or `None` --
  currently fails closed with the neutral code
  `provider_unit_indicator_semantics_unresolved` (a structurally malformed
  value fails closed separately with `provider_unit_context_invalid_type`).
  This is a strengthening, not a relaxation: it does not accept `False`,
  and it does not claim `True` is certified either.
- The feature flag remains disabled by default and was not enabled during
  this reconciliation gate's implementation or tests.

See `MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md` and the updated "Unit
Policy" sections of `MOTIVE_UTILIZATION_WRITER_TRANSACTION.md` for the full
downgraded contract.

## Update: Unit Semantics Certification Gate (2026-08-16)

A follow-up documentation-review gate confirmed, from official Motive
developer documentation, that no reconciling statement exists between
`X-Metric-Units` and the returned `vehicle.metric_units` field for this
endpoint. This route's behavior is unchanged: it remains disabled by
default, makes at most one provider call per invocation, and every returned
unit-indicator value still fails closed at the writer transaction's
persistence-readiness gate. See
`MOTIVE_UTILIZATION_UNIT_SEMANTICS_CERTIFICATION.md` for the full sourced
review.

## Update: Authentication + Unit-Mismatch Certification Gate (2026-08-17)

Motive API Support's 2026-08-17 written reply confirmed the returned
`vehicle.metric_units` indicator's meaning (`true`=metric, `false`=imperial)
and the request/response consistency rule for `GET /v1/vehicle_utilization`.
At the time this update was written, this route's request behavior was
unchanged: it still made at most one provider call per invocation, still
always sent `X-Metric-Units: true` (the canonical writer policy), and the
read stage still performed no returned-unit-indicator check of its own --
that remained the writer transaction's job. **Superseded 2026-08-17 (later
same day, see "Update: Controlled-Route Account-Default Validation Gate"
below): this route no longer sends `X-Metric-Units: true` at all.** The
description immediately below (of the canonical `true`/`false` mismatch
outcomes) describes the writer's forced-mode behavior as it existed before
that later update; read the final update section for this route's current
behavior. What changed at the time of this gate was the writer
transaction's outcome for that check:

- a returned `vehicle.metric_units = true` now **agrees** with this route's
  canonical `X-Metric-Units: true` request and is unit-ready -- a
  successful invocation now durably writes the row, instead of always
  failing closed as it did between 2026-08-16 and 2026-08-17;
- a returned `false` is a **provider-confirmed mismatch**
  (`provider_unit_policy_mismatch`), not a neutral "unresolved" outcome --
  this is exactly the combination the one real 2026-08-16 production
  execution of this route observed, and it is now understood to be
  provider-confirmed-unexpected rather than an open question (see
  `MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md`'s own update section);
- a returned `None`/missing value still fails closed with
  `provider_unit_indicator_semantics_unresolved`;
- a malformed (non-Boolean, non-`None`) value still fails closed with
  `provider_unit_context_invalid_type`.

The feature flag (`MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED`)
remains disabled by default and was **not** enabled during this gate's
implementation or tests -- this update changes only the writer's
persistence-readiness outcome for already-mocked test scenarios, never a
live call. See
`docs/engineering/MOTIVE_UTILIZATION_UNIT_SEMANTICS_CERTIFICATION.md` for
the full provider-confirmed semantics upgrade and
`docs/engineering/MOTIVE_AUTHENTICATION_CERTIFICATION.md` for the
authentication half of this gate.

## Update: Historical-Rollup Reconciliation Gate (2026-08-17)

This route's bounds are **unchanged**: still feature-flagged off by
default, still exactly one fixed historical day
(`2026-08-13..2026-08-13`), still at most three deterministic stored
vehicles, still at most one Motive provider call, still zero checkpoint and
zero sync-history writes. Only the underlying writer transaction's replay
policy changed (see `MOTIVE_UTILIZATION_WRITER_TRANSACTION.md`'s own update
section and `MOTIVE_UTILIZATION_HISTORICAL_RECONCILIATION.md` for the full
field-level audit): a repeat invocation of this route whose returned rollup
differs from an already-persisted row in an approved mutable field
(`utilization_percent`, `idle_time`, `driving_time`, `idle_fuel`,
`driving_fuel`) now reconciles that row in place (`records_updated`
increments, `reconciled_fields_count` reports how many fields changed)
instead of failing closed with `conflicting_existing_identity`. A genuine
identity/context conflict (mismatched unit context, provenance, or window)
still fails closed exactly as before. The route's response shape gains one
additive field, `reconciled_fields_count`, alongside the existing
`records_updated`. No live Motive call was made, no database migration was
added, and the feature flag was not enabled during this update's tests.

## Update: Controlled-Route Account-Default Validation Gate (2026-08-17)

**This is the current, authoritative description of this route's request
mode. All prior sections and updates above that describe this route always
sending `X-Metric-Units: true` are superseded by this section.**

PR #173 added `MotiveVehicleUtilizationUnitRequestMode`
(`METRIC`/`IMPERIAL`/`ACCOUNT_DEFAULT`) and additive `unit_request_mode`
parameters to `request_vehicle_utilization_page()` and
`write_vehicle_utilization_transaction()`, but deliberately left this
controlled route unmodified (see
`MOTIVE_UTILIZATION_ACCOUNT_DEFAULT_UNIT_MODE.md` section 6). This gate makes
the smallest possible change so that this route — and *only* this route —
now uses `ACCOUNT_DEFAULT`:

- `_execute_one_page_controlled_read` in
  `app/motive/vehicle_utilization_controlled_write.py` now calls
  `request_vehicle_utilization_page(..., unit_request_mode=MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT, ...)`
  instead of `metric_units=True`. The `X-Metric-Units` header is therefore
  **omitted entirely** from this route's one provider request (proven by a
  mocked-transport test asserting the key is genuinely absent from the
  outgoing headers dict, not sent as an empty string or `None` value).
  `x-api-key` and `Accept: application/json` are unchanged; `X-Time-Zone` and
  `X-User-Id` remain absent, exactly as before.
- `run_controlled_vehicle_utilization_write` now passes
  `unit_request_mode=MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT`
  into `write_vehicle_utilization_transaction(...)`. As a result, a returned
  `vehicle.metric_units = True` **or** `= False` both persist successfully
  (the writer records exactly the returned Boolean, never a hardcoded
  value) — this route no longer treats a returned `False` as a
  `provider_unit_policy_mismatch`. A missing (`None`) or malformed returned
  indicator still fails closed with the same two codes as before
  (`provider_unit_indicator_semantics_unresolved` /
  `provider_unit_context_invalid_type`).
- Every other bound is unchanged: fixed window `2026-08-13..2026-08-13`, at
  most 3 selected vehicles, at most 1 provider call, no retry, no page 2, no
  checkpoint/sync-history writes, feature flag
  (`MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED`) still default
  `false`. The response shape is unchanged (no new fields were added; the
  existing sanitized counters are sufficient to prove successful persistence,
  and `metric_units` can be verified independently against the database in
  tests).

At the time this section was written, no live `/v1/vehicle_utilization`
call, in any mode, had been made as part of this gate — every claim above
was proven by `httpx.MockTransport` tests only. **Superseded 2026-08-18: see
"Update: Account-Default Live-Staging Validation Success" immediately
below — the required single live call has since been made and succeeded.**

## Update: Account-Default Live-Staging Validation Success (2026-08-18)

**HISTORICAL** (unchanged, retained as evidence, not erased): the one prior
real controlled production validation, executed while this route still
forced `X-Metric-Units: true`, failed safely on a provider-confirmed
unit-context mismatch (`provider_calls_completed = 1`,
`returned_rollup_count = 1`, `records_inserted = 0`). See
`MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md` for the full sanitized record
of that earlier, forced-metric attempt. That result is not overwritten or
reinterpreted by this section — it remains accurate for the request mode
that was actually in effect at the time it was recorded.

**CURRENT:** a single, separately-authorized live-staging controlled
validation was executed after PR #174 deployed this route's switch to
`MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT`, and it succeeded.

Request bounds (unchanged from every prior invocation of this route):

- `request_window_start` / `request_window_end`: `2026-08-13` (fixed,
  single day)
- `selected_vehicle_count`: `3`
- request mode: `ACCOUNT_DEFAULT` — `X-Metric-Units` omitted entirely
- `provider_calls_attempted`: `1` (maximum for this route)
- no retry

Sanitized result:

```
status = success
resource = vehicle_utilization_controlled_write_validation
validation_mode = controlled_manual_write_validation

provider_calls_attempted = 1
provider_calls_completed = 1

pagination_total = 1
returned_rollup_count = 1
missing_requested_vehicle_count = 2

records_inserted = 1
records_unchanged = 0
records_updated = 0
reconciled_fields_count = 0

committed = true

checkpoint_advanced = false
sync_history_written = false
scheduled_ingestion_enabled = false
secrets_exposed = false
```

No provider vehicle ID, VIN, unit number, driver information, raw metric
value, raw provider payload, API key, Polaris bearer token, or database row
ID is recorded here or was recorded anywhere in the sanitized evidence
gathered for this validation. The controlled feature flag
(`MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED`) was returned to
`false` and redeployed immediately after this single invocation.

### What this validation proves

1. Polaris successfully made one live `/v1/vehicle_utilization` request
   through the bounded controlled path using `ACCOUNT_DEFAULT`.
2. The request completed successfully without Polaris forcing
   `X-Metric-Units`.
3. Motive returned one rollup for the three selected vehicles.
4. Polaris accepted the returned unit context under `ACCOUNT_DEFAULT` and
   durably inserted one utilization row.
5. The database transaction committed successfully.
6. Two requested vehicles were omitted by Motive, and Polaris did **not**
   synthesize zero rows, an inactive classification, or a no-activity
   classification for either of them — only the sanitized
   `missing_requested_vehicle_count = 2`.
7. No checkpoint was advanced.
8. No sync-history row was written.
9. Scheduled ingestion remained disabled throughout.
10. No retry occurred.
11. No secret was exposed in the sanitized response.

### What this validation does NOT prove

- **It does not prove all Motive vehicles, or this organization's other
  vehicles, behave the same way.** One rollup, for one of three selected
  vehicles, on one fixed historical day, was observed.
- **Omission does not mean zero activity.** The two omitted vehicles are
  `provider_rollup_absent`, nothing more.
- **`ACCOUNT_DEFAULT` is not certified for every account.** This is one
  successful observation on this Motive account, not a general provider
  behavior guarantee.
- **The exact provider company-rollup timezone field is still not
  certified.** See `MOTIVE_UTILIZATION_TIMEZONE_CERTIFICATION.md` — this
  validation proceeded under that document's provisional operational
  assumption, which remains provisional.
- **Broad historical ingestion is not ready**, and scheduled ingestion is
  **not** enabled by this validation or this document.
- **Pagination behavior beyond this one-result observation is not newly
  proven.** `pagination_total = 1` for this specific call; nothing broader
  is inferred.
- **Fuel values are not claimed to be universally imperial or metric** as a
  result of this single observation.
- **The exact returned `metric_units` Boolean is not recorded here**, because
  no read-only, provider-call-free proof of the persisted row's stored value
  was independently available at documentation time. Per the evidence
  constraints for this record: returned unit context was accepted and
  persisted under `ACCOUNT_DEFAULT`. A future audit with direct, read-only
  access to the staging database could record this precisely (as
  `observed_unit_context = metric` or `observed_unit_context = imperial`,
  never a raw Boolean, ID, or metric value) without requiring another live
  provider call.

### Doc/contract reconciliation

`app/motive/vehicle_utilization_writer_contract.py`'s
`controlled_manual_write_validation` block's `production_validation_executed`
and related fields should be read alongside this record as reflecting the
**current** (`ACCOUNT_DEFAULT`) state, not the earlier forced-metric failure
recorded in `MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md`. Both records are
accurate for the request mode that was in effect when each was captured;
neither supersedes or erases the other as a historical fact.

### Next gate

The next proposed engineering gate is **not** scheduled ingestion. It is:

**Bounded recent-window reconciliation design.**

That design gate must determine (design only — no implementation in that
gate either, until it is itself separately authorized):

- how many recent days to reread on a bounded, non-scheduled basis;
- batching and vehicle-count limits for a reread;
- pagination bounds for a reread (page count, per-page size);
- reconciliation/update semantics for a bounded reread (building on, not
  replacing, the existing `MUTABLE_ON_PROVIDER_RECONCILIATION` policy — see
  `MOTIVE_UTILIZATION_HISTORICAL_RECONCILIATION.md`);
- transaction boundaries for a multi-window reread;
- failure isolation (one window's failure must not corrupt or abandon
  others);
- checkpoint policy — deliberately still not implemented by this or any
  prior gate.

Scheduled ingestion, checkpoint advancement, broader feature-flag
enablement, and any further live Motive call all remain separately
authorized, later decisions — none of them is authorized by this
documentation update.
