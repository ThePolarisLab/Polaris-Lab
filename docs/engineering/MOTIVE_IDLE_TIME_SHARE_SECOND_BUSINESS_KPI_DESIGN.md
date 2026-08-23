# Motive Vehicle Utilization — Second Business KPI Design

## Status

Design gate only.

This document defines a second Motive business KPI from already-durable vehicle-utilization rows. It does **not** change runtime behavior, provider calls, scheduler behavior, database state, ingestion, reconciliation, snapshot persistence, Dashboard output, Daily Brief output, business status, alerts, thresholds, production configuration, or frontend behavior.

The first business KPI, `Observed 7-Day Vehicle Utilization`, is already implemented and production-certified. This gate deliberately reuses its certified production window, tenant, denominator, omission, and operational-health boundaries rather than inventing a second population model.

## Decision

Canonical second KPI display name:

`Observed 7-Day Vehicle Idle-Time Share`

Canonical machine name:

`observed_7_day_vehicle_idle_time_share`

Recommended first read endpoint:

`GET /api/v1/motive/fleet/vehicle-idle-time-share-kpi`

Permission:

`CONNECTOR_READ`

The first implementation must be read-only: zero Motive provider calls and zero database writes.

## Why idle-time share is the second KPI

The current production utilization rows already persist provider-certified:

- `idle_time` — seconds;
- `driving_time` — seconds;
- `idle_fuel` — fuel consumed while idling;
- `driving_fuel` — fuel consumed while driving;
- `metric_units` — returned provider unit-system indicator.

Current production requests `X-Metric-Units: false`, requires returned `metric_units == false`, and stores fuel in gallons. `idle_time` and `driving_time` remain seconds regardless of metric/imperial fuel mode.

The time fields provide the narrowest second business question that can be answered without adding assumptions about:

- fuel price;
- avoidable versus unavoidable idle;
- PTO operation;
- maintenance behavior;
- yard behavior;
- reefer operation;
- route type;
- driver behavior;
- vehicle class;
- target idle percentage;
- business severity.

For that reason, idle-time share is preferred ahead of an idle-fuel-cost or idle-efficiency KPI.

## Business question

The KPI answers exactly this question:

> Across the certified vehicle-day rollups Motive actually returned for the latest seven-day production window and for which both idle and driving time are usable, what share of the combined observed idle-plus-driving seconds was reported as idle time?

It does **not** claim to answer:

- what percent of the full fleet was idling;
- what percent of each 24-hour day was idling;
- what percent of engine-on time was avoidable;
- what idle time was wasteful;
- what idle time should be eliminated;
- driver productivity;
- fuel efficiency;
- idle fuel cost;
- dispatch efficiency;
- route efficiency;
- maintenance quality;
- parked/inactive vehicle count.

## Source-of-truth precedence

Use the current production-ingestion contract, not older pre-production semantics text or historical comments.

Current production contract:

- provider endpoint: `GET /v1/vehicle_utilization`;
- latest seven completed `America/Chicago` local days;
- one exact one-day provider request per day;
- at most 100 stored tenant-owned Motive vehicles selected;
- current request mode `X-Metric-Units: false` / imperial;
- current returned unit provenance must be `metric_units == false` or ingestion fails closed;
- fuel unit is gallons;
- `idle_time` / `driving_time` are seconds;
- provider omission means unknown / no returned rollup, never zero activity;
- recent history is reread and provider-derived metrics may reconcile in place.

## Authoritative seven-day window

Do not calculate `today - 7 days` independently.

Resolve the exact same authoritative production state used by the first utilization KPI:

1. latest successful production history where:
   - `provider = motive`;
   - `provider_resource = vehicle_utilization`;
   - `mode = production_recent_window_ingestion`;
   - `status = success`;
2. matching successful production checkpoint;
3. persisted `completed_through`;
4. seven exact `America/Chicago` calendar days ending on `completed_through`, inclusive.

If production history/checkpoint health is inconsistent or not healthy, this KPI is unavailable.

The second KPI must not repair, bypass, trigger, or retry production ingestion.

## Historical requested population

Use `selected_vehicle_count` from the matching successful production history as the historical requested denominator.

