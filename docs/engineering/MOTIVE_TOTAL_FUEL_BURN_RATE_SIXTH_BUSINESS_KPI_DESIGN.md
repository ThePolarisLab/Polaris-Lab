# Motive Sixth Business KPI Design — Observed 7-Day Fuel Burn Rate

## Gate status

Design only.

This gate defines the sixth Motive business KPI using only already-persisted, already-certified vehicle-utilization fields. It does not add runtime code, a route, a Dashboard card, a scheduler change, a provider call, a database write, a migration, history, alerts, thresholds, or business-status logic.

## KPI

Display name:

`Observed 7-Day Fuel Burn Rate`

Canonical KPI name:

`observed_7_day_fuel_burn_rate`

Future read-only endpoint:

`GET /api/v1/motive/fleet/vehicle-fuel-burn-rate-kpi`

Permission:

`CONNECTOR_READ`

## Why this is the next safe KPI

The persisted Motive vehicle-utilization rollups already contain four fields with certified provider semantics:

- `idle_time` — seconds
- `driving_time` — seconds
- `idle_fuel` — fuel consumed while idling
- `driving_fuel` — fuel consumed while driving

Production ingestion currently requests imperial units and persists gallons for the certified production path.

`distance` and `engine_hours` remain deferred / legacy and MUST NOT be used by this KPI. Therefore this KPI is deliberately not MPG, miles per hour, gallons per mile, or engine-hour efficiency.

The KPI is distinct from the already-certified Idle Fuel Burn Rate and Driving Fuel Burn Rate because it describes the blended fuel-consumption rate across the total observed idle + driving operating time.

## Formula

For the complete seven-day window, use ratio-of-sums semantics:

`total observed fuel gallons / total observed operating hours`

where:

`total observed fuel gallons = sum(idle_fuel + driving_fuel)`

and:

`total observed operating hours = sum(idle_time + driving_time) / 3600`

Equivalent implementation formula:

`sum(idle_fuel + driving_fuel) * 3600 / sum(idle_time + driving_time)`

Do NOT calculate the arithmetic mean of per-vehicle-day burn rates.

Do NOT average the existing idle-burn-rate and driving-burn-rate KPI values.

## Window contract

Use the same latest successful production state and exact seven completed `America/Chicago` calendar days used by the existing Motive business KPIs.

The future service must inherit the same operational-health, successful-history, checkpoint, tenant, exact-window, historical selected-vehicle-count, and current-population safeguards already certified for the existing Motive KPI read models.

Expected requested vehicle-days:

`historical selected_vehicle_count * 7`

Provider omissions remain unknown and MUST NOT become synthetic zero rows.

## Valid vehicle-day semantics

A returned one-day rollup is metric-valid for this KPI only when all of the following are true:

- tenant matches the authenticated organization;
- provider is `motive`;
- row belongs to the exact seven-day candidate window;
- request window is exactly one day;
- returned unit provenance matches the certified production imperial contract;
- `idle_time` is finite and non-negative;
- `driving_time` is finite and non-negative;
- `idle_fuel` is finite and non-negative;
- `driving_fuel` is finite and non-negative.

Let:

`operating_seconds = idle_time + driving_time`

`fuel_gallons = idle_fuel + driving_fuel`

Then:

- `operating_seconds > 0` and `fuel_gallons >= 0` is valid;
- `operating_seconds > 0` and `fuel_gallons == 0` is a legitimate real zero contribution;
- `operating_seconds == 0` and `fuel_gallons == 0` has no burn-rate denominator and is not metric-valid;
- `operating_seconds == 0` and `fuel_gallons > 0` is internally inconsistent and the KPI must fail closed rather than silently divide or discard the anomaly;
- any negative or non-finite time/fuel value must fail closed.

A missing/null component means the vehicle-day is not metric-valid. Null MUST NOT become zero.

## Aggregation semantics

For all metric-valid vehicle-days in the exact seven-day window:

1. Sum `idle_fuel + driving_fuel` across rows.
2. Sum `idle_time + driving_time` across rows.
3. Convert summed seconds to hours only at the final ratio boundary.
4. Compute the ratio-of-sums.
5. Round the public KPI value to two decimals.

A legitimate resulting `0.00` must remain zero and must not become unavailable.

If no metric-valid vehicle-day contributes a positive total operating-time denominator, the KPI is unavailable.

## Coverage

Keep provider-rollup coverage separate from KPI-valid coverage.

