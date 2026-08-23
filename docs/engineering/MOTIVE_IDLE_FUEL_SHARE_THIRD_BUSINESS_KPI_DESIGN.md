# Motive Vehicle Utilization — Third Business KPI Design

## Status

Design gate only.

This document defines a third Motive business KPI from already-durable vehicle-utilization rows. It does **not** change runtime behavior, provider calls, scheduler behavior, database state, ingestion, reconciliation, snapshot persistence, Dashboard output, Daily Brief output, business status, alerts, thresholds, production configuration, or frontend behavior.

The already-certified business KPIs are:

1. `Observed 7-Day Vehicle Utilization`;
2. `Observed 7-Day Vehicle Idle-Time Share`.

This gate deliberately reuses their certified production window, tenant, denominator, omission, operational-health, and population-safety boundaries rather than inventing a new population model.

## Decision

Canonical display name:

`Observed 7-Day Vehicle Idle-Fuel Share`

Canonical machine name:

`observed_7_day_vehicle_idle_fuel_share`

Recommended first read endpoint:

`GET /api/v1/motive/fleet/vehicle-idle-fuel-share-kpi`

Permission:

`CONNECTOR_READ`

The first implementation must be read-only: zero Motive provider calls and zero database writes.

## Why idle-fuel share is the third KPI

The current production vehicle-utilization rows already persist provider-certified:

- `idle_fuel` — fuel consumed while idling;
- `driving_fuel` — fuel consumed while driving;
- `metric_units` — returned provider unit-system indicator;
- exact request-window dates;
- tenant-owned Motive vehicle association.

Current production requests `X-Metric-Units: false`, requires returned `metric_units == false`, and therefore persists fuel in gallons. The same unit is used for `idle_fuel` and `driving_fuel` on an accepted production row.

A share formed from the two same-unit fuel fields is dimensionless, so it can answer one narrow business question without adding fuel-price or cost assumptions.

## Business question

The KPI answers exactly:

> Across the certified vehicle-day rollups Motive actually returned for the latest seven-day production window and for which both idle and driving fuel are usable, what share of the combined observed idle-plus-driving fuel volume was reported as idle fuel?

It does **not** claim to answer:

- how much fuel was avoidably wasted;
- what idle behavior should be eliminated;
- whether idle is good or bad;
- what idle fuel cost in dollars;
- driver efficiency;
- dispatch efficiency;
- route efficiency;
- maintenance quality;
- PTO or equipment-operation efficiency;
- reefer fuel consumption;
- percent of total company fuel purchases;
- percent of all engine fuel use outside the provider rollup definition.

## Interpretation boundary

Stationary fuel consumption can include operating contexts that are not automatically wasteful or avoidable. The first KPI implementation must therefore remain descriptive only.

Do not label the result:

- waste;
- avoidable idle;
- excessive idle;
- inefficient;
- high idle;
- low idle;
- good;
- bad;
- target missed;
- needs attention.

No fuel-price multiplication or dollar estimate is authorized in this gate.

## Source-of-truth precedence

Use the current production-ingestion contract and current provider-confirmed unit policy.

Current production contract:

- provider endpoint: `GET /v1/vehicle_utilization`;
- latest seven completed `America/Chicago` local days;
- one exact one-day provider request per day;
- at most 100 stored tenant-owned Motive vehicles selected;
- request mode `X-Metric-Units: false` / imperial;
- returned `metric_units` must be `false` or ingestion fails closed;
- accepted `idle_fuel` / `driving_fuel` values are gallons;
- provider omission means unknown / no returned rollup, never zero activity;
- recent history is reread and provider-derived metrics may reconcile in place.

## Authoritative seven-day window

Do not independently calculate `today - 7 days`.

Resolve the same authoritative production state used by the first two KPIs:

1. latest successful production history where:
   - `provider = motive`;
   - `provider_resource = vehicle_utilization`;
   - `mode = production_recent_window_ingestion`;
   - `status = success`;
2. matching successful production checkpoint;
3. persisted `completed_through`;
4. seven exact `America/Chicago` calendar days ending on `completed_through`, inclusive.

If production history/checkpoint health is inconsistent or not healthy, this KPI is unavailable.

The KPI must not repair, bypass, trigger, retry, or refresh production ingestion.

## Historical requested population

Use `selected_vehicle_count` from the matching successful production history as the historical requested denominator.

Expected requested vehicle-days:

`selected_vehicle_count * 7`

Do not substitute current fleet count for the historical denominator.

Reuse the same conservative current-population compatibility guard as the certified utilization and idle-time-share KPIs. If current tenant vehicle population is not compatible with the successful run's historical selected count, fail closed rather than allowing stale rows to inflate coverage.

