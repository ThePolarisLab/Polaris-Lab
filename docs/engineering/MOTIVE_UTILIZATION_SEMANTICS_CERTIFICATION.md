# Motive Vehicle Utilization Semantics Certification

This Fleet Operations V1 gate certifies provider semantics for the current Motive `GET /v1/vehicle_utilization` contract without enabling ingestion.

It adds no scheduler, no broad Motive sync, no checkpoint advancement, no Fleet KPI, no Dashboard card, and no Daily Brief attention.

## Official-Doc Confirmation

Official Motive documentation describes `GET /v1/vehicle_utilization` as a vehicle utilization summary / rollup endpoint.

Confirmed request filters:

- `vehicle_ids[]`
- `start_date`
- `end_date`
- `per_page`
- `page_no`

Confirmed documented response structure:

```text
vehicle_idle_rollups[]
  vehicle_idle_rollup
    vehicle
      id
      metric_units
    utilization
    idle_time
    idle_fuel
    driving_time
    driving_fuel
```

Confirmed semantics:

- `vehicle.id` is the provider vehicle identity.
- `vehicle.metric_units` is a boolean indicating whether metric units are used.
- `utilization` is vehicle utilization rate expressed as a percentage.
- `idle_time` is total idle time in seconds.
- `driving_time` is total driving time in seconds.
- `idle_fuel` is fuel consumed while idling.
- `driving_fuel` is fuel consumed while driving.
- `X-Metric-Units` selects metric versus imperial unit system.
- The endpoint is pre-aggregated / rollup.
- Rollup timestamps are computed in the company-configured rollup timezone and are not controlled by `X-Time-Zone`.

Polaris does not certify `America/Winnipeg` as Motive's company-configured rollup timezone. Polaris uses it only as the local calendar for choosing the temporary verifier's completed-day request window.

## Controlled Production Observation

The controlled production verifier observed:

- top-level object
- `pagination`
- `vehicle_idle_rollups`
- item wrapper `vehicle_idle_rollup`
- item keys `driving_fuel`, `driving_time`, `idle_fuel`, `idle_time`, `utilization`, and `vehicle`
- nested vehicle keys including `id` and `metric_units`
- vehicle identity path `vehicle.id`
- unit metadata path `vehicle_idle_rollups[].vehicle_idle_rollup.vehicle.metric_units`
- no provider utilization record ID
- no provider-returned reporting-period start/end fields

## Type Boundary

Official Motive docs describe:

- `utilization` as `String`
- `idle_time` as `Integer`
- `driving_time` as `Integer`
- `idle_fuel` as `String`
- `driving_fuel` as `String`

Controlled production returned numeric JSON values for the observed metrics.

This is not treated as an error. Polaris intentionally accepts safe finite numeric JSON values and safe finite numeric strings, preserving `0` separately from `NULL`.

## Certification Matrix

| Field | Evidence | Classification | Persistence field | Dashboard / Daily Brief |
| --- | --- | --- | --- | --- |
| `provider_vehicle_id` | Official docs + production path `vehicle.id` | CONFIRMED | `provider_vehicle_id` | No |
| `utilization_percent` | Official percent semantics + production metric | CONFIRMED | `utilization_percent` | No |
| `idle_time` | Official seconds semantics + production metric | CONFIRMED | `idle_time` | No |
| `driving_time` | Official seconds semantics + production metric | CONFIRMED | `driving_time` | No |
| `idle_fuel` | Official idle fuel semantics + production metric | CONFIRMED | `idle_fuel` | No |
| `driving_fuel` | Official driving fuel semantics + production metric | CONFIRMED | `driving_fuel` | No |
| `metric_units` | Official boolean unit-system indicator | CONFIRMED | `metric_units` | No |
| `request_window_start` | Official `start_date` request parameter | CONFIRMED_REQUEST_CONTEXT | `request_window_start` | No |
| `request_window_end` | Official `end_date` request parameter | CONFIRMED_REQUEST_CONTEXT | `request_window_end` | No |
| `reporting_period_start` | Not returned by documented v1 item | DEFERRED | `reporting_period_start` | No |
| `reporting_period_end` | Not returned by documented v1 item | DEFERRED | `reporting_period_end` | No |
| `distance` | Not part of documented v1 vehicle-utilization response | DEFERRED / LEGACY | `distance` | No |
| `engine_hours` | Not part of documented v1 vehicle-utilization response | DEFERRED / LEGACY | `engine_hours` | No |

## Provider Schema Compatibility

The production-observed, officially documented `vehicle_idle_rollups` envelope is provider-schema compatible.

Absence of provider-returned reporting-period fields no longer makes the provider schema incompatible. That absence remains important for durable persistence design, but it is not a provider-contract failure because the official endpoint is documented as a request-window summary.

