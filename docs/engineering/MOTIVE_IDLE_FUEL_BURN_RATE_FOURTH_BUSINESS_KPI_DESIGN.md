# Motive Vehicle Utilization — Fourth Business KPI Design

## Status

Design gate only.

This document defines a fourth Motive business KPI from already-durable vehicle-utilization rows. It does **not** change runtime behavior, provider calls, scheduler behavior, database state, ingestion, reconciliation, snapshots/history, Dashboard output, Daily Brief output, business status, alerts, thresholds, production configuration, or frontend behavior.

The already-certified Motive business KPIs are:

1. `Observed 7-Day Vehicle Utilization`;
2. `Observed 7-Day Vehicle Idle-Time Share`;
3. `Observed 7-Day Vehicle Idle-Fuel Share`.

This gate deliberately reuses their certified production window, tenant, historical denominator, omission semantics, operational-health guard, current-population compatibility guard, and unit provenance boundaries.

## Decision

Canonical display name:

`Observed 7-Day Idle Fuel Burn Rate`

Canonical machine name:

`observed_7_day_idle_fuel_burn_rate`

Recommended first read endpoint:

`GET /api/v1/motive/fleet/vehicle-idle-fuel-burn-rate-kpi`

Permission:

`CONNECTOR_READ`

The first implementation must be read-only: zero Motive provider calls and zero database writes.

## Why this is the fourth KPI

The current certified `GET /v1/vehicle_utilization` contract gives Polaris two fields that can be combined without relying on deferred legacy columns:

- `idle_time` — provider-documented total idle time in seconds;
- `idle_fuel` — provider-documented fuel consumed while idling.

Current production requests imperial units and only accepts rows whose returned unit indicator matches the certified request mode, so accepted production `idle_fuel` values are gallons.

`distance` and `engine_hours` exist as legacy persistence columns but are explicitly **DEFERRED** in the current semantic contract and are not part of the certified v1 response contract. Therefore this gate must not create MPG, miles-per-hour, engine-hours-per-day, or any metric dependent on those fields.

Idle fuel burn rate is the strongest distinct metric available from the remaining certified data because it answers a narrow operational question with known units:

> During the idle time Motive actually reported in the latest certified seven-day observation window, how many gallons of idle fuel were reported per observed idle hour?

## Business question

The KPI answers exactly:

> Across metric-valid vehicle-day observations in the latest certified seven-day production window, what is the ratio of total Motive-reported idle fuel gallons to total Motive-reported idle hours?

It does **not** claim to answer:

- how much idle fuel was avoidable;
- whether idling was good or bad;
- whether an individual vehicle or driver performed well;
- what idle fuel cost in dollars;
- what the fleet should target;
- whether PTO, parked regeneration, cab comfort, warm-up, maintenance, or other stationary-load contexts explain the fuel consumption;
- total company fuel economy;
- road fuel economy;
- MPG;
- gallons per engine hour for all engine states;
- reefer fuel consumption.

## Interpretation boundary

This is a descriptive burn-rate metric only.

A higher or lower gallons-per-idle-hour value is not automatically better or worse. Stationary engine load can vary for legitimate operating reasons, and the current vehicle-utilization rollup does not classify those reasons.

Do not label the result:

- waste;
- avoidable fuel;
- excessive idle;
- inefficient;
- efficient;
- high;
- low;
- good;
- bad;
- target missed;
- needs attention.

No fuel-price multiplication or cost estimate is authorized in this gate.

## Source-of-truth precedence

Use the same current production-ingestion contract used by the first three KPIs.

Current production contract:

- provider endpoint: `GET /v1/vehicle_utilization`;
- latest seven completed `America/Chicago` local days;
- one exact one-day provider request per day;
- at most 100 stored tenant-owned Motive vehicles selected;
- request mode: `X-Metric-Units: false` / imperial;
- accepted returned `metric_units == false`;
- accepted `idle_fuel` values are gallons;
- `idle_time` values are seconds;
- provider omission means unknown / no returned rollup, never zero activity;
- recent history is reread and provider-derived metrics may reconcile in place.

If older comments or legacy documentation conflict with the current certified production policy, the current production-ingestion contract and current unit-policy certification take precedence.

