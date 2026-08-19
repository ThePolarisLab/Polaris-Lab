# Motive Vehicle Utilization Recent-Window Reconciliation: One-Day Controlled Live-Staging Validation

## Status

Implementation-only. **This PR makes NO live Motive provider call.** Both
required feature flags default to disabled and neither is enabled anywhere
in this change, including Render. Live execution against staging is a
separate, later, explicitly human-authorized action, not part of this gate.

## Purpose

Provide the smallest safe, feature-gated mechanism that allows exactly ONE
manually-authorized live-staging invocation of the recent-window
reconciliation runner (`app/motive/vehicle_utilization_recent_reconciliation.py`,
merged in PR #177) with `horizon_days=1`, so that a human operator can prove
the runner works against real Motive data before any broader (multi-day,
multi-batch, scheduled, or checkpointed) execution is ever considered.

This is a validation mechanism, not a production sync route. It is
controlled and manual only:

- it is NOT a general reconciliation endpoint;
- it is NOT a sync endpoint;
- it is NOT a scheduler trigger;
- it is NOT a user-configurable broad backfill route.

## Route

```
POST /api/v1/motive/verify/vehicle-utilization-recent-reconciliation
```

Implemented in `chief-of-staff/backend/app/api/motive.py`
(`verify_motive_vehicle_utilization_recent_reconciliation`), orchestrated by
`chief-of-staff/backend/app/motive/vehicle_utilization_recent_reconciliation_validation.py`
(`run_recent_vehicle_utilization_reconciliation_live_validation`), which
calls the real, unmodified runner
(`run_recent_vehicle_utilization_reconciliation`) with `horizon_days`
hardcoded to `1`.

## Authorization Requirements

All of the following are required, checked in this order:

1. Authenticated Polaris principal with `CONNECTOR_WRITE` permission
   (`Depends(require_permission(Permission.CONNECTOR_WRITE))`).
2. **Both** feature flags explicitly true:
   - `MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_ENABLED` -- the
     runner's own existing feature gate (added by PR #177).
   - `MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_VALIDATION_ENABLED` --
     this route's own, genuinely separate, additional gate.

   Neither flag implies the other. Both default to `false`. Runner
   enablement alone does NOT expose this route; route enablement alone does
   NOT bypass the runner's own gate (the runner still checks its own flag
   internally, first, before anything else).
3. An explicit `confirm: true` JSON request body.

Request body (the ONLY accepted field):

```json
{"confirm": true}
```

The route does **not** accept, and will not use even if supplied:
`horizon_days`, any date range, vehicle IDs, batch size, page size, retry
options, `organization_id`, or any other parameter. The authenticated
tenant and hardcoded constants control everything.

## Hard Live Bounds

| Bound | Value |
| --- | --- |
| `horizon_days` | hardcoded `1` (never caller-supplied) |
| Max calendar windows | 1 |
| Max vehicle batches | 1 |
| Max selected vehicles | 100 |
| Max pages per unit | 1 |
| Max provider calls | 1 |
| Automatic retries | none |

Before invoking the runner, the route counts the tenant's eligible vehicles
(via the runner's own tenant-scoped selection query, called directly -- no
runner behavior change) and fails closed **before any provider HTTP
request** if that count exceeds 100. It does not truncate silently to 100,
does not select only the first 100, and does not make multiple calls to
cover the rest. This is a stricter, route-owned bound than the runner's own
general-purpose 200-call safety budget, because this route is a one-call
proof, not a fleet-scale execution.

After the runner returns, the route independently re-verifies that
`provider_calls_attempted <= 1`. This should be structurally impossible to
violate given the hardcoded one-day horizon and the pre-flight vehicle
count bound above; if it is ever violated, the route treats it as a genuine
invariant violation and fails closed (HTTP 500), never retrying.

## Date / Window

Uses the runner's existing horizon logic unmodified. `horizon_days=1` means
exactly the most recent completed calendar day, using the same
non-provider-certified Polaris request-window timezone convention every
existing Motive utilization caller uses
(`MOTIVE_VEHICLE_UTILIZATION_REQUEST_WINDOW_TIME_ZONE`). "Today" is never
included. The caller cannot supply a date. No `X-Time-Zone` header is added,
and the date basis is not claimed to be provider-certified timezone
binding.

## Unit Mode