## Persistence Readiness

The schema is ready for a future writer shape, but durable ingestion remains blocked.

Current status:

- `schema_ready_for_future_writer_shape = true`
- `writer_enabled = false`
- `persistence_enabled = false`
- `checkpoint_advancement_enabled = false`
- `scheduled_sync_enabled = false`
- `broad_sync_enabled = false`
- Polaris-owned replay/idempotency identity = `CERTIFIED`
- provider natural key = `NOT_RETURNED` / `NOT_CERTIFIED`
- database uniqueness enforcement = `DISABLED` / `NOT_IMPLEMENTED`

The existing nullable unique constraint on `organization_id + provider_vehicle_id + reporting_period_start + reporting_period_end` is not certified as a future utilization idempotency key.

The certified Polaris-owned replay identity is `organization_id + motive_vehicle_id + request_window_start + request_window_end` under the canonical writer unit policy `X-Metric-Units: true`. That certification does not enable writes, does not claim Motive returned a provider natural key, and does not add database enforcement yet.

## Still Deferred

- exact `end_date` inclusive/exclusive boundary behavior
- exact MOR company-configured rollup timezone value
- returned-row cardinality for requested vehicles
- no-activity vehicle behavior
- `pagination.total` business meaning for future ingestion
- provider natural key not returned / not certified
- database uniqueness enforcement
- writer transaction implementation
- empty-result interpretation
- conversion to one internal unit system
- checkpoint advancement strategy
- MOR business interpretation of utilization
- alert thresholds and Fleet KPI semantics

## Bounded Evidence Gate

The next gate adds a separate manual endpoint:

`POST /api/v1/motive/verify/vehicle-utilization-evidence`

It performs exactly three bounded provider calls against the same selected organization-owned vehicles:

- day A only
- day B only
- combined day A through day B

The probe compares only additive metrics and never adds utilization percentages.

This is runtime evidence only. It remains few-vehicle, few-request, sanitized, and non-persistent. It does not certify universal provider cardinality, no-activity semantics, exact company rollup timezone, final durable idempotency identity, or checkpoint advancement.

## Durable Writer Contract Gate

The next gate adds a read-only writer-contract endpoint:

`GET /api/v1/motive/fleet/vehicle-utilization-writer-contract`

This endpoint records the completed bounded production evidence and defines the fail-closed contract a future durable writer must follow. It does not enable the writer, persist utilization rows, advance checkpoints, schedule ingestion, request Motive, or create Dashboard / Daily Brief attention.

The future writer may persist only returned Motive rollups that:

- use the certified `vehicle_idle_rollups[] -> vehicle_idle_rollup` envelope;
- map `vehicle.id` to exactly one existing organization-owned `motive_vehicles` row;
- were included in the authenticated organization's requested vehicle set;
- pass certified metric parser validation;
- are not duplicate returned rollups for the same vehicle and request window;
- are not unexpected vehicles;
- have complete pagination for the writer's requested page set.

Missing requested vehicles remain classified as `provider_rollup_absent`. Absence must not synthesize a utilization row, zero metrics, inactive state, or no-activity classification.

The proposed Polaris-owned idempotency boundary for returned, validated rollups is:

`organization_id + motive_vehicle_id + request_window_start + request_window_end`

This key is now certified as a Polaris-owned replay/idempotency identity for a future writer only under Polaris's fixed canonical unit policy: the durable writer must request `X-Metric-Units: true`, treat the canonical unit system as metric, and require returned `vehicle.metric_units == true`. This does not certify Motive's default behavior when the header is omitted. The existing verifier/evidence request boundary may still use `POLARIS_MOTIVE_X_METRIC_UNITS` for manual probes, but that environment value is not authoritative for future durable writes.

Future writes must reject replays that would change unit mode for an existing vehicle/window, fail closed if returned `metric_units` is missing, unknown, or inconsistent with the certified metric policy, and must not silently convert values. `metric_units` is not added to the durable key because Polaris should not create parallel metric and imperial rows for the same vehicle/request window. Database uniqueness, persistence, writer transactions, and checkpoint advancement remain disabled or blocked. The pagination contract itself is now certified — see `MOTIVE_UTILIZATION_PAGINATION_CONTRACT.md` — but broad writer enablement remains blocked pending the remaining writer-transaction and checkpoint work.

The request window remains request context. Polaris must not copy it into provider reporting-period fields because the provider item does not return reporting-period start/end fields.

Scheduled daily ingestion and automatic checkpoint-window calculation remain blocked until the exact company-configured Motive rollup timezone is known. Broad write ingestion remains blocked until the durable writer transaction, database uniqueness, and checkpoint advancement are implemented; the pagination-reader blocker itself has been resolved.
