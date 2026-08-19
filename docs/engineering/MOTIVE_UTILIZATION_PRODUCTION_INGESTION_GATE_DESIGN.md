# Motive Vehicle Utilization Production Ingestion Gate Design

## Status
Design only. This document does not enable scheduled ingestion, checkpoints, sync history, provider calls, or production writes.

## Evidence entering this gate
The production-ingestion design starts after the separately authorized seven-day staging validation completed successfully: 23 selected vehicles, 7/7 completed windows, 7/7 completed batches, 7/7 completed provider calls, 72 returned rollups, 61 inserts, 11 updates, 24 reconciled mutable fields, zero failed units, and no checkpoint/history/scheduler/secret side effects. Provider omissions remain omissions only and must never be interpreted as zero utilization or inactivity.

On 2026-08-19 Motive API Support supplied two additional written confirmations that supersede two earlier production-design assumptions:

1. `GET /v1/vehicle_utilization` resolves `start_date` and `end_date` using the company's configured/default rollup timezone. For Mor Logistics Manitoba Limited, the authoritative IANA mapping for the currently configured Central Time - Chicago setting is `America/Chicago`. Calendar-day boundaries follow that timezone's daylight-saving rules, and `end_date` is inclusive. Motive does not document a separate per-vehicle or customer-configurable rollup timezone for this endpoint.
2. Motive does not explicitly certify omission of `X-Metric-Units` as a supported way to select the account/company-configured unit system. Motive did explicitly confirm that `X-Metric-Units: false` means US Imperial, with returned `vehicle.metric_units: false` and `idle_fuel` / `driving_fuel` interpreted as gallons.

These provider confirmations are recorded separately in `MOTIVE_UTILIZATION_PROVIDER_TIMEZONE_AND_UNIT_CERTIFICATION_2026-08-19.md`.

## Objective
Introduce a disabled-by-default, tenant-safe production ingestion path that can eventually run once per day and refresh a recent rolling window while preserving the already-certified provider, pagination, identity, writer, and reconciliation semantics and adopting the newly provider-certified production timezone and unit-request contract.

This gate separates scheduled orchestration, rolling-window selection, durable reconciliation writes, sync-history observability, and checkpoint advancement. No one concern silently enables another.

## Production request policy

### Rolling window and timezone
- Process the latest 7 completed local calendar days only.
- Never request the current in-progress calendar day.
- Interpret request-window dates in `America/Chicago` for this Motive account.
- Use the IANA timezone database rules for daylight-saving transitions; never hard-code a UTC offset.
- Treat `end_date` as inclusive.
- Use seven independent one-day windows rather than one seven-day aggregate request.
- Reread the full recent seven-day window every run so late provider corrections can reconcile in place.
- Store `America/Chicago` as request-window timezone metadata for each orchestrated synchronization run and, where the persistence contract supports it, for the request context used by durable utilization rows.
- Do not send `X-Time-Zone`; the timezone is provider/account configuration, not a request-header override.

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
- The production request contract is explicit US Imperial.
- Send `X-Metric-Units: false` on every production `GET /v1/vehicle_utilization` request.
- Require returned `vehicle.metric_units == false` for every persisted rollup. A missing, malformed, or disagreeing unit indicator fails closed before fuel metrics are persisted.
- Interpret `idle_fuel` and `driving_fuel` as gallons only when the explicit `false` request and returned `vehicle.metric_units: false` agree.
- Preserve `idle_time` and `driving_time` as provider-returned seconds under the previously certified time-metric semantics.
- Store the requested measurement system (`US_IMPERIAL` / `X-Metric-Units=false`) in synchronization metadata.
- No unit conversion.
- `ACCOUNT_DEFAULT` / header omission is no longer the planned production contract because Motive did not certify omission of `X-Metric-Units` as a supported account-default selector.

## Writer semantics
Reuse the existing writer/reconciliation path except where a later implementation PR must minimally adapt unit-request validation from the staging `ACCOUNT_DEFAULT` mode to the explicit US Imperial production contract:
- persist returned rollups only,
- map each rollup to exactly one organization-owned Motive vehicle,
- never auto-create a vehicle,
- preserve database identity `organization_id + motive_vehicle_id + request_window_start + request_window_end`,
- identical replay remains a no-op,
- provider-corrected mutable fields may reconcile in place under the existing policy,
- omissions never delete, zero, or mutate previously stored rows,
- unexpected or duplicate provider vehicles fail closed,
- fuel-bearing rollups persist only when explicit requested and returned unit context agree.

