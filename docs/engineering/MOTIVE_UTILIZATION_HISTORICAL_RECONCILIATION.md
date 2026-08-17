# Motive Vehicle-Utilization Historical-Rollup Reconciliation

This gate defines and implements a safe **historical-rollup reconciliation
policy** for Motive vehicle utilization. It is a policy + transaction-safety
gate, **not** a scheduling gate: it does not touch `MotiveSyncCheckpoint`,
does not add a scheduler, does not change the controlled route's
feature-flag default, does not change authentication, and adds no database
migration.

Repository: `ThePolarisLab/Polaris-Lab`. Starting `main`:
`1b77d2f279e623e6cdde58b69d7eacf461d31c84` (PR #166, "Certify Motive API key
auth and utilization unit mismatch," and PR #165, a KB milestone doc, both
merged).

## 0. Why This Gate Exists

Motive API Support has confirmed that vehicle-utilization rollups may later
be incomplete or change slightly as provider-side processing completes, and
recommended periodically rereading a recent rolling window. Before this
gate, `write_vehicle_utilization_transaction`
(`app/motive/vehicle_utilization_writer.py`) treated **any** replay of an
existing durable identity whose provider-derived values differed from the
stored row as a hard conflict and rejected it outright
(`conflicting_existing_identity`). That behavior was correct before the
provider clarification -- Polaris had no basis to assume a changed value was
legitimate rather than a bug or a mapping error -- but it cannot support
safe rolling-window rereads indefinitely, since a provider-side correction
to an already-persisted window would always be rejected.

This gate defines exactly when Polaris may reconcile a changed historical
rollup and when it must still refuse the update.

## 1. Starting-State Confirmation

Before implementation, the following assumptions (from the task
specification) were confirmed directly against the code, not assumed:

| Assumption | Confirmed against |
| --- | --- |
| Durable identity: `organization_id, motive_vehicle_id, request_window_start, request_window_end` | `MotiveVehicleUtilizationRecord.__table_args__` (`uq_motive_vehicle_util_org_vehicle_request_window`), `vehicle_utilization_writer.py` `_plan_writes`/`_load_existing_identity_rows` |
| Returned-only persistence, no synthetic rows for omitted requested vehicles | `write_vehicle_utilization_transaction` only ever iterates `rollups` (the returned set); `missing_requested_vehicle_count` is a diagnostic count only, never a row |
| Canonical request policy `X-Metric-Units: true` | `vehicle_utilization_unit_policy.py` `MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_METRIC_UNITS = True` |
| Unit readiness: request true + returned true → allowed; true + false → fail closed; missing/malformed → fail closed | `validate_vehicle_utilization_unit_persistence_readiness` |
| One DB transaction | `write_vehicle_utilization_transaction`: exactly one `session.commit()`, one `try/except` with `session.rollback()` on every failure path |
| Tenant-safe `MotiveVehicleRecord` mapping | `_resolve_tenant_vehicles` scopes by `organization_id`; cross-tenant vehicles are `unknown_vehicle` |
| Controlled route disabled by default | `MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED` defaults false (`controlled_write_enabled()`) |
| Checkpoints / scheduling disabled | `write_vehicle_utilization_transaction` and `run_controlled_vehicle_utilization_write` never import or touch `MotiveSyncCheckpoint`; no scheduler code exists for this resource |
| No broad utilization sync | No `/sync/vehicle-utilization` route exists |
| Prior replay policy: identical → unchanged; changed → fail closed | `_is_identical_replay` (pre-gate) / `_plan_writes` |

All assumptions held. No STOP condition in section 1/4/21/22/23 of the task
specification was triggered by this audit.

## 2. Provider Semantics Preserved (Unchanged By This Gate)

- one returned `vehicle_idle_rollup` is one aggregate for one vehicle across
  the requested date range;
- `start_date`/`end_date` are inclusive calendar-date filters;
- an omitted requested vehicle does **not** prove zero activity or
  inactivity;
- `pagination.total` counts returned aggregate rows after filters, not
  requested vehicle IDs;
- historical utilization rollups may legitimately change after initial
  processing (the provider basis for this gate);
- recent periods may be reread to reconcile provider-finalized values.

Unit-consistency rules from PR #166 are unchanged and unweakened -- see
section 5, Case 5 below.

