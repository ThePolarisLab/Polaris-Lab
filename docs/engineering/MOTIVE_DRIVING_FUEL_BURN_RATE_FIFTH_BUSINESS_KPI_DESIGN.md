# Motive Vehicle Utilization — Fifth Business KPI Design

## Status

Design gate only.

This document defines a fifth Motive business KPI from already-durable vehicle-utilization rows. It does **not** change runtime behavior, provider calls, scheduler behavior, database state, ingestion, reconciliation, snapshots/history, Dashboard output, Daily Brief output, business status, alerts, thresholds, production configuration, or frontend behavior.

The already production-certified Motive business KPIs are:

1. `Observed 7-Day Vehicle Utilization`;
2. `Observed 7-Day Vehicle Idle-Time Share`;
3. `Observed 7-Day Vehicle Idle-Fuel Share`;
4. `Observed 7-Day Idle Fuel Burn Rate`.

This gate deliberately reuses their certified production window, tenant, historical denominator, omission semantics, operational-health guard, current-population compatibility guard, and unit provenance boundaries.

## Decision

Canonical display name:

`Observed 7-Day Driving Fuel Burn Rate`

Canonical machine name:

`observed_7_day_driving_fuel_burn_rate`

Recommended first read endpoint:

`GET /api/v1/motive/fleet/vehicle-driving-fuel-burn-rate-kpi`

Permission:

`CONNECTOR_READ`

The first implementation must be read-only: zero Motive provider calls and zero database writes.

## Why this is the fifth KPI

The certified Motive `GET /v1/vehicle_utilization` contract already provides two fields with known semantics and units:

- `driving_time` — provider-documented total driving time in seconds;
- `driving_fuel` — provider-documented fuel consumed while driving.

Current production requests imperial units and accepts only returned rows with `metric_units == false`, so accepted production `driving_fuel` values are gallons.

`distance` and `engine_hours` remain explicitly **DEFERRED** and must not be used. Therefore this KPI is **not** MPG, fuel economy, average speed, or engine-hours-based consumption.

Two other obvious candidates are deliberately rejected as redundant:

- driving-time share is the complement of the already-certified idle-time share within the same idle+driving denominator;
- driving-fuel share is the complement of the already-certified idle-fuel share within the same idle+driving fuel denominator.

Driving fuel burn rate is distinct because it answers a separate rate question with known units:

> During Motive-reported driving time in the latest certified seven-day observation window, how many gallons of driving fuel were reported per observed driving hour?

## Business question

The KPI answers exactly:

> Across metric-valid vehicle-day observations in the latest certified seven-day production window, what is the ratio of total Motive-reported driving fuel gallons to total Motive-reported driving hours?

It does **not** claim to answer:

- miles per gallon;
- fuel economy;
- route efficiency;
- driver efficiency;
- dispatch efficiency;
- whether a higher or lower gallons-per-driving-hour value is good or bad;
- what driving fuel cost in dollars;
- total company fuel purchases;
- engine-hours-based fuel consumption;
- reefer fuel consumption;
- whether traffic, grade, payload, weather, road speed, warm-up, regeneration, PTO, or other operating context explains the observed rate.

## Interpretation boundary

This is a descriptive driving burn-rate metric only.

A higher or lower gallons-per-driving-hour value is not automatically better or worse. The same truck can consume different gallons per driving hour under different speeds, payloads, terrain, traffic, weather, and operating conditions. Without certified distance and contextual data, this KPI must not be presented as fuel efficiency.

Do not label the result:

- efficient;
- inefficient;
- high;
- low;
- good;
- bad;
- excessive;
- waste;
- avoidable fuel;
- target missed;
- needs attention.

No fuel-price multiplication or cost estimate is authorized in this gate.

## Source-of-truth precedence

Use the current certified production-ingestion contract shared by the first four KPIs.

Current production contract:

- provider endpoint: `GET /v1/vehicle_utilization`;
- latest seven completed `America/Chicago` local days;
- one exact one-day provider request per day;
- at most 100 stored tenant-owned Motive vehicles selected;
- request mode: `X-Metric-Units: false` / imperial;
- accepted returned `metric_units == false`;
- accepted `driving_fuel` values are gallons;
- `driving_time` values are seconds;
- provider omission means unknown / no returned rollup, never zero activity;
- recent history is reread and provider-derived metrics may reconcile in place.

If older comments or legacy documentation conflict with current certified production behavior, the current production-ingestion contract and current unit-policy certification take precedence.

## Authoritative seven-day window

Do not independently calculate `today - 7 days`.

Resolve the same authoritative production state used by the first four KPIs:

1. latest successful production history where:
   - `provider = motive`;
   - `provider_resource = vehicle_utilization`;
   - `mode = production_recent_window_ingestion`;
   - `status = success`;
2. matching successful production checkpoint;
3. persisted `completed_through`;
4. seven exact `America/Chicago` calendar days ending on `completed_through`, inclusive.

