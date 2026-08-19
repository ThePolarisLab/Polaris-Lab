# Motive vehicle-utilization first production-ingestion success

Date: 2026-08-19

## Outcome

The first separately authorized bounded production-ingestion attempt for Motive vehicle utilization completed successfully against the production route introduced in PR #187 and operated under the runbook merged in PR #188.

The attempt is complete and must not be rerun as the same authorization.

## Route and authorization boundary

Route:

`POST /api/v1/motive/sync/vehicle-utilization`

Request body:

```json
{"confirm": true}
```

The request was made exactly once after the zero-provider-call preflight passed and after only the production-ingestion feature gate was enabled. The production scheduler remained disabled.

## Preflight evidence

Before the production request:

- backend `/health` returned HTTP 200;
- deployed OpenAPI returned HTTP 200;
- the production route was present in OpenAPI;
- the normal Polaris authenticated browser session had both an access token and organization context present;
- `GET /api/v1/motive/status` returned HTTP 200;
- Motive connector status was `connected`;
- `authorization_required` was false;
- Company API Key was reported present;
- `secrets_exposed` was false.

The preflight did not call `/api/v1/motive/verify` and did not intentionally make a Motive provider request.

## Successful production result

The one authorized production-ingestion request returned HTTP 200 with `status: success`.

Sanitized evidence:

```text
status: success
resource: vehicle_utilization
run_mode: production_recent_window_ingestion
horizon_days: 7
request_timezone: America/Chicago
unit_request_mode: imperial
fuel_unit: gallons
x_metric_units: false
selected_vehicle_count: 23
windows_attempted: 7
windows_completed: 7
windows_failed: 0
provider_calls_attempted: 7
provider_calls_completed: 7
rollups_returned: 72
missing_requested_vehicle_count: 89
records_inserted: 11
records_unchanged: 0
records_updated: 61
reconciled_fields_count: 181
checkpoint_advanced: true
sync_history_written: true
scheduled_ingestion_enabled: false
secrets_exposed: false
failed_units: []
```

## Interpretation

All seven completed `America/Chicago` daily windows completed successfully. The backend completed all seven authorized provider calls and reported no failed windows or failed units.

The explicit production unit contract was honored: `X-Metric-Units: false`, returned/requested mode `imperial`, and fuel unit `gallons`. No unit conversion was requested or performed by this production contract.

The `missing_requested_vehicle_count: 89` value remains provider omission evidence only. It must not be interpreted as zero utilization, inactivity, an inactive business state, or synthesized rows.

Persistence behavior matched the production gate contract:

- 11 records were inserted;
- 61 existing records were reconciled/updated;
- 181 provider-reconcilable fields changed;
- one sanitized sync-history record was written;
- the production checkpoint advanced because all seven windows completed successfully.

No scheduler was enabled and no secrets were exposed in the sanitized response evidence.

## Immediate shutdown evidence

After the one authorized request completed, the Render environment was returned to the safe state and confirmed live:

```text
MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED=false
MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED=false
```

The older Motive controlled-write and reconciliation-validation gates also remain false.

## Closed authorization

This production attempt is complete. Do not run `POST /api/v1/motive/sync/vehicle-utilization` again under this authorization.

Any future manual production attempt requires a separate authorization and fresh preflight. Scheduler/cron implementation or enablement remains a separate gate.

## Next gate

This successful first production-ingestion result closes the manual production-ingestion proof milestone. Before any broad or scheduled production enablement:

1. keep production ingestion and scheduler flags default-off;
2. preserve the 7-day / 100-vehicle / 7-call / no-retry safety boundaries unless separately redesigned;
3. preserve `America/Chicago` local calendar-day semantics and explicit imperial request mode;
4. preserve provider omissions as omissions only;
5. rotate the Motive Company API Key before broad/scheduled production enablement;
6. design, review, test, and merge scheduler behavior separately before any scheduler flag is enabled.

No scheduler, cron, Dashboard, Daily Brief, historical backfill, key rotation, or additional provider call is performed by this documentation change.