## 3. Field-Level Reconciliation Matrix

Audited directly from `app/models/motive.py`
(`MotiveVehicleUtilizationRecord`), the parser
(`app/connectors/motive_vehicle_utilization.py`,
`MotiveVehicleUtilizationRollup`), and the writer
(`app/motive/vehicle_utilization_writer.py`) -- not assumed from the task
specification's own "likely candidates" list.

Two structural facts drove this audit:

1. `MotiveVehicleUtilizationRollup` (the parsed, validated incoming value)
   carries **only**: `provider_vehicle_id`, `source_endpoint`, `provider`,
   `utilization_percent`, `idle_time`, `driving_time`, `idle_fuel`,
   `driving_fuel`, `metric_units`, `request_start_date`, `request_end_date`,
   `source_keys`, `parser_version`. There is **no** `distance`,
   `engine_hours`, `observed_at`, or `reporting_period_start`/`_end` on the
   rollup at all -- the current parser never produces these values from any
   provider response.
2. `_build_new_row` (the writer's insert path) always sets
   `reporting_period_start=None`, `reporting_period_end=None`,
   `distance=None`, `engine_hours=None`, `observed_at=None`,
   `provider_payload_metadata={}`, `provider=MOTIVE_PROVIDER` (a constant,
   never `rollup.provider`), and `metric_units=True` (a constant, gated by
   the unit-readiness check having already required the incoming value to
   be `True`).

| Column | Category | Classification | Rationale |
| --- | --- | --- | --- |
| `id` | -- | `OUT_OF_SCOPE` | Surrogate PK, never provider data |
| `organization_id` | A (durable identity) | `IMMUTABLE` | Part of the certified identity key and the unique constraint |
| `organization_slug` | -- (Polaris-owned tenant metadata) | `DERIVED_BUT_STABLE` | Already deliberately excluded from replay-equivalence comparison (existing `_is_identical_replay`/now `_existing_row_context_compatible` docstring); not provider-derived, not touched by reconciliation |
| `provider` | B (provenance) | `IMMUTABLE` | Always the constant `"motive"`; never read from the rollup |
| `provider_vehicle_id` | B (identity/context) | `IMMUTABLE` | Resolves the `MotiveVehicleRecord` FK; a mismatch is a mapping conflict (section 15), never reconciled |
| `motive_vehicle_id` | A (durable identity) | `IMMUTABLE` | Part of the certified identity key and the unique constraint |
| `source_endpoint` | B (provenance) | `IMMUTABLE` | Must equal `CERTIFIED_SOURCE_ENDPOINT`; a mismatch means the existing row predates/violates the certified writer contract |
| `request_window_start` | A (durable identity) | `IMMUTABLE` | Part of the certified identity key and the unique constraint |
| `request_window_end` | A (durable identity) | `IMMUTABLE` | Part of the certified identity key and the unique constraint |
| `reporting_period_start` | F (currently-null) | `NULL_ONLY` | Not on the rollup dataclass; writer always inserts `None`; nothing to reconcile against |
| `reporting_period_end` | F (currently-null) | `NULL_ONLY` | Same as above |
| `utilization_percent` | C (provider-derived rollup) | `MUTABLE_ON_PROVIDER_RECONCILIATION` | Directly parsed from the returned `utilization` field; provider-confirmed to "change slightly" |
| `idle_time` | C (provider-derived rollup) | `MUTABLE_ON_PROVIDER_RECONCILIATION` | Directly parsed from the returned `idle_time` field |
| `driving_time` | C (provider-derived rollup) | `MUTABLE_ON_PROVIDER_RECONCILIATION` | Directly parsed from the returned `driving_time` field |
| `idle_fuel` | C (provider-derived rollup) | `MUTABLE_ON_PROVIDER_RECONCILIATION` | Directly parsed from the returned `idle_fuel` field; unit-context-gated before ever reaching reconciliation (see Case 5) |
| `driving_fuel` | C (provider-derived rollup) | `MUTABLE_ON_PROVIDER_RECONCILIATION` | Directly parsed from the returned `driving_fuel` field; unit-context-gated |
| `metric_units` | B (identity/context) | `IMMUTABLE` | By the time a rollup reaches reconciliation it has already passed the unit-readiness gate (always `True`); an existing row with `metric_units is not True` is treated as context-incompatible (Case 4/section 14), never reconciled to `True` |
| `distance` | E/F (legacy/currently-null) | `NULL_ONLY` | Not on the rollup dataclass at all; writer always inserts `None` |
| `engine_hours` | E/F (legacy/currently-null) | `NULL_ONLY` | Not on the rollup dataclass at all; writer always inserts `None` |
| `observed_at` | E/F (legacy/currently-null) | `NULL_ONLY` | Not on the rollup dataclass at all; writer always inserts `None`; no invented Motive observation timestamp |
| `parser_version` | D (provenance) | `IMMUTABLE` | Must equal `CERTIFIED_PARSER_VERSION`; per section 6's explicit STOP condition, a parser-version change is never a trigger for a row rewrite in this gate -- it would require a separately-authorized migration/backfill design |
| `provider_payload_metadata` | D/E (provenance/legacy) | `OUT_OF_SCOPE` | Always `{}`; the writer never stores raw payload content and reconciliation does not add that capability |
| `created_at` | -- (bookkeeping) | `IMMUTABLE` | Historical fact of first insert; never rewritten |
| `updated_at` | -- (bookkeeping) | `DERIVED_BUT_STABLE` | SQLAlchemy `onupdate` fires automatically, and only, when a real column is actually mutated; a true no-op (Case 2) never touches it |

**`MUTABLE_ON_PROVIDER_RECONCILIATION`** (the complete, exhaustive set):
`utilization_percent`, `idle_time`, `driving_time`, `idle_fuel`,
`driving_fuel`. No other column is ever written by reconciliation.

No genuinely new column or migration was found to be required by this
audit -- the STOP condition in section 4/22 was not triggered.

## 4. Durable Identity: Unchanged

The reconciliation identity remains exactly `organization_id +
motive_vehicle_id + request_window_start + request_window_end`. This gate
does not change database uniqueness, does not use `provider_vehicle_id`
alone, `reporting_period_start`/`_end`, `observed_at`, fuel values,
utilization value, or parser version as an alternate identity, and adds
**no migration**.

## 5. Reconciliation Policy (Implemented)

**Case 1 — no existing row.** All writer validations pass → INSERT the
returned rollup (unchanged from before this gate).

**Case 2 — existing row, exact same provider data.** No-op / unchanged.
Timestamps are never touched merely to record replay activity (no column is
mutated, so SQLAlchemy's `onupdate` never fires).

**Case 3 — existing row, changed provider-derived rollup data.** May
reconcile only if **all** of the following remain true (checked by
`_existing_row_context_compatible`, then `_compute_mutable_field_changes`):
same organization (implicit in the query scope); same `motive_vehicle_id`;
same request window; same unit-consistent measurement context
(`metric_units is True` on the existing row); same canonical
parser/contract provenance (`source_endpoint`, `parser_version` both
certified); no identity field changed; the incoming rollup itself already
passed every writer validation (steps 1-7, before reconciliation is even
considered); and the change affects only the explicitly-approved
`MUTABLE_ON_PROVIDER_RECONCILIATION` fields. Then: update only the
differing approved fields, atomically, as part of the same single-commit
transaction as everything else in the batch.

**Case 4 — existing row, identity/context conflict.** Fail closed
(`conflicting_existing_identity`). The existing row is left completely
unchanged; no second row is created; the whole batch rolls back.

**Case 5 — unit policy changed or became inconsistent.** Fail closed. Never
convert between unit systems during reconciliation. In practice this is
subsumed by Case 4: an incoming rollup with a returned `metric_units` that
disagrees with the canonical request already fails at the pre-existing
unit-readiness gate (step 6, `provider_unit_policy_mismatch` /
`provider_unit_indicator_semantics_unresolved` /
`provider_unit_context_invalid_type`) before reconciliation logic ever
runs; an existing row whose `metric_units is not True` fails
`_existing_row_context_compatible` and is treated as Case 4.

## 6. Approved Mutable Field Audit

See the matrix in section 3. The "likely candidates" list in the task
specification (`utilization`, `idle_time`, `driving_time`, `idle_fuel`,
`driving_fuel`) matched the audited result exactly, but this was verified
by reading the model/parser/writer, not assumed. `metric_units`,
`parser_version`, `provider_vehicle_id`, the request-window fields, the
reporting-period fields, `distance`, and `engine_hours` were all
individually audited and found to be either `IMMUTABLE` or `NULL_ONLY` (see
section 3) -- none of them are approved-mutable. No parser-version-triggered
rewrite is implemented; per the section-6 STOP condition, that would require
a separate migration/backfill gate.

## 7. No Blind Overwrite

Reconciliation is implemented as an explicit, field-by-field comparison and
controlled change set. `_compute_mutable_field_changes` compares exactly
the five approved fields (never anything else) using Decimal-safe equality,
and returns only the ones that actually differ; the caller
(`write_vehicle_utilization_transaction`) applies exactly those fields via
explicit `setattr` calls -- there is no ORM `session.merge()`, no
`update()` statement touching arbitrary columns, and no code path that
copies every field from the incoming rollup onto the existing row. As a
defensive guard (real, tested code, not only a comment/convention),
`_compute_mutable_field_changes` raises
`provider_rollup_reconciliation_conflict` if a compared field is ever found
to differ while not being present in `MUTABLE_ON_PROVIDER_RECONCILIATION`
-- unreachable with the current fixed candidate list, but a genuine
safety net if the schema or candidate list ever drift out of sync.

## 8. Decimal Safety

All five approved fields are `Numeric` columns mapped to Python `Decimal`
end-to-end (rollup dataclass → writer → ORM column). `_decimal_differs`
wraps both sides in `Decimal(...)` and compares with `!=` -- no `float()`
coercion anywhere, and no epsilon/tolerance logic. `Decimal("1.0000")` vs.
`Decimal("1.0000")` → unchanged. A different Decimal value is a legitimate
reconciliation candidate for an approved field. The test suite includes an
explicit proof using values that a float round-trip would corrupt
(`Decimal("100000000000.0001")` vs. `Decimal("100000000000.0002")`),
asserting the stored value's string representation is bit-for-bit exact.

## 9. Auditability

No raw Motive payload is ever stored (`provider_payload_metadata` stays
`{}`, unchanged). Auditability is implemented via writer-return metadata
(preference order option B from the task specification):
`VehicleUtilizationWriteResult.records_updated` now counts reconciled rows
(previously always `0`), and a new additive
`reconciled_fields_count: int = 0` field sums how many individual approved
fields changed across the whole batch. Both are surfaced through
`run_controlled_vehicle_utilization_write`'s sanitized result dict and its
structured log line. No new audit subsystem, no reconciliation-event table,
and no schema change were added -- there was no existing sync/reconciliation
history structure that fits this gate's scope without checkpoint
semantics (see section 10), so option B was the correct minimal choice.

## 10. Sync History

Unchanged. The controlled route continues to guarantee
`sync_history_written = false`; this gate does not begin writing
`MotiveSyncHistory` rows for reconciliation activity. `MotiveSyncHistory`
remains semantically tied to checkpoint-driven sync runs, which are out of
scope here.

## 11. Checkpoints

Absolute: `MotiveSyncCheckpoint` is never read, created, or advanced by
this gate. No checkpoint write occurs on insert, unchanged replay,
reconciled replay, or failure. The writer transaction and the controlled
route are unchanged in this respect; the full backend test suite continues
to assert zero checkpoint mutations for every writer/controlled-write test.

## 12. Rolling-Window Contract (For A Future Scheduler)

No scheduler is added in this gate. The reconciliation contract is defined
so a future rolling-window reader can safely call
`write_vehicle_utilization_transaction` repeatedly for overlapping recent
windows:

- rereads are expected and safe;
- identical rows are a true no-op;
- changed approved metrics reconcile in place;
- omitted vehicles never delete, zero, or infer anything about existing
  rows (see section 13);
- there is no hard deletion because a provider row disappears from a later
  response;
- whole-batch atomicity holds regardless of how many times the writer is
  called or how the calls overlap in vehicle/window coverage.

## 13. Disappearing Provider Rows

If Polaris previously persisted a returned rollup for a window, and a later
reread of the same requested window does not return that vehicle, the
writer does **nothing** to that row: no delete, no zeroing, no "inactive"
marking, no inference, no synthesized replacement. This falls directly out
of the implementation: `write_vehicle_utilization_transaction` only ever
iterates the `rollups` sequence it is handed; there is no code path that
enumerates previously-persisted rows to reconcile against an absence. This
is proven by a dedicated test
(`test_omitted_vehicle_row_is_left_completely_untouched`) that snapshots
every field (including `updated_at`) before and after a reread that omits
the vehicle, and asserts byte-for-byte equality. If future provider
guidance ever supports deletion semantics, that must be a separate,
explicitly-authorized gate -- not implied by this one.

## 14. Changed Unit Indicator

If an existing stored row was persisted under a valid, consistent unit
context (`metric_units is True`, certified provenance) and a later reread
returns a rollup with a contradictory unit indicator, the writer fails
closed **before reconciliation is ever considered**: a returned `False`
fails at the pre-existing unit-readiness gate with the existing, unchanged
`provider_unit_policy_mismatch` code (or `provider_unit_indicator_semantics_unresolved`
for a missing value, or `provider_unit_context_invalid_type` for a
malformed value). Fuel values are never reconciled in this scenario, and
the previously-persisted row is never altered.

## 15. Changed Vehicle Mapping

If `provider_vehicle_id` would resolve to a different `MotiveVehicleRecord`
or becomes ambiguous within the organization, the writer fails closed with
the existing `unknown_vehicle` code (unchanged from before this gate) or,
if an existing durable row's `provider_vehicle_id` disagrees with the
incoming rollup's, `_existing_row_context_compatible` returns `False` and
the row is treated as a Case 4 identity conflict. There is no vehicle
auto-create and no cross-tenant lookup; both are unchanged by this gate.

## 16. Transaction Semantics

Whole-batch atomicity is preserved and, if anything, made more explicit by
this gate. `_plan_writes` now computes a full **decision** for every row in
the batch (insert / unchanged / reconcile / conflict) before any row is
staged (`session.add`) or any existing row is mutated (`setattr`). Only
after the entire batch's decisions are known safe does
`write_vehicle_utilization_transaction` apply them: insert new rows, then
apply each reconciliation's field-by-field change set, then flush, then
commit exactly once. Any conflict anywhere in the batch raises before
`session.flush()`/`session.commit()`, and the top-level `except` clause
calls `session.rollback()`, discarding any already-applied-but-unflushed
`setattr` mutations along with everything else -- so a batch containing one
safe reconciliation and one hard conflict rolls back **both**. This is
proven by `test_whole_batch_rollback_discards_a_pending_reconciliation_too`.

## 17. Concurrency

Unchanged from the writer-transaction gate: the database unique constraint
`uq_motive_vehicle_util_org_vehicle_request_window` remains the final
concurrency guard, and `IntegrityError` is still translated into the
sanitized `database_identity_conflict` code with a full rollback. This
gate adds no distributed lock and no new row-locking mechanism; the
existing application-level preflight (`_load_existing_identity_rows`) plus
the database constraint remain sufficient for the stated scope, matching
the prior gate's conclusion. No STOP condition was triggered here --
reconciliation does not change the concurrency model, since a reconciled
row's `setattr` mutations are only ever flushed as part of the same single
`session.flush()`/`session.commit()` pair as inserts, so the same
constraint-as-final-guard behavior applies to both.

## 18. Writer Return Contract

`VehicleUtilizationWriteResult` gains one additive field,
`reconciled_fields_count: int = 0` (backward compatible: existing
positional and keyword construction is unaffected since it has a default).
`records_updated` now genuinely counts reconciled rows. No raw metric
value, and no vehicle ID beyond what was already part of the sanitized
contract, is ever returned.

## 19. Existing Controlled Route

`POST /api/v1/motive/verify/vehicle-utilization-write` remains
feature-flagged off by default
(`MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED`). No live Motive
call is made in this gate or its tests. The route's response dict gains
the additive `reconciled_fields_count` key alongside the existing
`records_updated`; it is not broadened into a general sync endpoint, and
its bounds (one fixed historical day, at most three vehicles, at most one
provider call) are unchanged.

## 20. Error Classes

`conflicting_existing_identity` remains the code for identity/context
conflicts (unchanged meaning, now more precisely scoped to identity/context
disagreement rather than "any difference"). `provider_unit_policy_mismatch`
remains the unit-mismatch code from PR #166, unchanged. One new code is
added: `provider_rollup_reconciliation_conflict`
(`RECONCILIATION_CONFLICT_ERROR_CODE`), used only for the defensive
unapproved-field-difference guard described in section 7 -- currently
unreachable through real provider data given the present schema, but
mapped into the controlled route's `_CONTROLLED_WRITE_WRITER_ERROR_CODES`
set for completeness.

## 21. Historical Data Safety

No live database mutation was made in this gate; every test runs against a
synthetic, ephemeral SQLite database. This gate does not assume the
database is empty in production -- the reconciliation logic is written to
be backward-safe for any pre-existing row: an existing row is only ever
reconciled if it first passes `_existing_row_context_compatible` (proof it
was created under the certified writer contract); a legacy/incompatible row
sharing the identity key is treated as a Case 4 conflict, exactly as
before this gate (see `test_conflicting_replay_incompatible_existing_unit_context_fails_closed`
and `test_conflicting_replay_incompatible_existing_source_provenance_fails_closed`,
both still passing unchanged). No backfill and no cleanup are performed.

## 22. Database Schema

No migration. No uniqueness change. No new column. The field-level audit
in section 3 found every currently-persisted column already accounted for
by the existing schema; nothing required a new column to support
reconciliation.

## 23. Timezone

Not touched by this gate. `X-Time-Zone` is not added. Request-window
timezone logic is unchanged.

## 24. Authentication

Not touched by this gate. `x-api-key` remains as certified by PR #166. No
live auth test was run, and no key was rotated.

## 25-30. Test Matrix

Implemented in `tests/test_motive_vehicle_utilization_writer_transaction.py`
and `tests/test_motive_vehicle_utilization_controlled_write.py`:

- basic replay: insert, identical replay (no-op, no timestamp change), and
  parametrized reconciliation for all five approved fields individually,
  plus a multi-field reconciliation in one row;
- unsafe differences: organization mismatch, cross-tenant vehicle,
  unexpected vehicle, duplicate returned rollup, incompatible existing unit
  context, incompatible existing source/parser provenance, a different
  request window creating a separate row (never overwriting the original),
  and the defensive unapproved-field-difference guard;
- omission: a vehicle/window absent from a reread leaves the existing row
  byte-for-byte untouched (including `updated_at`) -- zero delete, zero
  zeroing, zero synthesized replacement, zero inactive inference;
- batch atomicity: one safe reconciliation + one hard conflict rolls back
  the whole batch, including the safe reconciliation; one insert + one
  reconciliation + one identical replay commits once with correct counts;
- Decimals: exact Decimal reconciliation proven with values a float
  round-trip would corrupt; identical Decimals remain unchanged; no
  epsilon/tolerance logic exists anywhere in the comparison path;
- no-live/no-checkpoint: every test in both files continues to assert zero
  Motive HTTP calls (all provider interaction is mocked), zero checkpoint
  writes, zero sync-history writes, and the controlled route's default-off
  feature flag.

## 31. Documentation

This document is new. `MOTIVE_UTILIZATION_WRITER_TRANSACTION.md` and
`MOTIVE_UTILIZATION_CONTROLLED_WRITE_VALIDATION.md` each gained an "Update"
section describing this gate's changes to their respective contracts.
`POLARIS_TRACK_4C_MOTIVE_ROADMAP.md` gained a new roadmap entry.
`MOTIVE_UTILIZATION_CONTROLLED_WRITE_VALIDATION.md` was not otherwise
restructured, since reconciliation status did not require changing its
production-validation-evidence section.

## 32. Knowledge Base

No new Knowledge Base milestone PR is created in this gate; the existing
milestone automation may capture this gate's completion separately.

## 33. Pre-Existing `MotiveConnector` Bug (Not Touched)

`app/api/connectors.py` appears to call
`MotiveConnector(credential_store=MotiveCredentialStore(...))` while
`MotiveConnector.__init__` does not accept a `credential_store` parameter.
This is a separately identified, pre-existing issue, confirmed in a prior
gate's review. It is **not** touched by this gate -- no scope creep. It
remains a known, out-of-scope issue for a future, separately-authorized
fix.

## Absolute Prohibitions (Confirmed Honored)

No live Motive call. No production database write. No scheduler. No
checkpoint advancement. No broad utilization sync. No key rotation. No
database migration. No frontend, Dashboard, or Daily Brief changes. No fix
to the unrelated `MotiveConnector` bug. No deletion semantics. No
synthetic zero-activity rows. No blind ORM merge.