Any schema change needed to durably record request timezone or requested measurement-system provenance must be separately reviewed. This docs gate does not authorize a migration.

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

Use a dedicated vehicle-utilization checkpoint resource key. Store the latest completed `America/Chicago` calendar day covered by an all-success production run. If a run processes D-7 through D-1 and every window succeeds, checkpoint becomes D-1.

Checkpoint advances only when all seven windows completed, every writer transaction committed, no provider/pagination/unit/invariant failure occurred, and the sync-history write succeeded. Partial success never advances it.

The next fetch range is always the latest seven completed `America/Chicago` days even if the checkpoint is older. This avoids gap-skipping and preserves the provider guidance that completed rollups may later change and should be reread over a recent rolling window.

## Sync-history design
Create one parent sync-history entry per orchestrated production run, not one entry per vehicle or provider row.

Sanitized history may include only:
- status: success / partial / failed,
- horizon days,
- request timezone: `America/Chicago`,
- requested measurement system: `US_IMPERIAL`,
- metric request header mode: explicit `X-Metric-Units=false`,
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

After a separately validated production orchestrator, proposed initial cadence is once daily, delayed until the prior `America/Chicago` calendar day is safely complete. A conservative initial target is approximately 06:00 `America/Chicago`. The implementation must never depend on `X-Time-Zone` for Motive rollup behavior.

Motive has now confirmed that the company's configured/default rollup timezone for this account maps to `America/Chicago`, including daylight-saving rules. Therefore production calendar calculations should use that IANA zone directly rather than an unspecified operational-Central assumption or a fixed offset.

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
1. the minimal unit-request contract adaptation needed to issue explicit `X-Metric-Units: false` and fail closed unless returned `vehicle.metric_units == false`,
2. `America/Chicago` local-calendar window construction using IANA timezone rules,
3. request timezone and requested measurement-system sync metadata,
4. an internal production-orchestration service,
5. organization-scoped concurrency exclusion,
6. one manual/admin production-ingestion route behind the new default-off ingestion flag,
7. sync-history write behavior,
8. checkpoint advancement behavior,
9. focused mocked tests.

It must not yet add or enable cron/scheduling. Any database migration required for new provenance metadata must be isolated and separately reviewed rather than silently bundled.

## Required implementation invariants
Tests must prove:
- >100 vehicles fails before provider HTTP,
- provider-call count cannot exceed 7,
- current `America/Chicago` day is never requested,
- every window is exactly one completed `America/Chicago` calendar day,
- daylight-saving transitions are handled by IANA timezone rules rather than fixed offsets,
- `end_date` handling remains inclusive,
- every production utilization request explicitly emits `X-Metric-Units: false`,
- returned `vehicle.metric_units` must be exactly `false` before fuel metrics are persisted,
- missing/malformed/true returned unit context fails closed,
- `idle_fuel` / `driving_fuel` are treated as gallons only under an agreeing explicit US Imperial request/response context,
- omissions are never synthesized,
- partial success keeps committed successful windows but checkpoint remains unchanged,
- all-success advances checkpoint exactly once,
- history is written exactly once per orchestrated run,
- history records safe timezone/unit-request provenance but contains no IDs, VINs, raw metrics, raw payloads, or secrets,
- a concurrent second run makes zero provider calls,
- scheduler remains disabled,
- production code does not rely on `ACCOUNT_DEFAULT` header omission.

## Live-enablement sequence after implementation
No production scheduling is authorized by this design.

After implementation merges and CI is green:
1. keep scheduler flag false,
2. rotate the Motive API key,
3. enable only the production-ingestion flag in staging,
4. perform zero-provider-call auth/config preflight,
5. verify the implementation reports `America/Chicago` and explicit US Imperial request policy without exposing secrets,
6. run exactly one separately authorized manual production-ingestion validation,
7. capture sanitized history and checkpoint evidence,
8. disable the production-ingestion flag,
9. document the evidence,
10. separately review scheduler enablement,
11. only then consider once-daily scheduling.

## Out of scope
This design does not authorize another seven-day validation POST, scheduler activation, broad production ingestion, multiple vehicle batches, automatic retries, raw-payload persistence, Dashboard/Daily Brief changes, reinterpretation of missing rollups, historical identity migration, unit conversion, API-key disclosure, or reliance on an uncertified account-default unit-header omission behavior.