Expected requested vehicle-days:

`selected_vehicle_count * 7`

Do not use the current `motive_vehicles` count as the historical denominator.

Because the current production history stores only the selected count and not the exact historical selected provider-ID set, the first implementation must reuse the same conservative population-safety guard as the certified utilization KPI: if current tenant vehicle population is not compatible with the successful run's historical selected count, fail closed rather than allowing stale vehicle-window rows to inflate coverage.

Do not weaken that guard in this KPI.

## Atomic observation

The atomic observation is one tenant-owned durable Motive vehicle-utilization row for one exact one-day request window:

`organization_id + motive_vehicle_id + request_window_start + request_window_end`

A row may contribute to the idle-time-share value only when all of the following are true:

- tenant matches the authenticated organization;
- `motive_vehicle_id` is non-null and belongs to the same tenant;
- `request_window_start == request_window_end`;
- the day is inside the authoritative seven-day production window;
- `metric_units == false` as current production provenance guard;
- `idle_time` is non-null;
- `driving_time` is non-null;
- `idle_time >= 0`;
- `driving_time >= 0`;
- `idle_time + driving_time > 0`.

The unit-provenance guard is retained even though seconds themselves do not depend on imperial versus metric mode. It prevents old or non-production-context rows from silently entering the business KPI.

## Invalid and zero-valued rows

A returned numeric zero is not missing.

Examples:

- `idle_time = 0`, `driving_time > 0` is a valid observation and contributes zero idle seconds;
- `idle_time > 0`, `driving_time = 0` is a valid observation and may produce a 100% idle-time share if it is the only contributing time;
- `idle_time = 0`, `driving_time = 0` has no positive time denominator and is not metric-valid for the share calculation;
- null idle or driving time is incomplete, not zero;
- a negative idle or driving time violates the provider-total semantic expectation and must fail closed rather than be silently normalized, clamped, or treated as missing.

No absolute-value conversion, minimum floor, or synthetic denominator is allowed.

## KPI formula

For all metric-valid vehicle-day observations in the authoritative seven-day window:

`observed_idle_seconds = sum(idle_time)`

`observed_driving_seconds = sum(driving_time)`

`observed_idle_plus_driving_seconds = observed_idle_seconds + observed_driving_seconds`

KPI value:

`observed_idle_seconds / observed_idle_plus_driving_seconds * 100`

Return with deterministic display precision, recommended two decimal places.

### Why ratio-of-sums, not average-of-row-percentages

Do **not** calculate an idle percentage for each vehicle-day and then take a simple arithmetic mean.

A simple mean would give a five-minute observed vehicle-day the same weight as a ten-hour observed vehicle-day.

The ratio-of-sums answers the stated business question: what share of the combined observed idle-plus-driving time was idle.

Do not weight by:

- utilization percent;
- fuel;
- mileage;
- revenue;
- loads;
- driver hours;
- vehicle count beyond the explicit coverage calculation.

## Coverage

Coverage is mandatory context and remains vehicle-day based.

### Provider rollup coverage

`provider_rollup_vehicle_days / expected_requested_vehicle_days * 100`

`provider_rollup_vehicle_days` counts distinct tenant-owned durable rows for the exact seven one-day windows, independent of whether idle/driving time is complete.

### Idle-time metric coverage

`metric_valid_vehicle_days / expected_requested_vehicle_days * 100`

`metric_valid_vehicle_days` counts only rows eligible for the idle-time-share formula.

### Missing requested vehicle-days

`expected_requested_vehicle_days - provider_rollup_vehicle_days`

Missing requested vehicle-days remain unknown provider omissions.

Never synthesize missing rows as:

- zero idle;
- zero driving;
- inactive;
- parked;
- out of service.

## Availability and representativeness

### `available_observed`

Return an observed value only when:

- production operational state is healthy;
- the authoritative seven-day window and historical denominator are valid;
- at least one metric-valid vehicle-day exists;
- total observed idle-plus-driving seconds are greater than zero;
- no fail-closed data-integrity condition is present.

### `unavailable`

Return unavailable when any required operational/population contract is invalid, no metric-valid time exists, total observed denominator is zero, or a certified-window row violates a fail-closed condition.

