# Motive Vehicle Utilization Production Ingestion Gate Design

## Status
Design only. This document does not enable scheduled ingestion, checkpoints, sync history, provider calls, or production writes.

## Evidence entering this gate
The production-ingestion design starts after the separately authorized seven-day staging validation completed successfully: 23 selected vehicles, 7/7 completed windows, 7/7 completed batches, 7/7 completed provider calls, 72 returned rollups, 61 inserts, 11 updates, 24 reconciled mutable fields, zero failed units, and no checkpoint/history/scheduler/secret side effects. Provider omissions remain omissions only and must never be interpreted as zero utilization or inactivity.

## Objective
Introduce a disabled-by-default, tenant-safe production ingestion path that can eventually run once per day and refresh a recent rolling window without changing the already-certified provider, pagination, unit, identity, writer, or reconciliation semantics.

This gate separates scheduled orchestration, rolling-window selection, durable reconciliation writes, sync-history observability, and checkpoint advancement. No one concern silently enables another.

## Production request policy

### Rolling window
- Process the latest 7 completed calendar days only.
- Never request the current in-progress calendar day.
- Use seven independent one-day windows rather than one seven-day aggregate request.
- Reread the full recent seven-day window every run so late provider corrections can reconcile in place.

### Vehicle scope
- Select organization-owned Motive vehicles only.
- Maximum 100 eligible vehicles in the first production gate.
- More than 100 eligible vehicles fails closed before provider HTTP; no silent truncation.
- Multi-batch production ingestion is deferred to a later reviewed gate.

### Provider-call budget
- Maximum 7 provider calls per run.
- One page per daily window with `per_page=100`.
- No automatic provider retries in the first production gate.
- Retry/backoff requires separate review.

### Unit mode
- Continue the already validated `ACCOUNT_DEFAULT` mode.
- Do not emit `X-Metric-Units` in this gate.
- Preserve returned unit context and the existing fail-closed unit validation.
- No unit conversion.

## Writer semantics
Reuse the existing writer/reconciliation path unchanged:
- persist returned rollups only,
- map each rollup to exactly one organization-owned Motive vehicle,
- never auto-create a vehicle,
- preserve database identity `organization_id + motive_vehicle_id + request_window_start + request_window_end`,
- identical replay remains a no-op,
- provider-corrected mutable fields may reconcile in place under the existing policy,
- omissions never delete, zero, or mutate previously stored rows,
- unexpected or duplicate provider vehicles fail closed.

## Transaction boundary
Each daily request window remains its own durable writer transaction. The production orchestrator must not wrap all seven windows in a second broad transaction.

This preserves already validated daily-window behavior, allows durable successful corrections to remain committed if a later day fails, and lets the next scheduled run naturally reread the rolling window.

## Run outcome policy

### Success
All seven windows complete successfully.
- write one successful sync-history record,
- advance the utilization checkpoint only after all seven durable windows and the history record are complete,
- return sanitized counters only.

### Partial success
At least one window succeeds and at least one fails.
- retain already committed successful daily-window writes,
- write one partial sync-history record,
- do not advance the checkpoint,
- next run rereads all seven recent completed days,
- never synthesize replacement rows for failed or omitted vehicles.

### Failure
No window succeeds, or a preflight/invariant failure prevents the run.
- write one failed sync-history record when the history layer itself is available,
- do not advance the checkpoint,
- do not classify provider omission as provider failure.

## Checkpoint design
The checkpoint is an orchestration marker, not provider-row identity and not the source of the next fetch range.

Use a dedicated vehicle-utilization checkpoint resource key. Store the latest completed calendar day covered by an all-success production run. If a run processes D-7 through D-1 and every window succeeds, checkpoint becomes D-1.

Checkpoint advances only when all seven windows completed, every writer transaction committed, no provider/pagination/unit/invariant failure occurred, and the sync-history write succeeded. Partial success never advances it.

