# Motive Vehicle Utilization Production Scheduler Design

## Status
Design only. This document does not add a scheduler, cron workflow, machine endpoint, provider call, Render change, GitHub secret, API-key rotation, or production enablement.

## Evidence entering this gate
The first controlled production-ingestion run completed successfully and is recorded in PR #189: HTTP 200, 7/7 `America/Chicago` daily windows completed, 7/7 provider calls completed, 72 rollups returned, 11 inserted, 61 updated, 0 unchanged, 181 reconciled fields, checkpoint advanced, sync history written, zero failed units, scheduler disabled, and no secrets exposed. Both production flags were returned to false after the run.

The existing production orchestrator remains the execution authority. Scheduler work must not fork, duplicate, or weaken its certified behavior:

- latest seven completed `America/Chicago` calendar days;
- never the current in-progress local day;
- maximum 100 organization-owned vehicles;
- maximum seven Motive provider calls per run;
- one page per daily window;
- no automatic provider retries;
- explicit `X-Metric-Units: false`;
- returned `vehicle.metric_units == false` required before persistence;
- gallons, no unit conversion;
- provider omissions remain omissions only;
- one writer transaction per daily window;
- one sanitized parent sync-history row per orchestrated ingestion run;
- ingestion checkpoint advances only after all seven windows succeed and history is durable;
- organization-scoped production-run concurrency exclusion.

## Objective
Add, in a later implementation PR, a disabled-by-default machine trigger that invokes the already validated production orchestrator once per `America/Chicago` local day without introducing bearer-token automation, provider retries, duplicate same-day runs, timezone drift, or a second ingestion path.

## Scheduler architecture
Use the same general no-additional-cost scheduling boundary already used by Polaris ACE, but with Motive-specific secrets, tenant targeting, and stricter no-retry behavior:

```text
GitHub Actions scheduled trigger
-> HMAC-authenticated Motive scheduler endpoint
-> backend resolves one configured active organization
-> local-time / same-day dispatch gate
-> existing vehicle-utilization production orchestrator
-> existing writer + sync history + ingestion checkpoint
```

GitHub is only the clock and wake-up mechanism. It must not receive the Motive Company API Key, database credentials, organization IDs/slugs, provider vehicle IDs, utilization values, Polaris user tokens, or raw provider data.

## Machine endpoint
Proposed endpoint:

```text
POST /api/v1/internal/motive/vehicle-utilization/run
```

The endpoint is machine-only. It must not accept organization ID or slug, dates, horizon, vehicle IDs, page size, timezone, unit mode, retry options, Motive credentials, or Polaris user bearer tokens from the request.

The backend resolves the target organization from a Render-only configuration value, proposed:

```text
POLARIS_MOTIVE_UTILIZATION_SCHEDULED_ORGANIZATION_SLUG
```

Resolution must fail closed unless that value maps to exactly one active organization.

## HMAC authentication
Use a Motive-specific trigger secret, separate from ACE and from the Motive API key:

```text
POLARIS_MOTIVE_UTILIZATION_CRON_TRIGGER_SECRET
```

Required request headers:

```text
X-Polaris-Job-Timestamp
X-Polaris-Job-Signature
```

Use lowercase-hex HMAC-SHA256 over the same canonical structure already established for the ACE machine trigger:

```text
HTTP_METHOD_UPPERCASE
REQUEST_PATH
UNIX_TIMESTAMP_SECONDS
SHA256_HEX_OF_REQUEST_BODY
```

The scheduled request body should be empty. The backend must reject missing configuration, malformed/stale/future timestamps, malformed signatures, mismatched signatures, and unexpected request bodies before any provider call.

The HMAC secret must exist only in Render and GitHub Actions secret storage. It must never be committed or logged.

## Feature-gate policy
Both production controls must be true for a scheduled ingestion to reach the orchestrator:

```text
MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED=true
MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED=true
```

Safety behavior:

- scheduler flag false -> sanitized disabled/no-op result with zero Motive calls;
- ingestion flag false -> sanitized disabled/no-op result with zero Motive calls;
- scheduler true while ingestion false must never bypass the ingestion gate;
- manual/admin route remains governed by the ingestion flag and is not implicitly invoked by scheduler configuration;
- older controlled-write/reconciliation validation flags remain unrelated and false.