Never return `0%` merely because the KPI is unavailable.

### Fleet-representative flag

`fleet_representative = true` only when idle-time metric coverage is exactly 100% of expected requested vehicle-days.

At anything below 100%, the metric remains an observed-sample statistic.

Even at 100% coverage, the KPI still describes the share of provider-reported `idle_time + driving_time`; it does not become a statement about all 24 hours of every vehicle day.

## Business interpretation boundary

The KPI is descriptive only.

The following interpretations are forbidden in the first implementation:

- `high idle`;
- `low idle`;
- `good`;
- `bad`;
- `efficient`;
- `inefficient`;
- `waste`;
- `excessive idle`;
- `avoidable idle`;
- `needs attention`;
- `target missed`.

Those require historical baseline and operating-context review.

A 20% result means only that 20% of the combined metric-valid observed idle-plus-driving seconds were provider-reported idle seconds for that certified window.

## Executive-attention boundary

This KPI must not alter or populate:

- Executive Dashboard `business_status`;
- `Needs Attention`;
- Today's Plan / Today's Priority;
- `Watch Items`;
- Polaris Recommendation;
- Daily Brief business status;
- Daily Brief System / Data Health;
- email;
- Slack;
- notifications;
- alerts.

No GOOD/WATCH/HIGH, red/amber/green, pass/fail, or target semantics are introduced.

## First implementation surface

The first runtime gate after this design should be backend read-only only:

- tenant-scoped service;
- authenticated GET endpoint;
- existing `CONNECTOR_READ` permission;
- current certified production rows only;
- zero provider calls;
- zero database writes;
- no migration;
- no scheduler change;
- no ingestion change;
- no snapshot/history change;
- no frontend card yet.

Recommended endpoint:

`GET /api/v1/motive/fleet/vehicle-idle-time-share-kpi`

## Recommended sanitized response

- `status`: `available_observed` or `unavailable`;
- `kpi`: `observed_7_day_vehicle_idle_time_share`;
- `window_start`;
- `window_end`;
- `request_timezone`: `America/Chicago`;
- `value_percent` or null;
- `selected_vehicle_count`;
- `expected_requested_vehicle_days`;
- `provider_rollup_vehicle_days`;
- `metric_valid_vehicle_days`;
- `missing_requested_vehicle_days`;
- `provider_rollup_coverage_percent`;
- `idle_time_metric_coverage_percent`;
- `fleet_representative`;
- `time_unit`: `seconds`;
- `unit_request_mode`: `imperial` as production provenance context;
- `secrets_exposed`: false.

The first public response does not need raw summed seconds. The percentage plus coverage is sufficient for the first consumer and reduces unnecessary business-volume exposure.

Do not expose:

- provider vehicle IDs;
- Motive vehicle database IDs;
- VINs;
- plates;
- unit numbers;
- run IDs;
- source history IDs;
- raw provider payloads;
- raw sync-history JSON;
- API keys;
- access/session tokens;
- request headers;
- exception strings.

## Query and deduplication rules

The future read model must:

- scope every query by authenticated `organization_id`;
- use only the exact seven one-day request windows established from the successful production checkpoint/history;
- count distinct durable vehicle-day identities;
- fail closed on unexpected duplicate full identities;
- ignore reporting-period columns for identity;
- exclude rows outside the certified window;
- exclude multi-day request-window rows;
- exclude rows without tenant-owned Motive vehicle association;
- exclude non-current unit-provenance rows from the metric-valid set;
- never join another tenant's vehicle/history rows;
- never call Motive to fill a missing value.

## Current coverage evidence and limitation

Repository certification proves that all four additive fields (`idle_time`, `driving_time`, `idle_fuel`, `driving_fuel`) were observed in the documented production response shape, and bounded evidence showed the additive time/fuel fields composed consistently across adjacent single-day versus combined windows for the returned vehicle slot.

That evidence does **not** prove that idle/driving time is present on 100% of MOR's current requested vehicle-days. Therefore the KPI must carry its own explicit current-window metric coverage and remain observed/non-representative below 100%.

Low coverage is not a reason to fabricate data. If current production coverage is poor, production certification may legitimately return a low-coverage observed result or unavailable state and the consumer-placement gate should remain on hold.

