# Motive Vehicle Utilization Unit-Context Evidence

**HISTORICAL RECORD, retained as evidence, not superseded or erased.** This
document records the single controlled production validation that ran while
the controlled route still forced `X-Metric-Units: true`. It failed safely,
exactly as this document describes below. On **2026-08-18**, a later,
separate controlled validation — after the route was switched to
`MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT` (PR #174) —
**succeeded** and durably inserted one row. See
`MOTIVE_UTILIZATION_CONTROLLED_WRITE_VALIDATION.md`'s "Update:
Account-Default Live-Staging Validation Success (2026-08-18)" section for
that current record. Both records are accurate for the request mode that
was actually in effect at the time each was captured; this document is not
rewritten in light of the later success.

This gate reconciles two newly authoritative pieces of evidence gathered
after PR #162 ("Add controlled Motive utilization write validation")
merged, and downgrades the previously-certified returned unit-indicator
policy accordingly. It does **not** make a live Motive call, does **not**
merge, and does **not** add a migration.

## A. One Real Controlled Production Validation

On **2026-08-16**, a human operator executed the feature-flagged
`POST /api/v1/motive/verify/vehicle-utilization-write` route in production,
under explicit confirmation. It failed safely.

Sanitized facts only:

| Field | Value |
| --- | --- |
| `execution_date` | `2026-08-16` |
| `route` | `/api/v1/motive/verify/vehicle-utilization-write` |
| `fixed request window` | `2026-08-13..2026-08-13` |
| `selected_vehicle_count` | `3` |
| `provider_calls_attempted` | `1` |
| `provider_calls_completed` | `1` |
| `returned_rollup_count` | `1` |
| `records_inserted` | `0` |
| `checkpoint_advanced` | `false` |
| `sync_history_written` | `false` |
| `secrets_exposed` | `false` |
| `status` | `failed` |
| `error_code` | `provider_unit_policy_mismatch` |

**Not recorded, ever:** provider vehicle ID, VIN, vehicle number,
utilization value, time values, fuel values, raw provider response, API
key, or authorization token. This document, and the sanitized static
metadata added to `app/motive/vehicle_utilization_writer_contract.py`
(`PRODUCTION_WRITE_VALIDATION_EVIDENCE`), are the only durable record of
this event; neither is dynamically inferred from logs.

### What the failure actually proved

The controlled request explicitly sent `X-Metric-Units: true`. Motive
returned exactly one rollup that **parsed successfully** but whose
`vehicle.metric_units` did **not** equal `True`.

That is the entire, certified conclusion:

> Polaris's prior assumption that the returned Boolean must equal the
> requested Boolean is **not certified**, and was contradicted by one live
> provider observation.

This document, the code, and every test added in this gate deliberately
draw **no further conclusion**. In particular, none of the following is
certified, claimed, or implied anywhere in this codebase:

- `False == imperial`
- `False == metric`
- the header was ignored
- the parser is wrong
- the provider's documentation is wrong

Zero durable rows were written. The route failed closed exactly as
designed: `records_inserted = 0`, no checkpoint write, no sync-history
write, no secrets exposed.

## B. Motive API Support's August 12, 2026 Written Clarification

Motive API Support sent a written clarification for `GET
/v1/vehicle_utilization` semantics, treated as provider-authoritative
guidance for this integration:

1. `start_date`/`end_date` are calendar-date filters resolved using the
   company's configured/default Motive timezone.
2. `end_date` is **inclusive**.
3. Each `vehicle_idle_rollup` is one aggregate for one vehicle across the
   requested date range.
4. Multiple `vehicle_ids[]` yield **at most one** aggregate per matching
   vehicle for that requested range.
5. Vehicles without matching utilization rollups are **omitted**; absence
   means only "no matching rollup returned," not proof of inactivity.
6. `pagination.total` is the number of result rows / vehicle-level
   aggregates after filters, **not** the requested vehicle count.
7. `idle_time` and `driving_time` are seconds.
8. `idle_fuel` and `driving_fuel` depend on the requested unit system.
9. `X-Metric-Units` selects the requested unit system.
10. `vehicle.metric_units` should be retained as response unit context.
11. No provider rollup ID is exposed.
12. The recommended synchronization identity is effectively `vehicle.id +
    normalized start_date + normalized end_date`.
13. Completed utilization rollups **may occasionally be incomplete or
    later differ slightly** as records are processed.
14. Production integrations should periodically re-read a recent rolling
    window rather than assuming a returned completed aggregate is
    permanently immutable.

Polaris does not extrapolate beyond this written guidance for
`/v1/vehicle_utilization`.

## What Changed In This Codebase

### 1. Unit policy status: downgraded, not guessed

`app/motive/vehicle_utilization_unit_policy.py` now exposes:

```
unit_policy_status: LIVE_PROVIDER_UNIT_INDICATOR_SEMANTICS_UNRESOLVED
canonical_request_policy: "X-Metric-Units = true"
canonical_requested_unit_system: "metric"
canonical_request_policy_certified: true
returned_metric_units_boolean_semantics_certified: false
returned_metric_units_must_equal_request_boolean: false
durable_fuel_persistence_enabled: false
unit_conversion_enabled: false
combine_fuel_across_unknown_unit_context: false
```

The certified request-side policy is **unchanged**: Polaris still always
sends `X-Metric-Units: true`. Only the returned-side relationship is now
unresolved.

### 2. Persistence-readiness validator redesign

`validate_vehicle_utilization_unit_persistence_readiness` replaces the
prior `validate_vehicle_utilization_writer_metric_units`. It distinguishes:

- **request unit policy** (certified: Polaris always requests
  `X-Metric-Units: true`), from
- **returned provider unit indicator** (currently unresolved semantics).

Until Motive's returned Boolean semantics are explicitly certified (a
module-level flag, not a guess), **no** returned value -- `True`, `False`,
or `None` -- makes a fuel-bearing rollup ready for durable persistence.
Every value fails closed with the same neutral code,
`provider_unit_indicator_semantics_unresolved`; a structurally malformed
(non-Boolean, non-`None`) value fails closed separately with
`provider_unit_context_invalid_type`, since that is a response-shape
problem, not an open semantics question.

