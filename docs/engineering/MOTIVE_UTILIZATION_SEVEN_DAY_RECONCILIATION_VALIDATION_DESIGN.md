# Motive Vehicle Utilization: Seven-Day Controlled Manual Reconciliation Validation Design

## Status

Design-only gate. **No live Motive provider call is authorized or executed by this document.** No runtime code, Render environment change, scheduler, checkpoint advancement, sync-history write, migration, Dashboard/Daily Brief change, or broad sync enablement is part of this gate.

This design follows the successful one-day controlled live-staging validation recorded after PR #179 / PR #180. That one-day run selected 23 eligible vehicles, made exactly one provider call, returned 10 rollups, inserted 10 rows, observed 13 provider omissions, and left checkpoint/history/scheduling disabled.

## Purpose

Define the smallest safe next gate that proves the already-merged recent-window reconciliation runner across the previously designed **7 trailing completed calendar days** without introducing scheduling or checkpoint behavior.

This gate is manual, bounded, feature-gated, and separately authorized. It is not a production sync route and is not a scheduler trigger.

## Proposed Route

A new controlled route should be added in a later implementation PR:

```text
POST /api/v1/motive/verify/vehicle-utilization-recent-reconciliation-seven-day
```

Request body:

```json
{"confirm": true}
```

No caller-supplied dates, horizon, vehicle IDs, batch size, page size, retry options, organization ID, or arbitrary parameters are accepted.

## Authorization and Feature Gates

Require all of the following:

1. Authenticated Polaris principal with `CONNECTOR_WRITE` permission.
2. Existing runner gate:
   `MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_ENABLED=true`
3. A new, separate seven-day validation gate, default false, recommended:
   `MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_SEVEN_DAY_VALIDATION_ENABLED=true`
4. Explicit `{"confirm": true}` request body.

The existing one-day route-validation flag must **not** be reused as authorization for this broader gate. One-day validation authorization and seven-day validation authorization are separate operational decisions.

## Hard Bounds

The implementation must enforce these bounds independently of the general runner:

| Bound | Seven-day validation value |
| --- | ---: |
| Horizon | exactly 7 completed calendar days |
| Calendar windows | exactly 7 daily windows |
| Selected eligible vehicles | maximum 100 |
| Vehicle batches per day | maximum 1 |
| Provider pages per day/batch | maximum 1 |
| Provider calls | maximum 7 total |
| Automatic retries | none |
| Checkpoint advancement | disabled |
| Sync-history writes | disabled |
| Scheduler / cron / worker | disabled |

If eligible tenant vehicles exceed 100, fail closed **before any provider HTTP request**. Do not truncate to the first 100 and do not split into multiple batches for this validation gate.

The reason is deliberate: with at most 100 selected vehicles and one daily window at a time, the seven-day proof is bounded to at most **7 provider calls total**.

## Date / Window Semantics

Reuse the existing reconciliation runner’s completed-calendar-day logic unmodified.

The seven windows are the seven trailing completed calendar days ending yesterday, processed oldest-to-newest. Today is never included. The caller cannot select dates.

The existing Polaris request-window timezone convention remains operational only; this design does not upgrade the exact Motive rollup-timezone configuration field to provider-certified status. Do not add `X-Time-Zone`.

## Unit Mode

Reuse the runner unchanged with:

`MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT`

Therefore:

- omit `X-Metric-Units`;
- do not convert units;
- persist returned Boolean `metric_units` as observed context;
- missing/malformed unit context fails closed;
- immutable existing-row unit conflict fails closed.

The prior successful one-day staging result is empirical bounded evidence only and does not convert omitted-header behavior into universal provider documentation.

## Persistence / Reconciliation Semantics

Reuse the existing writer transaction unchanged.

For each daily unit:

- persist only provider-returned rollups;
- never synthesize zero rows for omitted requested vehicles;
- use the existing durable identity:
  `organization_id + motive_vehicle_id + request_window_start + request_window_end`;
- identical replay remains unchanged;
- later provider corrections may reconcile only the existing five mutable fields already authorized by the writer contract;
- immutable identity/context/provenance conflicts fail closed;
- one vehicle-batch/day remains one transaction boundary.