## Why idle-fuel share is deferred

A possible later metric is:

`idle_fuel / (idle_fuel + driving_fuel)`

That ratio could be technically computed from current imperial rows, but it is deliberately deferred behind idle-time share because business interpretation is more sensitive to:

- PTO and equipment context;
- fuel-consuming stationary work;
- fuel-cost assumptions if converted to dollars;
- vehicle/equipment differences;
- avoidability assumptions.

No idle-fuel business KPI or cost estimate is authorized by this design.

## Historical trend boundary

The existing generic utilization KPI snapshot table currently stores the first utilization KPI only.

This design does not modify that table, create a second snapshot type, or add historical idle-time-share trends.

If the second KPI is later production-certified and a trend is desired, snapshot/history persistence must be designed separately. Do not reconstruct a trustworthy historical idle-time-share series from mutable current rows after fleet membership changes.

## Required implementation test matrix

At minimum, the future backend implementation must prove:

1. healthy successful production state + valid time rows returns `available_observed`;
2. ratio-of-sums is correct;
3. a valid returned zero `idle_time` contributes a real zero;
4. a valid returned zero `driving_time` is preserved;
5. `idle_time = driving_time = 0` does not create a synthetic percentage;
6. null idle/driving fields are incomplete, not zero;
7. negative idle/driving data fails closed;
8. denominator comes from matching successful production history, not current vehicle-table count;
9. expected vehicle-days equals selected vehicle count × 7;
10. provider-rollup coverage is correct;
11. idle-time metric coverage is correct;
12. missing provider rows are never synthesized;
13. exact one-day window rule is enforced;
14. rows outside the certified seven-day window are excluded;
15. non-current unit-provenance rows are excluded from the metric-valid set;
16. current population-change safety guard matches the first KPI's conservative behavior;
17. zero metric-valid rows returns `unavailable`, never 0%;
18. healthy rows with zero total idle-plus-driving seconds return `unavailable`;
19. unhealthy/inconsistent production operational state returns `unavailable`;
20. cross-tenant rows/history/checkpoints cannot influence the result;
21. response exposes no provider IDs, VINs, run/history IDs, raw JSON, credentials, or exception strings;
22. service/endpoint performs zero Motive provider calls;
23. service/endpoint performs SELECTs only and zero database writes;
24. `fleet_representative` is true only at exactly 100% metric-valid vehicle-day coverage;
25. no Dashboard, Daily Brief, alert, threshold, or business-status behavior changes.

## Production certification after implementation

After the read-only backend implementation merges and deploys:

1. make exactly one authenticated production GET of the second KPI endpoint;
2. compare only sanitized aggregate fields;
3. verify the window matches the certified production checkpoint;
4. verify expected requested vehicle-days equals selected vehicles × 7;
5. verify coverage arithmetic;
6. verify `secrets_exposed=false`;
7. do not trigger Motive sync, scheduler, reconciliation, or provider verification for certification;
8. if coverage is partial, keep the result explicitly observed/non-fleet-representative;
9. do not add a frontend consumer until the production result is certified.

## Non-goals

This design does not:

- implement the KPI;
- add schema or migrations;
- add a snapshot;
- add history;
- add a frontend card;
- add a chart;
- add idle-fuel KPI;
- calculate fuel cost;
- classify avoidable idle;
- rank trucks;
- rank drivers;
- add thresholds;
- add alerts;
- change provider requests;
- add provider calls;
- change the seven-day production horizon;
- change timezone or unit policy;
- change ingestion;
- change reconciliation;
- change scheduling;
- backfill data;
- modify Daily Brief or System Health semantics.

## Recommended rollout

1. Merge this design gate.
2. Implement the read-only idle-time-share service and endpoint only.
3. Run focused denominator, ratio, zero/null, integrity, coverage, tenant, sanitization, SELECT-only, and zero-provider-call tests.
4. Run the full repository CI gates triggered by the implementation.
5. Production-certify with one authenticated GET.
6. Only after certification, separately design consumer placement or historical snapshot/trend behavior.
7. Only after a meaningful historical baseline and operating-context review, consider threshold or attention semantics.