### 3. Read vs. write: parser preserves, writer blocks

Provider schema parse success is now explicitly distinct from durable
persistence readiness. The parser
(`app/connectors/motive_vehicle_utilization.py`) is unchanged: it still
preserves a returned `True`/`False`/`None` `metric_units` value as observed
context and does not reject a payload merely because the Boolean is
`False`. The general certified paginated reader
(`app/connectors/motive_vehicle_utilization_pagination.py`) and the
controlled route's one-page reader
(`app/motive/vehicle_utilization_controlled_write.py`) no longer perform
their own returned-unit-indicator check; the writer transaction
(`app/motive/vehicle_utilization_writer.py`) is now the single place that
fails closed on unresolved returned unit-indicator semantics, before any
commit.

### 4. Controlled route

`POST /api/v1/motive/verify/vehicle-utilization-write` remains
feature-gated off by default (`MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED`)
and was not enabled or invoked during this gate's implementation or tests.
While disabled it still makes zero provider calls. Its error mapping now
recognizes `provider_unit_indicator_semantics_unresolved` (and
`provider_unit_context_invalid_type`) alongside the other writer-originated
fail-closed codes.

### 5. Missing-vehicle, date-window, and pagination status upgrades

Reflecting Motive Support's written confirmation:

- missing requested vehicle: `provider_rollup_absent`, and now
  `missing_rollup_means_no_activity = PROVIDER_CONFIRMED_FALSE` (upgraded
  from `DEFERRED`) -- it still creates no row, no zero metrics, and no
  inactive/no-activity classification.
- `end_date` inclusive, and "at most one aggregate per matching vehicle per
  requested range" are now `PROVIDER_CONFIRMED`.
- `pagination.total` meaning is now `PROVIDER_CONFIRMED_FILTERED_RESULT_ROW_COUNT`.
- provider date-boundary behavior is now `CONFIRMED_PROVIDER_SUPPORT`, and
  `company_configured_default_timezone_used = true`. The exact
  company-configured timezone **value** remains `DEFERRED` --
  `America/Winnipeg` is never claimed to be Motive's configured account
  timezone, and scheduled automatic daily ingestion remains blocked on it.

### 6. Historical rollup mutability: reclassified, not implemented

Motive's confirmation that completed rollups may later differ means a
conflicting historical value is no longer classified as inherently
invalid. The writer's **runtime behavior is unchanged in this gate**:
identical replay stays a no-op, conflicting replay still fails closed, and
updates remain disabled. Only the contract **classification** changes, to
`TEMPORARY_FAIL_CLOSED_PENDING_RECONCILIATION_POLICY`
(`app/motive/vehicle_utilization_writer_contract.py`,
`historical_rollup_mutability`). A future, separately-authorized gate must
design controlled historical refresh/upsert semantics before broad
scheduled ingestion. This PR does not implement updates, does not change
any existing durable row, does not add a version table, and does not add
audit-history schema.

### 7. Live validation status: executed, not "not executed"

`production_validation_executed` changes from `false` to a precise,
sanitized, static state:

```
production_validation_executed: true
production_validation_succeeded: false
production_validation_persisted_rows: false
production_validation_failure_stage: unit_context_readiness
production_validation_provider_calls: 1
production_validation_returned_rollups: 1
production_validation_error_code: provider_unit_policy_mismatch
production_validation_safe_failure: true
```

## Remaining Blockers

After this gate:

1. returned `vehicle.metric_units` Boolean semantics must be explicitly
   certified before fuel metrics can be durably persisted
2. historical-rollup reconciliation/update policy must be designed before
   broad rolling-window synchronization
3. checkpoint advancement implementation remains disabled
4. exact company-configured Motive timezone value must be confirmed before
   scheduled daily ingestion

## No Live Calls In This Gate

This gate makes **zero** live Motive HTTP calls anywhere -- not during
implementation, not during testing. All tests mock provider responses. The
one real controlled production validation described above was executed by
a human operator, outside this gate's session, before this reconciliation
work began; it is recorded here as sanitized evidence only, never
re-executed or re-verified live.

## Update: Unit Semantics Certification Gate (2026-08-16)

A follow-up gate reviewed current official Motive developer documentation
(`developer-docs.gomotive.com`) specifically to try to resolve whether
`X-Metric-Units` controls returned fuel-value units independent of the
returned `vehicle.metric_units` field for `GET /v1/vehicle_utilization`. It
found no reconciling statement on Motive's official reference page for this
endpoint -- the ambiguity documented above stands. That gate:

- keeps every certification/readiness flag on this page exactly as recorded
  above (no behavior change);
- formalizes the request-vs-response distinction with explicit names
  (`requested_measurement_system`, `vehicle_configured_metric_preference`,
  `response_measurement_system_certification`) in
  `app/motive/vehicle_utilization_unit_policy.py`;
- adds an additive `unit_semantics` block to the writer contract;
- documents (without migrating) that the persisted `metric_units` column
  stores raw provider-observed vehicle metadata, not certified fuel-unit
  provenance;
- prepares (but does not send) a provider clarification email draft.

See `MOTIVE_UTILIZATION_UNIT_SEMANTICS_CERTIFICATION.md` for the full
sourced documentation review, conclusion, and draft clarification email.

## Update: Authentication + Unit-Mismatch Certification Gate (2026-08-17)

Motive API Support's written reply on 2026-08-17 directly answered the
question this document's Section A left open. **Reclassification of the
2026-08-16 production evidence above**, sanitized facts unchanged:

| Field | Value (unchanged) |
| --- | --- |
| `production_validation_executed` | `true` |
| `production_validation_succeeded` | `false` |
| `provider_calls` | `1` |
| `returned_rollups` | `1` |
| `records_inserted` | `0` |
| `checkpoint_advanced` | `false` |
| `sync_history_written` | `false` |
| `safe_failure` | `true` |

| Classification | Value |
| --- | --- |
| Previous | `SEMANTICS_UNRESOLVED` |
| **Current** | **`PROVIDER_CONFIRMED_UNIT_CONTEXT_MISMATCH`** |

Motive Support confirmed that `X-Metric-Units=true` together with a
returned `vehicle.metric_units=false` is **not** an expected/documented
combination for `GET /v1/vehicle_utilization`, and that integrations must
fail closed and not persist fuel values when the requested and returned
unit context disagree. The single live observation recorded in Section A
above is exactly this combination. It is therefore no longer an open
semantics question -- it is a provider-confirmed mismatch that the route
correctly, and now provably-intentionally, failed closed on. No new
conclusion is drawn about *why* the mismatch occurred (a different
vehicle-level preference, an account-level setting, or something else);
only that Motive confirmed the combination is unexpected and that failing
closed was the correct response.

`app/motive/vehicle_utilization_writer_contract.py`'s
`PRODUCTION_WRITE_VALIDATION_EVIDENCE` and
`controlled_manual_write_validation` blocks now carry an explicit
`classification: "PROVIDER_CONFIRMED_UNIT_CONTEXT_MISMATCH"` field
(`production_validation_classification` in the latter) alongside the
unchanged `error_code: "provider_unit_policy_mismatch"` and all of the
sanitized counters in the table above.

See `docs/engineering/MOTIVE_UTILIZATION_UNIT_SEMANTICS_CERTIFICATION.md`
for the full provider-confirmed semantics upgrade (request/response
consistency rule, durable-persistence-readiness table, and the retired
`LIVE_PROVIDER_UNIT_INDICATOR_SEMANTICS_UNRESOLVED` status), and
`docs/engineering/MOTIVE_AUTHENTICATION_CERTIFICATION.md` for the
authentication half of this gate. This update makes **no** live Motive API
call, rotates no credential, and adds no database migration.
