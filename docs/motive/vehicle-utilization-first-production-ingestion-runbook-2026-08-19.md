# Motive vehicle-utilization first production-ingestion runbook

Date prepared: 2026-08-19

## Purpose

This runbook authorizes one controlled manual production-ingestion attempt against the bounded route merged in PR #187. It does not authorize scheduling, cron, repeated retries, broad Motive synchronization, Dashboard/Daily Brief changes, or any additional live validation route.

## Certified runtime contract

The production route is:

`POST /api/v1/motive/sync/vehicle-utilization`

Request body:

```json
{"confirm": true}
```

The caller cannot choose dates, timezone, units, vehicle ids, pagination, retries, horizon, or organization.

The production implementation is bounded to:

- the latest 7 completed `America/Chicago` calendar days;
- at most 100 organization-owned stored Motive vehicles;
- one request page per day;
- at most 7 Motive provider calls for the run;
- no automatic retries;
- explicit `X-Metric-Units: false`;
- returned `vehicle.metric_units == false` required before persistence;
- fuel values treated as gallons;
- no unit conversion;
- provider omissions remain omissions and are never converted into zero/inactive rows.

## Required safety state before the attempt

Keep every unrelated Motive write/reconciliation validation gate disabled.

Required values before preflight:

```text
MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED=false
MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED=false
MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_ENABLED=false
MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_VALIDATION_ENABLED=false
MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_SEVEN_DAY_VALIDATION_ENABLED=false
MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED=false
```

No scheduler exists in the current runtime gate. The scheduler variable must still remain false.

## Zero-provider-call preflight

Do not enable the production-ingestion flag until all of these checks pass.

1. Confirm deployed backend health is HTTP 200 at `/health`.
2. Confirm deployed OpenAPI contains `POST /api/v1/motive/sync/vehicle-utilization`.
3. Log in through the normal Polaris frontend so the browser has a current authenticated session. Do not reuse a known-expired bearer token from an earlier browser console session.
4. Read `GET /api/v1/motive/status` through the authenticated application boundary. This endpoint uses connector configuration/persisted status only; it does not call Motive. Confirm:
   - Company API Key is reported present/configured;
   - connection is not marked `authorization_required`;
   - `secrets_exposed` is false.
5. Confirm the production-ingestion feature flag is still false during all preflight checks.

Do not call `/api/v1/motive/verify` as part of this preflight because that route intentionally makes a Motive provider request.

## Enablement immediately before the attempt

Only after the zero-provider-call preflight passes:

```text
MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED=true
MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED=false
```

Leave every older validation/controlled-write/reconciliation flag false.

Wait for the Render service to be live with the new environment value before proceeding.

## The one authorized POST

Make exactly one newly authorized request:

```text
POST https://polaris-executive-api.onrender.com/api/v1/motive/sync/vehicle-utilization
Content-Type: application/json
Authorization: Bearer <current authenticated Polaris token>

{"confirm":true}
```

Do not paste, log, screenshot, or store the bearer token or Motive API key in the repo, chat, screenshots, or runbook evidence.

### One-attempt rule

Once the POST has been sent, the attempt is consumed.

If the browser reports a timeout, network ambiguity, lost response, page refresh, or other uncertain client-side outcome after the request may have left the browser, **do not submit the POST again**. Treat it as an attempted production run and inspect durable sync-history/checkpoint evidence before deciding any future action.

There is no automatic retry in the backend production orchestrator. Do not manually compensate by clicking or submitting twice.

## Expected sanitized success evidence

A successful response should show only sanitized counters/context, including:

- `status: success`
- `resource: vehicle_utilization`
- `run_mode: production_recent_window_ingestion`
- `horizon_days: 7`
- `request_timezone: America/Chicago`
- `unit_request_mode: imperial`
- `fuel_unit: gallons`
- `x_metric_units: false`
- `selected_vehicle_count <= 100`
- `windows_attempted: 7`
- `windows_completed: 7`
- `windows_failed: 0`
- `provider_calls_attempted <= 7`
- `provider_calls_completed == provider_calls_attempted`
- `checkpoint_advanced: true`
- `sync_history_written: true`
- `scheduled_ingestion_enabled: false`
- `secrets_exposed: false`
- `failed_units: []`

Provider omission counts may be non-zero and are not a failure by themselves.

## Partial or failed outcomes

### Partial success

HTTP 207 / `status: partial_success` means at least one daily window committed and at least one daily window failed.

Expected safety behavior:

- already committed daily-window writes remain committed;
- checkpoint does not advance;
- one sanitized sync-history record is written;
- no failed unit is retried automatically;
- do not rerun the POST without a new, separately reviewed authorization.

### Safe provider/runtime failure

HTTP 502 or another sanitized failure response must be treated as the completed attempt. Do not rerun automatically.

### Conflict / concurrency rejection

HTTP 409 for an already-running production run or vehicle-limit/precondition conflict means no second provider run should be started to work around the rejection. Investigate the cause first.

### Authentication rejection

If the request is rejected before authenticated route execution (for example an expired Polaris bearer credential), do not reuse that same request as evidence of Motive ingestion. Refresh/login first. Any later POST is a separate attempt and requires separate authorization.

## Immediate shutdown after the attempt

As soon as the single attempt returns or becomes client-side ambiguous, set:

```text
MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED=false
MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED=false
```

Confirm the Render service is live again with both values false.

Keep all older Motive validation and controlled-write flags false.

## Evidence to record after the attempt

Record only sanitized evidence:

- date/time of attempt;
- route and HTTP status;
- response status;
- horizon/timezone/unit mode;
- selected vehicle count;
- windows attempted/completed/failed;
- provider calls attempted/completed;
- rollups returned;
- missing requested-vehicle count;
- inserted/unchanged/updated record counts;
- reconciled-fields count;
- checkpoint advanced yes/no;
- sync history written yes/no;
- failed-unit safe error codes, if any;
- confirmation that scheduling remained disabled;
- confirmation that no secrets were exposed;
- confirmation that the production-ingestion flag was returned to false.

Never record provider vehicle IDs, VINs, raw metric values, raw provider payloads, API keys, bearer tokens, or Authorization headers.

## Exit criteria

The first production-ingestion gate is successful only when:

1. the single authorized run completes safely;
2. durable sync history exists for the run;
3. checkpoint advancement behavior matches the result status;
4. no provider identity/secret/raw payload is exposed;
5. production-ingestion and scheduler flags are false again;
6. the evidence is committed in a separate docs-only PR before any scheduler work begins.

## Explicitly deferred

This runbook does not authorize:

- a second production-ingestion POST;
- a retry after an ambiguous attempt;
- scheduler/cron implementation or enablement;
- broader historical backfill;
- increasing the 7-day horizon or 100-vehicle limit;
- changing unit mode away from explicit imperial;
- Dashboard/Daily Brief interpretation of missing provider rollups;
- broad production enablement before Motive API-key rotation.

Motive API-key rotation remains mandatory before scheduled/broad production enablement.