## Authoritative seven-day window

Do not independently calculate `today - 7 days`.

Resolve the same authoritative production state used by the first three KPIs:

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

A row may contribute to idle-fuel burn rate only when all of the following are true:

- tenant matches the authenticated organization;
- `motive_vehicle_id` is non-null and belongs to the same tenant;
- request window is exactly one day;
- the day is inside the authoritative seven-day production window;
- `metric_units == false`;
- `idle_time` is non-null;
- `idle_fuel` is non-null;
- `idle_time >= 0`;
- `idle_fuel >= 0`.

## Zero, null, and invalid values

Returned numeric zero is real data, not missing data.

### Valid zero-fuel idle observation

`idle_time > 0` and `idle_fuel = 0` is valid and contributes idle time with zero idle fuel.

### No-idle observation

`idle_time = 0` and `idle_fuel = 0` is a valid provider observation but contributes **no burn-rate denominator**. It is not a metric-valid vehicle-day for the burn-rate calculation because there was no observed idle time over which a gallons-per-hour rate can be defined.

### Inconsistent zero-time positive-fuel observation

`idle_time = 0` and `idle_fuel > 0` is internally inconsistent for this KPI and must fail closed for the certified window rather than dividing by zero or silently ignoring the positive fuel.

### Null values

Null idle time or idle fuel is incomplete, not zero, and is not metric-valid.

### Negative values

Negative idle time or idle fuel violates the certified semantic expectation and must fail closed. Do not clamp, take absolute value, or silently treat it as missing.

### Non-finite values

Non-finite numeric values are invalid and must fail closed.

## KPI formula

For all metric-valid vehicle-day observations in the authoritative seven-day window:

`observed_idle_seconds = sum(idle_time)`

`observed_idle_hours = observed_idle_seconds / 3600`

`observed_idle_fuel_gallons = sum(idle_fuel)`

KPI value:

`observed_idle_fuel_gallons / observed_idle_hours`

Equivalent implementation form:

`observed_idle_fuel_gallons * 3600 / observed_idle_seconds`

Canonical unit:

`gallons_per_idle_hour`

Recommended display precision:

2 decimal places.

## Ratio-of-sums, not mean of per-row burn rates

Do **not** compute `idle_fuel / idle_hours` for each vehicle-day and then take a simple arithmetic mean.

A simple mean would give a few minutes of idling the same influence as many hours of idling.

The approved formula is the ratio of total observed idle fuel to total observed idle time so each unit of observed idle time contributes proportionally.

Do not weight by:

- utilization percentage;
- driving time;
- driving fuel;
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

`provider_rollup_vehicle_days` counts distinct tenant-owned durable rows for the exact seven one-day windows, independent of idle metric completeness.

### Idle-burn-rate metric coverage

`metric_valid_vehicle_days / expected_requested_vehicle_days * 100`

`metric_valid_vehicle_days` counts only rows with:

- certified imperial unit provenance;
- non-null non-negative idle time and idle fuel;
- positive idle time.

Rows with `idle_time = 0` and `idle_fuel = 0` remain valid provider rollups but are not burn-rate metric-valid because they have no idle-hour denominator.

### Missing requested vehicle-days

`expected_requested_vehicle_days - provider_rollup_vehicle_days`

Missing provider rollups remain unknown. Never synthesize them as zero idling, zero fuel, parked, inactive, or out of service.

## Availability and representativeness

### `available_observed`

Return an observed value only when:

- production operational state is healthy;
- authoritative window and historical denominator are valid;
- at least one metric-valid vehicle-day exists;
- total observed idle seconds is greater than zero;
- no certified-window integrity failure is present.

A valid observed result may be exactly `0.00 gal/idle-hour` if positive observed idle time exists and the summed returned idle fuel is zero.

### `unavailable`

Return unavailable when required operational/population state is invalid, there are no metric-valid idle observations, total observed idle seconds is zero, or any fail-closed integrity condition is present.

Never return numeric zero merely because the metric is unavailable.

### Fleet representative

`fleet_representative = true` only when burn-rate metric coverage is exactly 100% of expected requested vehicle-days.

