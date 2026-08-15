# Motive Vehicle Utilization Bounded Evidence Gate

This gate adds a manual, read-only runtime evidence probe for Motive `GET /v1/vehicle_utilization`.

It is not utilization ingestion. It does not persist utilization rows, advance checkpoints, create Fleet KPIs, add Dashboard cards, or create Daily Brief attention.

## Official Docs

Official Motive documentation establishes the v1 endpoint as a vehicle utilization rollup / summary endpoint.

Documented request parameters:

- `vehicle_ids[]`
- `start_date`
- `end_date`
- `per_page`
- `page_no`

Documented response shape:

- `vehicle_idle_rollups[]`
- `vehicle_idle_rollup`
- `vehicle.id`
- `vehicle.metric_units`
- `utilization`
- `idle_time`
- `idle_fuel`
- `driving_time`
- `driving_fuel`

Documented metric semantics:

- `utilization`: percentage
- `idle_time`: seconds
- `driving_time`: seconds
- `idle_fuel`: fuel consumed while idling
- `driving_fuel`: fuel consumed while driving
- `X-Metric-Units`: metric versus imperial unit selection

Motive documents this as a rollup endpoint whose date/time behavior uses the company-configured rollup timezone. `X-Time-Zone` does not certify or control that rollup timezone for this endpoint.

## Certified Previous Production Observation

Prior controlled production verification observed the documented `vehicle_idle_rollups` envelope, `vehicle_idle_rollup` wrapper, `vehicle.id`, `vehicle.metric_units`, and all five utilization metrics.

PR #154 separated provider-schema compatibility from durable persistence readiness. Missing provider-returned reporting-period fields no longer makes the documented provider schema incompatible, but persistence remains blocked.

## New Bounded Observation

The manual endpoint is:

`POST /api/v1/motive/verify/vehicle-utilization-evidence`

It performs exactly three provider requests on a successful run:

1. `start_date = day_a`, `end_date = day_a`
2. `start_date = day_b`, `end_date = day_b`
3. `start_date = day_a`, `end_date = day_b`

`day_a` and `day_b` are two adjacent fully completed calendar days selected using Polaris' internal request-window calendar, currently `America/Winnipeg`, as:

- `day_a = local_today - 3 days`
- `day_b = local_today - 2 days`

The request-window calendar is not Motive's certified company rollup timezone.

Each provider call uses:

- the same deterministic set of up to three stored organization-owned Motive vehicles
- `per_page = selected_vehicle_count`
- `page_no = 1`
- no retry
- no page 2
- no fallback request
- no `X-Time-Zone`
- no `X-User-Id`
- backend-only `X-API-Key`
- existing optional `X-Metric-Units` behavior

## Derived Evidence

The probe may derive sanitized evidence for:

- selected vehicle count
- returned unique selected vehicle count
- missing selected vehicle count
- duplicate selected vehicle rollup count
- unexpected vehicle observed
- pagination total presence and bounded truncation risk
- safe vehicle slot presence across day A, day B, and combined windows
- zero-shaped rollup observation
- missing rollup observation
- additive metric composition across the two single-day windows and combined window

The probe compares only additive metrics:

- `idle_time`
- `driving_time`
- `idle_fuel`
- `driving_fuel`

It never adds `utilization` percentages.

The rounding-bound method uses `Decimal` representation precision:

`0.5 * quantum(day_a) + 0.5 * quantum(day_b) + 0.5 * quantum(combined)`

The result returns only classifications such as `exact_match`, `within_rounding_bound`, `mismatch`, or indeterminate states. It does not expose metric values or tolerances.

## Still Deferred

This gate does not certify universal provider behavior.

Still deferred:

- exact MOR company-configured Motive rollup timezone
- `end_date` inclusive/exclusive contract as a durable writer rule
- universal row cardinality
- no-activity semantics
- `pagination.total` business meaning
- durable idempotency key
- checkpoint advancement strategy
- unit normalization
- Fleet KPIs
- Dashboard or Daily Brief attention

Exact company rollup timezone requires external provider setting evidence from Motive company/admin configuration.

## Completed Bounded Production Evidence

The completed bounded production run selected three stored organization-owned vehicles and made exactly three provider calls: day A, day B, and the combined A-through-B window. Each call used `page_no=1`, `per_page=3`, one attempt, no retry, no persistence, and no checkpoint mutation.

Observed windows:

- day A: `2026-08-12` to `2026-08-12`
- day B: `2026-08-13` to `2026-08-13`
- combined: `2026-08-12` to `2026-08-13`

For all three windows, Motive returned one unique selected vehicle rollup out of the three requested vehicles. Two selected vehicles were absent, no duplicate selected rollups were observed, no unexpected vehicle was observed, `pagination.total` was present and equal to returned item count `1`, and no bounded truncation was observed.

For the one returned vehicle slot, `metric_units` was consistent across the three windows. `idle_time`, `driving_time`, `idle_fuel`, and `driving_fuel` each matched exactly when the two single completed days were compared with the combined window. Polaris did not add `utilization` percentages. This supports the inclusive completed-date-window interpretation for the observed returned vehicle, but it is not a universal Motive provider guarantee.

That single observation does not expose or certify the actual `metric_units` Boolean value because production diagnostics intentionally redact provider values. Separately, official Motive documentation defines `X-Metric-Units: true` as metric units, `X-Metric-Units: false` as imperial units, and the returned vehicle `metric_units` field as a Boolean unit indicator.

Polaris now defines the future durable writer's canonical unit policy as `X-Metric-Units: true` / metric. This is a Polaris-owned persistence contract, not evidence of Motive's omitted-header default and not proof that earlier manual probes used metric units. Future writes must fail closed if returned `metric_units` is false, missing, or unknown; no conversion is enabled.

No zero-activity-shaped rollup was observed. Missing selected vehicles remain absence evidence only; Polaris does not infer no activity, inactive vehicle state, or zero utilization from a missing provider rollup.

## Security Boundary

The public response must not expose:

- provider vehicle IDs
- VINs
- vehicle numbers
- raw provider payloads
- metric values
- query/header values
- API keys or secrets

The response may expose only safe counts, dates, slot labels, booleans, classifications, and fixed contract metadata.