No checkpoint or sync-history state may be advanced/written by this gate.

## Failure Isolation

Reuse the runner’s current typed operational failure isolation:

- known Motive connector errors;
- pagination errors;
- writer errors;

may fail one `(day, batch)` unit and allow later days to continue.

No automatic retry is added.

Unexpected programming exceptions must still propagate/abort rather than being swallowed by a blanket `except Exception: continue`.

A seven-day result may therefore legitimately be `partial_success`; unlike the one-day route, partial success is possible here because there are seven independent daily units.

## Provider Call Budget

The route must independently verify before execution that the theoretical maximum is no more than 7 calls:

`7 days × 1 batch/day × 1 page = 7 provider calls maximum`

After the runner returns, defense-in-depth must verify:

`provider_calls_attempted <= 7`

Any larger value is an invariant violation and must fail closed without retry.

## Sanitized Response

Return only sanitized counters already exposed by the runner, including:

- status;
- horizon_days;
- windows attempted/completed/failed;
- selected vehicle count;
- vehicle batches attempted/completed/failed;
- provider calls attempted/completed;
- rollups returned;
- missing requested vehicle count;
- records inserted/unchanged/updated;
- reconciled fields count;
- failed units using only window start/end, batch ordinal, and safe error code;
- checkpoint_advanced;
- sync_history_written;
- scheduled_ingestion_enabled;
- secrets_exposed.

Do not expose provider vehicle IDs, DB IDs, VINs, driver PII, raw metrics, raw provider payloads, raw headers, API keys, bearer tokens, or organization identifiers.

## Proposed HTTP Status Mapping

- `200` — `success` or `no_op`.
- `207` — `partial_success`, because multiple daily units exist and some may safely fail while others commit.
- `400` — confirm missing/not true.
- `403` — missing `CONNECTOR_WRITE`.
- `409` — more than 100 eligible vehicles, before provider HTTP.
- `503` — either required feature flag disabled.
- `502` — all attempted daily units fail only with known safe provider/pagination/unit/writer operational failures.
- `500` — genuine unexpected/invariant programming failure only.

Final implementation should confirm this mapping against current API conventions before coding.

## Required Test Matrix for the Later Implementation PR

At minimum, with all provider HTTP mocked:

- runner flag disabled => 503, zero provider calls;
- seven-day route flag disabled => 503, zero provider calls;
- confirm false/missing => validation failure, zero provider calls;
- missing permission => authorization failure, zero provider calls;
- zero eligible vehicles => no-op, zero calls;
- 1 vehicle => 7 daily units maximum, at most 7 calls;
- 100 vehicles => allowed, still at most 7 calls;
- 101 vehicles => fail before provider HTTP;
- all seven days succeed;
- mix of insert / unchanged / corrected replay across days;
- provider omissions never create zero rows;
- one known safe operational failure + later successes => partial success and continued processing;
- all daily units safe-fail => sanitized failure;
- unexpected exception aborts and maps to 500;
- post-hoc provider-call budget violation fails closed;
- no checkpoint/history/scheduler mutation;
- response secret/PII hygiene.

## Operational Procedure After a Later Implementation PR Merges

No live execution is authorized by this design PR. A later implementation PR must merge and pass exact-head CI first.

Only then, under separate explicit human authorization:

1. Confirm staging has at most 100 eligible tenant vehicles.
2. Enable the runner flag and the new seven-day validation flag in staging only.
3. Invoke the controlled seven-day route exactly once.
4. Record only the sanitized response.
5. Immediately return both flags to false and redeploy.

Do not reuse the one-day validation route for this step and do not rerun automatically.

## Still Out of Scope After a Successful Seven-Day Validation

Even if the seven-day live validation succeeds, this design does **not** by itself authorize:

- scheduled reconciliation;
- cron/background workers;
- checkpoint advancement;
- sync-history writes;
- broad `/sync/vehicle-utilization` exposure;
- automatic retries;
- Dashboard / Daily Brief attention logic;
- API key rotation;
- broader than 7-day live backfill.

Those remain separate future gates.