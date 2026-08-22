# Motive Vehicle Utilization Operational Observability Design

## Status

Design gate only. This document does not change production runtime behavior, make provider calls, mutate Motive data, advance checkpoints, consume scheduler claims, or change feature flags.

## Context

Track 4C vehicle-utilization ingestion is now running automatically in production. The scheduler has been validated in automatic mode with one same-local-day execution acquiring the durable dispatch claim and a later wakeup returning `already_claimed` without duplicate provider execution.

The remaining operational gap is that administrators must currently combine GitHub Actions evidence with backend implementation knowledge to determine whether the latest production ingestion completed, how far the durable checkpoint advanced, and whether the current local-day scheduler claim was consumed.

The existing persistence already contains the required operational evidence:

- `MotiveSyncHistory` stores one sanitized production-ingestion history row per orchestrated run for `provider_resource=vehicle_utilization` and `mode=production_recent_window_ingestion`.
- `MotiveSyncCheckpoint` stores the durable production checkpoint for `provider_resource=vehicle_utilization`.
- `MotiveSyncCheckpoint` also stores the scheduler same-local-day dispatch claim under `provider_resource=vehicle_utilization_scheduler_dispatch`.

No new database table is required for this observability slice.

## Proposed authenticated read-only endpoint

Add:

`GET /api/v1/motive/vehicle-utilization/operations-status`

Authorization:

- require `Permission.CONNECTOR_READ`;
- organization is always taken from the authenticated principal;
- no caller-supplied organization id or slug;
- no machine/HMAC authentication path is added to this endpoint.

This endpoint is read-only and must perform zero Motive provider HTTP calls.

## Response contract

Return a compact sanitized object with these top-level sections.

### `production`

From the latest tenant-owned `MotiveSyncHistory` row where:

- `provider = motive`
- `provider_resource = vehicle_utilization`
- `mode = production_recent_window_ingestion`

Expose only:

- `status`
- `started_at`
- `completed_at`
- `records_read`
- `records_written`
- `error_code`
- selected allow-listed values from `resource_counts`:
  - `horizon_days`
  - `request_timezone`
  - `unit_request_mode`
  - `fuel_unit`
  - `selected_vehicle_count`
  - `windows_attempted`
  - `windows_completed`
  - `windows_failed`
  - `provider_calls_attempted`
  - `provider_calls_completed`
  - `rollups_returned`
  - `missing_requested_vehicle_count`
  - `records_inserted`
  - `records_unchanged`
  - `records_updated`
  - `reconciled_fields_count`
  - `checkpoint_advanced`

Do not expose raw provider payloads, run identifiers unless separately justified, database ids, secrets, request headers, provider vehicle ids, exception strings, or unrestricted JSON blobs.

If no production history exists, return a stable `not_started` representation rather than a 404.

### `checkpoint`

From the tenant-owned `MotiveSyncCheckpoint` row where `provider_resource=vehicle_utilization`, expose only:

- `status`
- `last_successful_sync_at`
- `completed_through`
- `request_timezone`
- `unit_request_mode`
- `fuel_unit`

The endpoint must parse `last_successful_position` defensively and allow only those keys. If the row does not exist, return `not_started` with null positions.

### `scheduler`

From the tenant-owned `MotiveSyncCheckpoint` row where `provider_resource=vehicle_utilization_scheduler_dispatch`, expose only:

- `claim_status`
- `claimed_local_date`
- `claim_recorded_at`
- `request_timezone`
- `scheduler_mode`

The scheduler claim is evidence only that a local-day dispatch was consumed. It must never be described as proof that production ingestion succeeded. Production success is determined from the production history/checkpoint sections.

If no scheduler claim exists, return `not_claimed` with null date/time fields.

### `configuration`

Expose safe booleans only:

- `production_ingestion_enabled`
- `production_scheduler_enabled`
- `controlled_validation_window_enabled`

Do not expose configured secret values, API keys, HMAC secrets, environment values, organization slug environment contents, or deployment-provider metadata.

### safety marker

Always include:

`"secrets_exposed": false`

## Derived health classification

The endpoint may return a simple deterministic `operational_status` derived only from persisted/safe configuration state:

- `healthy`: latest production history is `success`, production checkpoint indicates `success`, and the checkpoint's `completed_through` equals the latest production history checkpoint-after `completed_through` when available.
- `degraded`: latest production history is `partial` or `failed`, or the production checkpoint is absent/stale relative to an available successful history row.
- `not_started`: no production history and no production checkpoint exist.

Do not classify the system as unhealthy merely because the current local day has not yet been claimed before the scheduled window. Do not infer provider health from scheduler-claim state alone.

A later implementation may add schedule-age/staleness rules, but this first slice should avoid clock-based alert semantics until those thresholds are separately reviewed.

## Tenant isolation

Every history/checkpoint query must filter by `principal.organization_id` before resource/mode filtering. The endpoint must never return another organization's Motive operational metadata.

Tests must include a cross-tenant case proving that a newer row belonging to another organization cannot become the returned latest record.

## Failure behavior

Database read failures should return a sanitized 500 error with a stable error code such as `motive_operational_status_read_failed` and no exception text.

Because this route is observational only:

- no retry loop;
- no writes;
- no commits;
- no checkpoint mutation;
- no scheduler claim mutation;
- no provider request;
- no fallback that synthesizes success.

## Test matrix for implementation gate

At minimum:

1. requires `CONNECTOR_READ`;
2. returns `not_started` safely when no rows exist;
3. latest tenant-owned production history is selected deterministically;
4. production allow-list excludes unrestricted `resource_counts` keys;
5. production checkpoint safe fields are exposed correctly;
6. scheduler claim safe fields are exposed correctly;
7. scheduler claim without successful production history does not report `healthy`;
8. successful history plus matching successful checkpoint reports `healthy`;
9. failed/partial latest history reports `degraded`;
10. cross-tenant rows are never returned;
11. endpoint performs zero provider calls and zero database writes;
12. response always contains `secrets_exposed=false`;
13. database exceptions are sanitized.

## Non-goals

This gate does not:

- add Dashboard or Daily Brief UI;
- send alerts or emails;
- add a monitoring scheduler;
- change GitHub Actions;
- change Motive ingestion/scheduler timing;
- change retry behavior;
- change provider request units, timezone, pagination, horizon, or omission semantics;
- rotate credentials;
- add a new Motive provider domain.

## Recommended rollout

1. Merge this design gate.
2. Implement the authenticated read-only endpoint and focused tests in a separate PR.
3. Run CI.
4. Perform one authenticated production GET only; it must make zero Motive provider calls.
5. Compare returned production/checkpoint/scheduler evidence against the already-observed automatic scheduler cycle.
6. Only after the endpoint is certified should Track 4C consumer integration use it for System Health, Dashboard, or Daily Brief surfaces.