If production history/checkpoint health is inconsistent or unhealthy, this KPI is unavailable.

The KPI must never trigger, retry, repair, or refresh production ingestion.

## Historical requested population

Use `selected_vehicle_count` from the matching successful production history as the historical requested denominator.

Expected requested vehicle-days:

`selected_vehicle_count * 7`

Do not substitute current fleet count for the historical denominator.

Reuse the same conservative current-population compatibility guard as the existing certified KPIs. If current tenant Motive vehicle population is incompatible with the historical successful run population, fail closed rather than allowing stale rows to inflate coverage.

## Atomic observation

The atomic observation remains one tenant-owned durable Motive vehicle-utilization row for one exact one-day request window:

`organization_id + motive_vehicle_id + request_window_start + request_window_end`

A row may contribute to driving-fuel burn rate only when all of the following are true:

- tenant matches the authenticated organization;
- `motive_vehicle_id` is non-null and belongs to the same tenant;
- request window is exactly one day;
- the day is inside the authoritative seven-day production window;
- `metric_units == false`;
- `driving_time` is non-null;
- `driving_fuel` is non-null;
- `driving_time >= 0`;
- `driving_fuel >= 0`.

## Zero, null, and invalid values

Returned numeric zero is real data, not missing data.

### Valid zero-fuel driving observation

`driving_time > 0` and `driving_fuel = 0` is valid and contributes driving time with zero driving fuel.

### No-driving observation

`driving_time = 0` and `driving_fuel = 0` is a valid provider observation but contributes **no burn-rate denominator**. It is not metric-valid for the driving burn-rate calculation because no observed driving hour exists over which a gallons-per-hour rate can be defined.

### Inconsistent zero-time positive-fuel observation

`driving_time = 0` and `driving_fuel > 0` is internally inconsistent for this KPI and must fail closed for the certified window rather than dividing by zero or silently ignoring positive fuel.

### Null values

Null driving time or driving fuel is incomplete, not zero, and is not metric-valid.

### Negative values

Negative driving time or driving fuel violates the certified semantic expectation and must fail closed. Do not clamp, take absolute value, or silently treat it as missing.

### Non-finite values

Non-finite numeric values are invalid and must fail closed.

## KPI formula

For all metric-valid vehicle-day observations in the authoritative seven-day window:

`observed_driving_seconds = sum(driving_time)`

`observed_driving_hours = observed_driving_seconds / 3600`

`observed_driving_fuel_gallons = sum(driving_fuel)`

KPI value:

`observed_driving_fuel_gallons / observed_driving_hours`

Equivalent implementation form:

`observed_driving_fuel_gallons * 3600 / observed_driving_seconds`

Canonical unit:

`gallons_per_driving_hour`

Recommended display precision:

2 decimal places.

## Ratio-of-sums, not mean of per-row rates

Do **not** compute `driving_fuel / driving_hours` for each vehicle-day and then take a simple arithmetic mean.

A simple mean would give a few minutes of driving the same influence as many hours of driving.

The approved formula is the ratio of total observed driving fuel to total observed driving time so each unit of observed driving time contributes proportionally.

Do not weight by:

- utilization percentage;
- idle time;
- idle fuel;
- vehicle count beyond explicit coverage;
- distance;
- engine hours;
- revenue;
- loads;
- driver hours.

## Coverage

Coverage is mandatory context and remains vehicle-day based.

### Provider rollup coverage

`provider_rollup_vehicle_days / expected_requested_vehicle_days * 100`

`provider_rollup_vehicle_days` counts distinct tenant-owned durable rows for the exact seven one-day windows, independent of driving metric completeness.

### Driving-burn-rate metric coverage

`metric_valid_vehicle_days / expected_requested_vehicle_days * 100`

`metric_valid_vehicle_days` counts only rows with:

- certified imperial unit provenance;
- non-null non-negative driving time and driving fuel;
- positive driving time.

Rows with `driving_time = 0` and `driving_fuel = 0` remain valid provider rollups but are not driving-burn-rate metric-valid because they have no driving-hour denominator.

### Missing requested vehicle-days

`expected_requested_vehicle_days - provider_rollup_vehicle_days`

Missing provider rollups remain unknown. Never synthesize them as zero driving, zero fuel, parked, inactive, or out of service.

## Availability and representativeness

### `available_observed`

Return an observed value only when:

- production operational state is healthy;
- authoritative window and historical denominator are valid;
- at least one metric-valid vehicle-day exists;
- total observed driving seconds is greater than zero;
- no certified-window integrity failure is present.

A valid observed result may be exactly `0.00 gal/driving-hour` if positive observed driving time exists and summed returned driving fuel is zero.

### `unavailable`

Return unavailable when required operational/population state is invalid, there are no metric-valid driving observations, total observed driving seconds is zero, or any fail-closed integrity condition is present.