The next fetch range is always the latest seven completed days even if the checkpoint is older. This avoids gap-skipping and preserves the provider guidance that completed rollups may later change and should be reread over a recent rolling window.

## Sync-history design
Create one parent sync-history entry per orchestrated production run, not one entry per vehicle or provider row.

Sanitized history may include only:
- status: success / partial / failed,
- horizon days,
- windows attempted/completed/failed,
- batches attempted/completed/failed,
- provider calls attempted/completed,
- selected vehicle count,
- rollups returned,
- missing requested vehicle count,
- records inserted/unchanged/updated,
- reconciled fields count,
- failed unit count,
- checkpoint advanced Boolean,
- run start/completion timestamps,
- safe error code/classification.

Do not store raw provider payloads, VINs, vehicle IDs, API keys, bearer tokens, or metric values in sync history.

## Scheduling policy
The scheduler remains absent/disabled in the first implementation PR.

After a separately validated production orchestrator, proposed initial cadence is once daily, delayed until the prior day is safely complete. A conservative initial target is approximately 06:00 in the organization's operational Central-time context. The implementation must never depend on `X-Time-Zone` for Motive rollup behavior.

The exact provider rollup-timezone binding remains provider/account behavior rather than a request-header contract, so this design uses completed calendar days and a delayed run time.

## Concurrency guard
Only one vehicle-utilization production run may execute per organization at a time. The implementation must provide an organization-scoped fail-closed lock or equivalent database-safe exclusion mechanism. A second overlapping invocation exits without provider calls.

## Feature gates
Introduce separate default-off controls, for example:
- `MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED=false`
- `MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED=false`

The ingestion flag permits a manual/admin production-orchestrator validation after implementation. The scheduler flag remains off until that orchestrator has separate bounded live evidence.

The existing controlled-write, one-day, and seven-day validation flags remain separate and are not reused as production controls.

## Authentication and Motive key rotation
Before broad production scheduling is enabled:
- rotate the Motive Company API Key that was previously exposed outside the application security boundary,
- update only secure backend configuration,
- run a zero-write connectivity/status preflight,
- never reproduce the key in GitHub, docs, logs, screenshots, or chat.

Key rotation is a production-enablement prerequisite, not part of this docs-only design PR.

## Next implementation gate
The next PR should add only:
1. an internal production-orchestration service,
2. organization-scoped concurrency exclusion,
3. one manual/admin production-ingestion route behind the new default-off ingestion flag,
4. sync-history write behavior,
5. checkpoint advancement behavior,
6. focused mocked tests.

It must not yet add or enable cron/scheduling.

## Required implementation invariants
Tests must prove:
- >100 vehicles fails before provider HTTP,
- provider-call count cannot exceed 7,
- current day is never requested,
- every window is exactly one completed calendar day,
- omissions are never synthesized,
- partial success keeps committed successful windows but checkpoint remains unchanged,
- all-success advances checkpoint exactly once,
- history is written exactly once per orchestrated run,
- history contains no IDs, VINs, raw metrics, raw payloads, or secrets,
- a concurrent second run makes zero provider calls,
- scheduler remains disabled,
- `ACCOUNT_DEFAULT` behavior is unchanged.

## Live-enablement sequence after implementation
No production scheduling is authorized by this design.

After implementation merges and CI is green:
1. keep scheduler flag false,
2. rotate the Motive API key,
3. enable only the production-ingestion flag in staging,
4. perform zero-provider-call auth/config preflight,
5. run exactly one separately authorized manual production-ingestion validation,
6. capture sanitized history and checkpoint evidence,
7. disable the production-ingestion flag,
8. document the evidence,
9. separately review scheduler enablement,
10. only then consider once-daily scheduling.

## Out of scope
This design does not authorize another seven-day validation POST, scheduler activation, broad production ingestion, multiple vehicle batches, automatic retries, raw-payload persistence, Dashboard/Daily Brief changes, reinterpretation of missing rollups, historical identity migration, unit conversion, or API-key disclosure.