## Atomic observation

The atomic observation remains one tenant-owned durable Motive vehicle-utilization row for one exact one-day request window:

`organization_id + motive_vehicle_id + request_window_start + request_window_end`

A row may contribute to idle-fuel share only when all of the following are true:

- tenant matches the authenticated organization;
- `motive_vehicle_id` is non-null and belongs to the same tenant;
- `request_window_start == request_window_end`;
- the day is inside the authoritative seven-day production window;
- `metric_units == false`;
- `idle_fuel` is non-null;
- `driving_fuel` is non-null;
- `idle_fuel >= 0`;
- `driving_fuel >= 0`;
- `idle_fuel + driving_fuel > 0`.

## Zero, null, and invalid values

Returned numeric zero is real data, not missing data.

Examples:

- `idle_fuel = 0`, `driving_fuel > 0` is valid and contributes zero idle fuel;
- `idle_fuel > 0`, `driving_fuel = 0` is valid and may produce 100% idle-fuel share if it is the only contributing fuel;
- `idle_fuel = 0`, `driving_fuel = 0` has no positive fuel denominator and is not metric-valid for the share calculation;
- null idle or driving fuel is incomplete, not zero;
- negative fuel violates the provider total-fuel semantic expectation and must fail closed rather than be clamped, normalized, or silently excluded as harmless missing data.

No absolute-value conversion, minimum floor, inferred fuel, or synthetic denominator is allowed.

## KPI formula

For all metric-valid vehicle-day observations in the authoritative seven-day window:

`observed_idle_fuel = sum(idle_fuel)`

`observed_driving_fuel = sum(driving_fuel)`

`observed_idle_plus_driving_fuel = observed_idle_fuel + observed_driving_fuel`

KPI value:

`observed_idle_fuel / observed_idle_plus_driving_fuel * 100`

Return with deterministic display precision, recommended two decimal places.

### Ratio-of-sums, not mean of row percentages

Do **not** calculate a fuel-share percentage for each vehicle-day and then take a simple arithmetic mean.

A simple mean would give a very small fuel-volume observation the same weight as a high-volume observation.

The ratio-of-sums answers the stated business question: what share of the combined observed fuel volume was idle fuel.

Do not weight by:

- utilization percent;
- idle time;
- driving time;
- mileage;
- revenue;
- loads;
- driver hours;
- vehicle count beyond the explicit coverage calculation.

## Coverage

Coverage is mandatory context and remains vehicle-day based.

### Provider rollup coverage

`provider_rollup_vehicle_days / expected_requested_vehicle_days * 100`

`provider_rollup_vehicle_days` counts distinct tenant-owned durable rows for the exact seven one-day windows, independent of fuel completeness.

### Idle-fuel metric coverage

`metric_valid_vehicle_days / expected_requested_vehicle_days * 100`

`metric_valid_vehicle_days` counts only rows eligible for the idle-fuel-share formula.

### Missing requested vehicle-days

`expected_requested_vehicle_days - provider_rollup_vehicle_days`

Missing requested vehicle-days remain unknown provider omissions.

Never synthesize missing rows as zero fuel, zero idle, inactive, parked, or out of service.

## Availability and representativeness

### `available_observed`

Return an observed value only when:

- production operational state is healthy;
- the authoritative window and historical denominator are valid;
- at least one metric-valid vehicle-day exists;
- total observed idle-plus-driving fuel is greater than zero;
- no fail-closed data-integrity condition is present.

### `unavailable`

Return unavailable when any required operational/population contract is invalid, no metric-valid fuel exists, total observed fuel denominator is zero, or a certified-window row violates a fail-closed condition.

Never return `0%` merely because the KPI is unavailable.

### Fleet representative

`fleet_representative = true` only when idle-fuel metric coverage is exactly 100% of expected requested vehicle-days.

Below 100%, the metric remains an observed-sample statistic.

Even at 100% coverage, the KPI describes only provider-reported `idle_fuel + driving_fuel` inside the certified rollup contract; it does not become proof of total purchased fuel or avoidable fuel consumption.

## Recommended sanitized response

- `status`: `available_observed` or `unavailable`;
- `kpi`: `observed_7_day_vehicle_idle_fuel_share`;
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
- `idle_fuel_metric_coverage_percent`;
- `fleet_representative`;
- `fuel_unit`: `gallons`;
- `unit_request_mode`: `imperial`;
- `secrets_exposed`: false.

The first public response does not need raw summed gallons. The percentage plus coverage is sufficient for the first consumer and avoids unnecessary exposure of business fuel volume.