The runner continues to use
`MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT` unmodified: no
`X-Metric-Units` header, no unit conversion. The returned `metric_units`
Boolean is persisted as observed context; a missing or malformed indicator
fails closed at the writer's persistence-readiness gate, and an immutable
existing-row unit conflict also fails closed. This route does not claim the
outcome will be metric or imperial.

## Response Shape (Sanitized)

```json
{
  "status": "success | no_op | failed",
  "resource": "vehicle_utilization_recent_reconciliation_live_validation",
  "validation_mode": "controlled_manual_recent_reconciliation_live_validation",
  "horizon_days": 1,
  "windows_attempted": 0,
  "windows_completed": 0,
  "windows_failed": 0,
  "selected_vehicle_count": 0,
  "vehicle_batches_attempted": 0,
  "vehicle_batches_completed": 0,
  "vehicle_batches_failed": 0,
  "provider_calls_attempted": 0,
  "provider_calls_completed": 0,
  "rollups_returned": 0,
  "missing_requested_vehicle_count": 0,
  "records_inserted": 0,
  "records_unchanged": 0,
  "records_updated": 0,
  "reconciled_fields_count": 0,
  "checkpoint_advanced": false,
  "sync_history_written": false,
  "scheduled_ingestion_enabled": false,
  "secrets_exposed": false,
  "failed_units": []
}
```

`checkpoint_advanced`, `sync_history_written`, and
`scheduled_ingestion_enabled` are always `false` on every outcome -- this
route never mutates `MotiveSyncCheckpoint`, never writes
`MotiveSyncHistory`, and is never wired to a scheduler. `failed_units`
(when non-empty) contains only sanitized `window_start` / `window_end` /
`batch_ordinal` / `error_code` entries, reused verbatim from the runner's
own sanitized failure contract -- never a vehicle identity.

The response never includes: provider vehicle IDs, database IDs, VINs,
driver PII, raw metrics, raw provider payloads, raw headers, API keys, or
bearer tokens.

## HTTP Status Mapping

| Status | Meaning |
| --- | --- |
| `200` | success, or `no_op` when zero eligible tenant vehicles (zero provider calls) |
| `400` | `confirm` missing or not `true` |
| `403` | missing `CONNECTOR_WRITE` permission |
| `409` | tenant has more than 100 eligible vehicles (fails closed before any provider HTTP) |
| `503` | either required feature flag is disabled |
| `502` | a known, already-typed, safe provider/pagination/unit/writer operational failure that actually attempted the one provider call |
| `500` | a genuine unexpected/invariant programming failure only (never an expected, safely-caught, sanitized error) |

`partial_success` is not expected to occur through this route in practice
(it has exactly one unit of work: one day x one batch), but is defensively
mapped to `502` alongside `failed` if it is ever observed.

No exception message is ever leaked in a response body; every error detail
is a hand-built, sanitized dict.

## Zero-Vehicle Case

If the tenant has zero eligible Motive vehicles: zero provider calls, zero
database writes, a sanitized `no_op`/success response (HTTP 200). This is
never treated as a provider failure. Checkpoint and sync-history state are
left untouched (they are never written by this route regardless).

## Checkpoint / History / Scheduler

This route never advances `MotiveSyncCheckpoint`, never writes
`MotiveSyncHistory`, and adds no scheduler, cron, or background worker of
any kind. Every response always reports `checkpoint_advanced=false`,
`sync_history_written=false`, and `scheduled_ingestion_enabled=false`.

## Operational Procedure for a Real Live-Staging Validation (Not Part of This PR)

This PR does not perform a live validation. When a human operator later
decides to run the real, one-time live-staging validation described here,
the procedure is:

1. Confirm the tenant has at most 100 eligible Motive vehicles in staging.
2. Set `MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_ENABLED=true` in
   the staging environment only.
3. Set
   `MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_VALIDATION_ENABLED=true`
   in the staging environment only.
4. Call `POST /api/v1/motive/verify/vehicle-utilization-recent-reconciliation`
   with `{"confirm": true}` and `CONNECTOR_WRITE` credentials exactly once.
5. Record the sanitized response (status, counters, any `failed_units`).
6. **Immediately set both flags back to `false`** in staging. Do not leave
   either flag enabled after the validation completes.

No 7-day (or any horizon other than the hardcoded 1) live execution is
authorized by this document or this PR. A broader live horizon requires its
own, separately reviewed and authorized gate.