Never return numeric zero merely because the metric is unavailable.

### Fleet representative

`fleet_representative = true` only when driving-burn-rate metric coverage is exactly 100% of expected requested vehicle-days.

Below 100%, the KPI remains an observed-sample statistic.

Even at 100% coverage, the KPI describes Motive-reported driving fuel per Motive-reported driving hour only; it does not become MPG or proof of fleet fuel efficiency.

## Recommended sanitized response

- `status`: `available_observed` or `unavailable`;
- `kpi`: `observed_7_day_driving_fuel_burn_rate`;
- `window_start`;
- `window_end`;
- `request_timezone`: `America/Chicago`;
- `value_gallons_per_driving_hour` or null;
- `selected_vehicle_count`;
- `expected_requested_vehicle_days`;
- `provider_rollup_vehicle_days`;
- `metric_valid_vehicle_days`;
- `missing_requested_vehicle_days`;
- `provider_rollup_coverage_percent`;
- `driving_fuel_burn_rate_metric_coverage_percent`;
- `fleet_representative`;
- `driving_time_unit`: `seconds`;
- `fuel_unit`: `gallons`;
- `rate_unit`: `gallons_per_driving_hour`;
- `unit_request_mode`: `imperial`;
- `secrets_exposed`: false.

The public response does not need raw summed driving seconds or raw summed gallons. The burn rate plus coverage and units is sufficient for the first consumer and avoids unnecessary exposure of operational volume totals.

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
- never call Motive to fill missing driving time or fuel.

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

No driving-fuel-burn-rate snapshot/history/trend is authorized here.

Do not reconstruct historical driving-burn-rate points later from mutable utilization rows after fleet membership changes. If a trend is desired after production certification, snapshot/history persistence must be designed separately.

## Required implementation tests

At minimum, the future backend gate must prove:

1. healthy successful production state + valid driving rows returns `available_observed`;
2. ratio-of-sums gallons-per-driving-hour calculation is correct;
3. seconds-to-hours conversion is correct;
4. real `driving_fuel = 0` with positive driving time is preserved and may return `0.00`;
5. `driving_time = 0` and `driving_fuel = 0` is not driving-burn-rate metric-valid;
6. `driving_time = 0` and positive driving fuel fails closed;
7. null driving fields are incomplete, not zero;
8. negative driving time fails closed;
9. negative driving fuel fails closed;
10. non-finite values fail closed;
11. denominator comes from matching successful production history;
12. expected vehicle-days equals selected count × 7;
13. provider-rollup coverage is correct;
14. driving-burn-rate metric coverage is correct;
15. missing provider rows are never synthesized;
16. exact one-day window rule is enforced;
17. rows outside the certified window are excluded;
18. certified `metric_units == false` provenance is required;
19. current population-change safety guard matches existing KPIs;
20. zero metric-valid rows returns unavailable;
21. zero total observed driving seconds returns unavailable;
22. unhealthy production operational state returns unavailable;
23. cross-tenant data cannot influence the result;
24. response exposes no identities, raw payloads, secrets, or exception strings;
25. service/endpoint performs zero provider calls;
26. service/endpoint performs SELECTs only and zero writes;
27. `fleet_representative` is true only at exactly 100% driving-burn-rate metric-valid vehicle-day coverage;
28. `distance` and `engine_hours` are not queried or used;
29. no Dashboard, Daily Brief, threshold, alert, recommendation, or business-status behavior changes.

## Production certification after implementation

After a future backend implementation merges and deploys:

1. make exactly one authenticated GET of the driving-fuel-burn-rate endpoint;
2. verify the seven-day window against the certified production state;
3. verify expected vehicle-days equals selected vehicles × 7;
4. verify provider and driving-burn-rate metric coverage arithmetic;
5. verify `driving_time_unit = seconds`;
6. verify `fuel_unit = gallons`;
7. verify `rate_unit = gallons_per_driving_hour`;
8. verify `unit_request_mode = imperial`;
9. verify `secrets_exposed=false`;
10. do not trigger Motive sync, scheduler, reconciliation, or provider verification;
11. if coverage is partial, keep the result explicitly observed/non-fleet-representative;
12. do not add a frontend consumer until the backend result is production-certified.

## Non-goals

This gate does not:

- implement runtime code;
- call Motive;
- write database state;
- change ingestion or scheduler behavior;
- use legacy `distance` or `engine_hours` columns;
- calculate MPG, fuel economy, or vehicle speed;
- add snapshots/history;
- add a frontend card;
- estimate driving fuel cost;
- classify driving fuel as efficient, inefficient, wasteful, or avoidable;
- rank drivers or vehicles;
- add thresholds or benchmarks;
- change Business Status, Daily Brief, or attention surfaces.

## Next gate

After merge, implement only the read-only backend service + endpoint for `Observed 7-Day Driving Fuel Burn Rate`. Production-certify it before any Dashboard placement decision.