Do not expose provider vehicle IDs, Motive vehicle DB IDs, VINs, plates, unit numbers, run/history IDs, raw payloads, raw sync JSON, credentials, headers, or exception strings.

## Query and deduplication rules

The future read model must:

- scope every query by authenticated `organization_id`;
- use only the exact seven one-day request windows established from successful production history/checkpoint;
- count distinct durable vehicle-day identities;
- fail closed on unexpected duplicate full identities;
- ignore reporting-period columns for identity;
- exclude rows outside the certified window;
- exclude multi-day request-window rows;
- exclude rows without tenant-owned Motive vehicle association;
- require current production unit provenance (`metric_units == false`) for metric validity;
- never join another tenant's vehicle/history/checkpoint rows;
- never call Motive to fill missing fuel.

## Executive-attention boundary

This KPI must not alter or populate:

- Executive Dashboard `business_status`;
- Needs Attention;
- Today's Plan / Today's Priority;
- Watch Items;
- Polaris Recommendation;
- Daily Brief business status;
- Daily Brief System / Data Health;
- email;
- Slack;
- notifications;
- alerts.

No HIGH/MEDIUM/CRITICAL, GOOD/WATCH, pass/fail, benchmark, target, target-attainment, red/amber/green, or recommendation semantics are introduced.

## First implementation surface

After this design is merged, the next gate should be backend read-only only:

- tenant-scoped service;
- authenticated GET endpoint;
- existing `CONNECTOR_READ` permission;
- current certified production rows only;
- zero provider calls;
- zero database writes;
- no migration;
- no scheduler or ingestion change;
- no snapshot/history change;
- no frontend consumer yet.

## Historical trend boundary

No idle-fuel snapshot/history/trend is authorized here.

Do not reconstruct historical idle-fuel-share points later from mutable utilization rows after fleet membership changes. If a trend is desired after production certification, snapshot/history persistence must be designed separately.

## Required implementation tests

At minimum, the future backend gate must prove:

1. healthy successful production state + valid fuel rows returns `available_observed`;
2. ratio-of-sums calculation is correct;
3. real `idle_fuel = 0` is preserved;
4. real `driving_fuel = 0` is preserved;
5. `idle_fuel = driving_fuel = 0` does not create a synthetic percentage;
6. null fuel fields are incomplete, not zero;
7. negative fuel fails closed;
8. denominator comes from matching successful production history;
9. expected vehicle-days equals selected count × 7;
10. provider-rollup coverage is correct;
11. idle-fuel metric coverage is correct;
12. missing provider rows are never synthesized;
13. exact one-day window rule is enforced;
14. rows outside the certified window are excluded;
15. `metric_units != false` is excluded/fails the certified production provenance contract as appropriate;
16. current population-change safety guard matches existing KPIs;
17. zero metric-valid rows returns unavailable, never 0%;
18. zero total idle-plus-driving fuel returns unavailable;
19. unhealthy production operational state returns unavailable;
20. cross-tenant data cannot influence the result;
21. response exposes no identities, raw payloads, secrets, or exception strings;
22. service/endpoint performs zero provider calls;
23. service/endpoint performs SELECTs only and zero writes;
24. `fleet_representative` is true only at exactly 100% metric-valid vehicle-day coverage;
25. no Dashboard, Daily Brief, threshold, alert, recommendation, or business-status behavior changes.

## Production certification after implementation

After a future backend implementation merges and deploys:

1. make exactly one authenticated GET of the idle-fuel-share endpoint;
2. verify the seven-day window against the certified production state;
3. verify expected vehicle-days equals selected vehicles × 7;
4. verify provider and metric coverage arithmetic;
5. verify `fuel_unit = gallons` and `unit_request_mode = imperial`;
6. verify `secrets_exposed=false`;
7. do not trigger Motive sync, scheduler, reconciliation, or provider verification;
8. if coverage is partial, keep the result explicitly observed/non-fleet-representative;
9. do not add a frontend consumer until the backend result is production-certified.

## Non-goals

This gate does not:

- implement runtime code;
- call Motive;
- write database state;
- change ingestion or scheduler behavior;
- add snapshots/history;
- add a frontend card;
- estimate idle fuel cost;
- classify idle fuel as waste or avoidable;
- rank drivers or vehicles;
- add thresholds or benchmarks;
- change Business Status, Daily Brief, or attention surfaces.

## Next gate

After merge, implement only the read-only backend service + endpoint for `Observed 7-Day Vehicle Idle-Fuel Share`. Production-certify it before any consumer-placement decision.