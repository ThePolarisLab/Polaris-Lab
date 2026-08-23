# Motive Vehicle Utilization — History and Baseline Design

## Status

Design gate only.

This document defines how Polaris should preserve historical observations of the already production-certified `Observed 7-Day Vehicle Utilization` KPI so that a later Fleet / Operations consumer can show a neutral trend and, only after a separate business-review gate, support threshold design.

This gate does **not** add a database table, migration, endpoint, scheduler action, provider call, production write, frontend chart, alert, threshold, target, or business-status rule.

## Existing certified KPI

The current read endpoint is:

`GET /api/v1/motive/fleet/vehicle-utilization-kpi`

It returns the latest reconciled seven-completed-day observation from durable Motive utilization rows. The value is an arithmetic mean over valid returned vehicle-days, and it exposes utilization-metric coverage plus `fleet_representative` so missing provider observations remain unknown rather than being treated as zero.

The Executive Dashboard already consumes that endpoint as a neutral Fleet / Operations reporting card.

## Problem to solve

A historical trend cannot be reconstructed safely later from only the current durable utilization rows and `MotiveSyncHistory`.

Two existing properties make retrospective reconstruction ambiguous:

1. utilization rows are reconciliation state and may be updated when the same request window is re-read; they are not immutable point-in-time KPI observations;
2. production history preserves `selected_vehicle_count`, but it does not preserve the exact historical selected vehicle-ID set used for each run.

The current latest-KPI read model can therefore fail closed if the present tenant vehicle population no longer matches the latest production-run count. Extending that logic backward across fleet additions/removals would either guess the historical denominator or reinterpret past values using today's fleet population.

Neither is acceptable.

## Decision

Preserve one small **canonical aggregate KPI snapshot per reconciled seven-day window** at the time the successful production run still has an unambiguous selected vehicle population.

The snapshot is derived only from already-persisted tenant-owned Motive utilization rows and the exact production-run selection context. It must make **zero additional Motive provider calls**.

A snapshot is business-observation history, not raw provider history and not an operational severity event.

## Snapshot identity

The future persistence model should use a tenant-owned table with a name equivalent to:

`motive_vehicle_utilization_kpi_snapshots`

Canonical identity:

- `organization_id`;
- `kpi = observed_7_day_vehicle_utilization`;
- `window_start`;
- `window_end`.

There must be at most one canonical snapshot for a tenant/KPI/window.

A retry or deliberate re-reconciliation of the **same** completed window updates that canonical snapshot rather than creating a second business trend point. Operational attempt history remains the responsibility of `MotiveSyncHistory`.

## Minimum snapshot fields

The aggregate snapshot should preserve only the information required to reproduce the certified KPI meaning:

- tenant ownership (`organization_id`, `organization_slug`);
- KPI name/version;
- `status` (`available_observed` or `unavailable`);
- `window_start`;
- `window_end`;
- `request_timezone`;
- `value_percent` nullable;
- `selected_vehicle_count`;
- `expected_requested_vehicle_days`;
- `provider_rollup_vehicle_days`;
- `metric_valid_vehicle_days`;
- `missing_requested_vehicle_days`;
- `provider_rollup_coverage_percent`;
- `utilization_metric_coverage_percent`;
- `fleet_representative`;
- `fuel_unit`;
- `unit_request_mode`;
- source production-history lineage (internal history row ID or equivalent non-secret reference);
- `computed_at` / `updated_at`.

Do **not** store access tokens, API keys, headers, provider payloads, raw response bodies, or rendered exception strings in the KPI snapshot.

The aggregate snapshot does not need to persist provider vehicle IDs or a copy of every vehicle-day row.

## Computation contract

Snapshot computation must use the same semantic contract as the certified latest KPI:

- seven completed days;
- `America/Chicago` request timezone;
- production unit request mode;
- imperial fuel context / gallons;
- one expected vehicle-day for every selected vehicle on every day in the seven-day window;
- provider omissions remain missing/unknown;
- only valid utilization values contribute to the arithmetic mean;
- valid returned `0` utilization remains a real value and is not converted to missing;
- coverage is calculated independently from KPI value;
- `fleet_representative=true` only when every expected vehicle-day has a valid utilization metric.

The snapshot calculator must receive the exact selected tenant vehicle population from the successful production-run context. It must not reconstruct the selected population from today's `motive_vehicles` table.

## When a snapshot is written

A future implementation may create/update the aggregate snapshot **only after the primary production utilization reconciliation has succeeded** for that window.

The snapshot write is secondary analytics persistence. It must not cause a successful Motive ingestion/checkpoint transaction to be rolled back.

Recommended transaction boundary:

1. production ingestion and checkpoint complete using the already-certified transaction contract;
2. after that commit succeeds, compute the aggregate from durable rows plus the exact run selection context;
3. upsert the canonical snapshot in a separate short local transaction;
4. if the snapshot write fails, keep production ingestion successful and emit only sanitized operational logging/telemetry for the snapshot failure.

A snapshot failure must never trigger another Motive provider request automatically.

A missing snapshot is a history gap. It is not `0%` utilization.

## Unavailable snapshots

A successful production run can still yield no valid business KPI for a window.

When the aggregate cannot produce a valid observed utilization value under the certified contract, the canonical snapshot may be stored as:

- `status = unavailable`;
- `value_percent = null`;
- coverage/count fields preserved when safely known.

This allows the history to distinguish “the production window was processed but no certified KPI was available” from “no snapshot was recorded.”

No raw exception message should be persisted or exposed.

## No automatic historical backfill in the first implementation

The first snapshot implementation starts prospectively.

Do not attempt to manufacture pre-snapshot history from old mutable utilization rows, current fleet membership, or incomplete historical selection metadata.

Any future historical backfill requires a separate design and explicit evidence that the historical selected population and KPI semantics can be reconstructed without guessing.

## Read-only history endpoint

After snapshot persistence is separately implemented and certified, a following read-only gate may expose a tenant-scoped endpoint equivalent to:

`GET /api/v1/motive/fleet/vehicle-utilization-kpi/history?days=30`

The endpoint must read only the aggregate snapshot table and must make zero provider calls and zero writes.

Suggested response fields:

- KPI name;
- requested history horizon;
- timezone;
- `snapshot_count`;
- ordered `points` with:
  - window start/end;
  - status;
  - value percent nullable;
  - utilization-metric coverage percent;
  - valid/expected vehicle-days;
  - fleet representativeness;
- `secrets_exposed = false`.

The default `days=30` is a **display horizon**, not a business threshold or statistical sufficiency rule. The endpoint should have a conservative bounded maximum such as 90 days.

## Trend semantics

A future 30-day chart should plot one canonical point per `window_end` date.

For `available_observed` points:

- plot the returned value;
- preserve and expose its coverage context;
- do not silently normalize partial coverage to 100%;
- do not weight missing vehicle-days as zero.

For `unavailable` snapshots or missing snapshot dates:

- render a gap / missing observation;
- do not draw a synthetic zero-value point.

Do not linearly infer business performance through gaps in a way that suggests observed data existed.

## Baseline semantics

In this gate, **baseline** means only the accumulating set of historical certified observations and their coverage metadata.

Do not calculate or publish a “normal utilization,” target, pass/fail line, GOOD/WATCH/HIGH classification, or recommended threshold yet.

Do not average the rolling KPI snapshots into a single baseline number in the first history consumer. Each rolling point can have materially different metric coverage, so a simple average of those already-aggregated values can hide observation bias.

A later threshold-design gate must first review:

- number and continuity of snapshots;
- coverage distribution;
- fleet-population changes;
- seasonality/day-of-week effects;
- operating context such as maintenance, parked assets, dedicated lanes, and planned downtime;
- whether partial-coverage points are eligible for threshold calibration;
- whether weighting should occur at vehicle-day level rather than snapshot level.

Only that later gate may define business thresholds.

## Fleet population changes

Historical snapshots must retain the point-in-time denominator/count context from their source production run.

Adding or removing a vehicle later must not rewrite an older snapshot merely because today's fleet population differs.

This is the primary reason to persist the aggregate observation prospectively rather than reconstructing it later from current fleet membership.

## Tenant and security boundaries

All snapshot writes and reads must be tenant-scoped by `organization_id`.

History consumers must use existing `CONNECTOR_READ` or an equivalently reviewed read permission; no public unauthenticated history endpoint is authorized.

The history response must never expose:

- API keys or bearer tokens;
- authorization headers;
- provider payloads;
- provider vehicle IDs unless separately justified;
- database connection information;
- raw exception strings.

## Relationship to System / Data Health

KPI history is business reporting, not connector health.

A missing or unavailable business snapshot does not automatically create HIGH/MEDIUM/CRITICAL executive attention.

Operational failure to persist snapshots may later be surfaced in System / Data Health after a separate observability design, but that is outside this gate.

## Relationship to Daily Brief and Dashboard

This design does not modify:

- Daily Brief `system_health`;
- Dashboard `business_status`;
- Needs Attention;
- Watch Items;
- Today's Plan / Priority;
- Polaris Recommendation;
- email/Slack/notification delivery.

The existing latest KPI card remains unchanged.

## Future implementation sequence

After this design merges, proceed in separate gates:

1. **Snapshot persistence/schema gate** — add the tenant-owned aggregate snapshot model/migration and a pure calculator/upsert path with tests, but do not yet wire it to production scheduling.
2. **Production snapshot integration gate** — after successful utilization reconciliation, persist one canonical aggregate snapshot using the exact run selection context; no extra provider call and failure isolated from ingestion success.
3. **Read-only history endpoint gate** — expose bounded aggregate history with tenant isolation and zero writes/provider calls.
4. **Frontend trend gate** — show a neutral 30-day Fleet / Operations trend with explicit coverage and gaps.
5. **Historical baseline review** — after sufficient real observations exist, analyze coverage and operating context.
6. **Threshold design gate** — only then consider GOOD/WATCH/HIGH or target semantics.

Each gate requires its own CI and production certification appropriate to its surface.

## Acceptance criteria for this design gate

This design is accepted when it clearly establishes that:

- past KPI observations will not be reconstructed using today's fleet population;
- one canonical aggregate snapshot is retained per reconciled seven-day window;
- snapshot creation uses no additional Motive provider call;
- snapshot write failure cannot roll back successful ingestion;
- missing/unavailable history is never converted to zero;
- coverage remains first-class beside every observed value;
- 30 days is only a history display horizon;
- no business thresholds or alerts are introduced;
- no automatic historical backfill is authorized.