Provider rollup coverage:

`provider_rollup_vehicle_days / expected_requested_vehicle_days * 100`

Fuel burn-rate metric coverage:

`metric_valid_vehicle_days / expected_requested_vehicle_days * 100`

The public Dashboard, if implemented in a later gate, must use metric-valid coverage for the KPI display rather than the broader provider-rollup coverage.

Missing requested vehicle-days:

`expected_requested_vehicle_days - provider_rollup_vehicle_days`

Provider omissions remain unknown, never zero fuel/time.

## Fleet representativeness

`fleet_representative = true` only when fuel burn-rate metric coverage is exactly 100%.

Any partial metric coverage must return `fleet_representative = false`.

The KPI may still be `available_observed` with partial coverage when at least one valid vehicle-day exists and the operational contract is otherwise healthy.

## Future response contract

A future successful response may contain only aggregate/safe fields such as:

- `status`
- `kpi`
- `window_start`
- `window_end`
- `request_timezone`
- `value_gallons_per_observed_hour`
- `selected_vehicle_count`
- `expected_requested_vehicle_days`
- `provider_rollup_vehicle_days`
- `metric_valid_vehicle_days`
- `missing_requested_vehicle_days`
- `provider_rollup_coverage_percent`
- `fuel_burn_rate_metric_coverage_percent`
- `fleet_representative`
- `fuel_unit`
- `idle_time_unit`
- `driving_time_unit`
- `rate_unit`
- `unit_request_mode`
- `secrets_exposed`

Expected units for the current production contract:

- `fuel_unit = "gallons"`
- `idle_time_unit = "seconds"`
- `driving_time_unit = "seconds"`
- `rate_unit = "gallons_per_observed_hour"`
- `unit_request_mode = "imperial"`

## Public-surface exclusions

The response MUST NOT expose:

- provider vehicle IDs;
- Motive vehicle database IDs;
- VINs;
- plates;
- unit numbers;
- source history IDs;
- run IDs;
- raw summed fuel totals;
- raw summed time totals;
- raw provider payloads;
- credentials, tokens, headers, secrets, or exception strings.

`secrets_exposed` must always be `false`.

## Read-only requirement

The future KPI service and endpoint must be SELECT-only.

They must perform:

- zero Motive/provider HTTP calls;
- zero database writes;
- zero checkpoint updates;
- zero sync-history writes;
- zero scheduler changes;
- zero reconciliation changes;
- zero retry/provider behavior.

The KPI is computed only from already-durable certified rows.

## Business interpretation guardrails

This KPI is a descriptive operating-rate observation only.

It MUST NOT be presented as:

- MPG;
- fuel efficiency;
- fuel economy;
- waste;
- avoidable fuel use;
- excess consumption;
- a driver score;
- a vehicle score;
- a cost estimate;
- savings opportunity;
- target performance;
- high/low/good/bad status.

The observed rate can vary with the mixture of idling and driving, road speed, payload, traffic, terrain, weather, equipment characteristics, and other operating conditions.

No business threshold is authorized in this gate.

No alert, Needs Attention item, Today’s Plan item, recommendation, Daily Brief item, Business Status effect, Slack/email message, or ranking is authorized.

## Why not other candidate KPIs

### Driving-Time Share

Rejected as redundant because it is the direct complement of Idle-Time Share when both components are present.

### Driving-Fuel Share

Rejected as redundant because it is the direct complement of Idle-Fuel Share when both components are present.

### MPG / gallons per mile

Rejected because `distance` remains deferred / legacy for this provider contract.

### Engine-hour fuel rate

Rejected because `engine_hours` remains deferred / legacy.

### Idle-to-driving burn-rate ratio

Deferred because it is a derivative comparison of two already-certified burn-rate KPIs and is less directly interpretable than the blended observed operating burn rate.

## Future implementation gate

After this design is merged, the next gate may implement only:

1. one tenant-scoped read-only backend service;
2. one `CONNECTOR_READ` GET endpoint;
3. focused backend tests covering ratio-of-sums semantics, zero/null/inconsistent denominators, tenant isolation, coverage, population guard, SELECT-only behavior, sanitized output, and a hard prohibition on Motive provider calls.

That implementation gate must not include frontend placement, history, snapshot persistence, provider calls, ingestion changes, thresholds, alerts, costs, or business interpretation.

Frontend placement, if desired after production certification, must be a separate later design gate.