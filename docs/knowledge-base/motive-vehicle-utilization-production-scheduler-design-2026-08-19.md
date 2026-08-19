# Motive vehicle-utilization production scheduler design — 2026-08-19

## Current state
The first controlled production-ingestion run has succeeded and is documented in PR #189. The production ingestion and scheduler flags are both back to false. No scheduled Motive ingestion is currently enabled.

## Proposed scheduler boundary
A later implementation may add a disabled-by-default GitHub Actions schedule that calls a Motive-specific HMAC-authenticated Polaris backend endpoint. The backend resolves one configured active organization and invokes the existing bounded vehicle-utilization production orchestrator.

The scheduler must not create a second ingestion implementation. Existing production rules remain unchanged: latest seven completed `America/Chicago` days, maximum 100 vehicles, maximum seven provider calls, no automatic provider retries, explicit `X-Metric-Units: false`, returned `vehicle.metric_units == false`, gallons, no unit conversion, provider omissions remain omissions, and success-only ingestion checkpoint advancement.

## Proposed daily time
Target approximately 06:17 `America/Chicago`.

Because GitHub cron uses UTC, the workflow should have two UTC schedules:

```text
17 11 * * *
17 12 * * *
```

The backend uses IANA `America/Chicago` time rules and only permits execution during the reviewed 06:xx local window. The nonmatching UTC trigger is a safe zero-provider no-op. This preserves the same local schedule across CDT and CST without fixed-offset assumptions.

## Required machine authentication
Use a Motive-specific HMAC secret, separate from the Motive API key and ACE cron secret. The machine endpoint must not use Polaris user bearer tokens and must not accept organization/date/vehicle/unit/retry controls from the request.

Proposed Render-only values:

```text
POLARIS_MOTIVE_UTILIZATION_SCHEDULED_ORGANIZATION_SLUG
POLARIS_MOTIVE_UTILIZATION_CRON_TRIGGER_SECRET
```

The HMAC secret should also exist in GitHub Actions secret storage for signing the request. Neither value should be committed or logged.

## Required feature gates
A scheduled run may reach Motive only when both are true:

```text
MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED=true
MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED=true
```

Either flag false means zero Motive calls from the scheduler path. The implementation PR itself must leave both flags default-off.

## Same-day duplicate protection
The existing organization production lock prevents overlap but does not prevent a later duplicate run after the first has finished. The scheduler therefore needs a separate durable local-day dispatch claim, preferably using a distinct existing checkpoint resource such as:

```text
vehicle_utilization_scheduler_dispatch
```

The claim is recorded before any Motive call. Once a local day is claimed, a second scheduled trigger for that day makes zero provider calls. The claim remains consumed even if the production run later fails or becomes ambiguous. There is no same-day scheduler retry.

The scheduler dispatch marker is separate from the production ingestion checkpoint and never determines the seven-day fetch range.

## Retry policy
No automatic retries in GitHub or backend scheduler code. No catch-up loop after a missed trigger. Partial/failed ingestion waits for the next normal daily schedule, which rereads the latest seven completed days.

## Security and observability
Scheduled responses/logs may expose only sanitized status/counters. Never expose organization identity, vehicle IDs, VINs, metric values, raw payloads, Motive API keys, HMAC secrets, GitHub tokens, database credentials, or authorization headers.

The existing `MotiveSyncHistory` row remains the single parent ingestion history record. Scheduler dispatch state is only an at-most-once marker.

## API-key rotation gate
The scheduler may be implemented while disabled, but **no live scheduler execution or persistent scheduled enablement is allowed until the Motive Company API Key has been rotated in secure Render configuration** and a zero-write status/config preflight has passed.

## Next implementation scope
The next runtime PR should be limited to the Motive-specific HMAC endpoint, scheduled-organization resolver, `America/Chicago` execution-window gate, durable same-day dispatch claim, reuse of the existing production orchestrator, the two-UTC-entry GitHub Actions workflow with no retry, sanitized output, and focused tests.

No Render enablement, live Motive call, API-key disclosure, retry/backoff, historical backfill, multi-organization fan-out, Dashboard/Daily Brief change, or production contract change is authorized by this design.