The scheduler implementation PR must leave both flags default-off and must not change Render values.

## Local schedule
Initial target: once per local day at approximately 06:17 `America/Chicago`.

Why 06:17:

- it is well after the prior local calendar day has completed;
- it preserves the existing design intent of an approximately 06:00 Central run;
- minute 17 avoids the top-of-hour GitHub Actions load window;
- the ingestion itself always recomputes the latest seven completed local days, so it does not depend on a fixed UTC offset.

GitHub Actions cron is UTC-based and does not itself follow `America/Chicago` daylight-saving transitions. To preserve a stable local schedule without hard-coding a season, use two daily UTC triggers:

```text
17 11 * * *
17 12 * * *
```

These correspond to 06:17 local under CDT (UTC-5) and CST (UTC-6), respectively. The backend, not GitHub, is authoritative for whether a trigger is in the permitted local execution window.

## Local-time execution gate
On each authenticated machine trigger:

1. compute current time with `ZoneInfo("America/Chicago")`;
2. accept scheduling only when local hour is 06 and local minute is within a narrow reviewed window around the trigger time;
3. otherwise return a sanitized no-op with zero provider calls;
4. never use a fixed UTC offset;
5. never send `X-Time-Zone` to Motive.

The second UTC trigger each day is therefore an intentional safe no-op. DST transitions are resolved by IANA timezone rules.

## At-most-once scheduler dispatch per local day
The production-run lock prevents overlap but does not by itself prevent two sequential scheduled runs on the same day. The scheduler therefore needs a separate durable dispatch claim before any Motive provider call.

Use the existing checkpoint persistence model with a distinct scheduler-only resource key, for example:

```text
vehicle_utilization_scheduler_dispatch
```

This dispatch marker is separate from the ingestion checkpoint `vehicle_utilization` and must never be used to choose the seven-day provider fetch range.

For the target organization and current `America/Chicago` local date, the scheduler must atomically:

- acquire/create the scheduler-dispatch row under database-safe exclusion;
- check the last claimed local schedule date;
- if already claimed for today, return a sanitized duplicate/no-op with zero provider calls;
- otherwise persist today's local date as claimed before invoking the production orchestrator.

The claim is consumed regardless of later success, partial success, provider failure, network ambiguity, or process failure. This deliberately prevents same-day retry behavior.

If the service crashes after claiming the day but before making a provider call, that day's scheduled ingestion may be skipped. This is acceptable for the first scheduler gate because the next day's run rereads the latest seven completed days. Safety is preferred over an uncertain duplicate provider run.

No schema migration should be required if the existing checkpoint table can safely support a distinct provider-resource row. If implementation proves otherwise, migration work must be isolated in a separately reviewed PR.

## Retry and catch-up policy
There is no automatic retry in the first Motive scheduler gate.

- GitHub workflow makes one HTTP attempt per scheduled trigger.
- It must not retry on timeout, connection ambiguity, 429, or 5xx.
- Backend scheduler wrapper must not retry the machine trigger or production orchestrator.
- Existing production orchestrator remains no-retry for Motive provider calls.
- A partial/failed ingestion waits for the next local day's normal schedule; the next run rereads all seven completed days.
- A missed GitHub trigger is not replayed later that day by a catch-up loop.
- Application restart after the local execution window does not trigger an immediate catch-up run.

This avoids converting infrastructure ambiguity into duplicate provider calls.

## Interaction with manual production runs
A separately authorized manual production run can still use the existing manual route while the scheduler is disabled.

When the scheduler is enabled, operational policy should avoid manual production runs during the scheduler execution window. The existing organization-scoped production lock remains the final overlap protection.

The scheduler's same-day dispatch claim governs only scheduled dispatches. It does not rewrite the ingestion checkpoint and does not change durable provider-row identity.

A later operational runbook may choose to suppress a scheduled run when a successful manual run already advanced the ingestion checkpoint through the same D-1. That optimization is not required for the first implementation and must not weaken the scheduler's at-most-once claim.

## Result and observability policy
The scheduled endpoint returns only sanitized scheduler context and the existing sanitized production result.

Allowed scheduler fields include:

- status: executed / disabled / outside_window / already_claimed / failed;
- scheduler mode;
- request timezone `America/Chicago`;
- local schedule date;
- dispatch claimed Boolean;
- production result status;
- windows/provider-call/rollup/write counters already allowed by the production orchestrator;
- checkpoint advanced Boolean;
- sync history written Boolean;
- scheduler enabled Boolean;
- secrets exposed false.

Do not expose organization IDs/slugs, provider vehicle IDs, VINs, metric values, raw payloads, Motive API keys, HMAC secrets, GitHub tokens, database credentials, or Authorization headers.

The existing production `MotiveSyncHistory` row remains the parent ingestion-run record. The scheduler wrapper should not create a second full ingestion history row. The scheduler-dispatch checkpoint is only a durable at-most-once marker.

## API-key rotation prerequisite
Before any live scheduler execution or scheduled production enablement:

1. rotate the Motive Company API Key that was previously exposed outside the application security boundary;
2. update only secure Render backend configuration;
3. never paste or record the new key in GitHub, chat, logs, screenshots, or workflow configuration;
4. perform a zero-write connector status/config preflight;
5. keep the scheduler flag false until key rotation and deployment are confirmed.

Scheduler implementation may be merged while disabled before key rotation, but no live scheduler attempt is authorized until rotation is complete.

## Implementation scope for the next PR
The first scheduler implementation PR should add only:

1. Motive-specific HMAC machine endpoint;
2. one configured scheduled-organization slug resolver;
3. `America/Chicago` local execution-window check;
4. durable same-local-day scheduler-dispatch claim using a distinct checkpoint resource;
5. invocation of the existing production orchestrator without modifying its provider/writer semantics;
6. a GitHub Actions workflow with the two UTC schedules and no retry;
7. sanitized scheduler response/logging;
8. focused mocked tests.

It must not enable either production flag, modify Render values, rotate or expose the Motive API key, execute a live Motive call, change seven-day horizon/100-vehicle cap/units/timezone/pagination/omission/writer/checkpoint semantics, add automatic retry/backoff, add Dashboard/Daily Brief behavior, or add historical backfill/multi-batch ingestion.

## Required tests
Tests must prove at least:

- missing/invalid/stale HMAC fails before provider HTTP;
- request cannot select organization, dates, timezone, units, vehicles, or retries;
- configured organization slug must resolve to exactly one active organization;
- scheduler false -> zero provider calls;
- ingestion false -> zero provider calls even if scheduler flag is true;
- only `America/Chicago` 06:xx local window can execute;
- both UTC cron trigger times map correctly across CDT/CST through IANA timezone rules;
- outside-window trigger -> zero provider calls;
- first valid trigger for a local date claims that date exactly once;
- second sequential valid trigger on the same local date -> zero provider calls;
- concurrent triggers cannot both claim the same local date;
- claim persists even when the production run returns partial/failure or raises a sanitized operational error;
- scheduler wrapper performs no automatic retry;
- production orchestrator still enforces maximum seven provider calls and existing organization run lock;
- production ingestion checkpoint remains distinct from scheduler dispatch marker;
- scheduled response/logs contain no organization identity, provider IDs, VINs, metric values, raw payloads, or secrets;
- implementation ships with scheduler disabled.

## Staged activation after implementation
No scheduler activation is authorized by this design PR.

After a scheduler implementation PR is merged and CI is green:

1. keep both production flags false;
2. rotate the Motive API key;
3. confirm backend live with the rotated key using zero-provider/status checks first;
4. configure Motive-specific scheduled organization slug and HMAC trigger secret in Render;
5. configure only the matching HMAC secret and API URL in GitHub Actions secrets/variables;
6. keep scheduler false and perform a machine-endpoint zero-provider preflight;
7. separately authorize one scheduler-path controlled validation with the production orchestrator bounded exactly as today;
8. return flags false and document the result;
9. only after that evidence, separately authorize persistent daily enablement.

## Out of scope
This design does not authorize scheduler implementation, scheduler activation, a live machine-trigger request, another manual production POST, API-key disclosure, provider retries, same-day catch-up, multi-organization fan-out, historical backfill, multiple vehicle batches, unit conversion, Dashboard/Daily Brief interpretation, or any reinterpretation of provider omissions.