Below 100%, the KPI remains an observed-sample statistic.

Even at 100% coverage, the KPI describes Motive-reported idle fuel per Motive-reported idle hour only; it does not become proof of avoidable fuel use or total company fuel efficiency.

## Recommended sanitized response

- `status`: `available_observed` or `unavailable`;
- `kpi`: `observed_7_day_idle_fuel_burn_rate`;
- `window_start`;
- `window_end`;
- `request_timezone`: `America/Chicago`;
- `value_gallons_per_idle_hour` or null;
- `selected_vehicle_count`;
- `expected_requested_vehicle_days`;
- `provider_rollup_vehicle_days`;
- `metric_valid_vehicle_days`;
- `missing_requested_vehicle_days`;
- `provider_rollup_coverage_percent`;
- `idle_fuel_burn_rate_metric_coverage_percent`;
- `fleet_representative`;
- `idle_time_unit`: `seconds`;
- `fuel_unit`: `gallons`;
- `rate_unit`: `gallons_per_idle_hour`;
- `unit_request_mode`: `imperial`;
- `secrets_exposed`: false.

The first public response does not need raw summed idle seconds or raw summed gallons. The burn rate plus coverage and units is sufficient for the first consumer and avoids unnecessary exposure of operational volume totals.

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
- never call Motive to fill missing idle time or fuel.

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

No idle-fuel-burn-rate snapshot/history/trend is authorized here.

Do not reconstruct historical burn-rate points later from mutable utilization rows after fleet membership changes. If a trend is desired after production certification, snapshot/history persistence must be designed separately.

## Required implementation tests

At minimum, the future backend gate must prove:

1. healthy successful production state + valid idle rows returns `available_observed`;
2. ratio-of-sums gallons-per-idle-hour calculation is correct;
3. conversion from seconds to hours is correct;
4. real `idle_fuel = 0` with positive idle time is preserved and may return `0.00`;
5. `idle_time = 0` and `idle_fuel = 0` is not burn-rate metric-valid;
6. `idle_time = 0` and positive idle fuel fails closed;
7. null idle fields are incomplete, not zero;
8. negative idle time fails closed;
9. negative idle fuel fails closed;
10. non-finite values fail closed;
11. denominator comes from matching successful production history;
12. expected vehicle-days equals selected count × 7;
13. provider-rollup coverage is correct;
14. burn-rate metric coverage is correct;
15. missing provider rows are never synthesized;
16. exact one-day window rule is enforced;
17. rows outside the certified window are excluded;
18. certified `metric_units == false` provenance is required;
19. current population-change safety guard matches existing KPIs;
20. zero metric-valid rows returns unavailable;
21. zero total observed idle seconds returns unavailable;
22. unhealthy production operational state returns unavailable;
23. cross-tenant data cannot influence the result;
24. response exposes no identities, raw payloads, secrets, or exception strings;
25. service/endpoint performs zero provider calls;
26. service/endpoint performs SELECTs only and zero writes;
27. `fleet_representative` is true only at exactly 100% burn-rate metric-valid vehicle-day coverage;
28. `distance` and `engine_hours` are not queried or used;
29. no Dashboard, Daily Brief, threshold, alert, recommendation, or business-status behavior changes.

## Production certification after implementation

After a future backend implementation merges and deploys:

1. make exactly one authenticated GET of the idle-fuel-burn-rate endpoint;
2. verify the seven-day window against the certified production state;
3. verify expected vehicle-days equals selected vehicles × 7;
4. verify provider and burn-rate metric coverage arithmetic;
5. verify `idle_time_unit = seconds`;
6. verify `fuel_unit = gallons`;
7. verify `rate_unit = gallons_per_idle_hour`;
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
- calculate MPG or vehicle speed;
- add snapshots/history;
- add a frontend card;
- estimate idle fuel cost;
- classify idle fuel as waste or avoidable;
- rank drivers or vehicles;
- add thresholds or benchmarks;
- change Business Status, Daily Brief, or attention surfaces.

## Next gate

After merge, implement only the read-only backend service + endpoint for `Observed 7-Day Idle Fuel Burn Rate`. Production-certify it before any consumer-placement decision.