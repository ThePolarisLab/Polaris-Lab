# Motive Vehicle Utilization Schema Hardening

This Fleet Operations V1 slice prepares the existing Motive vehicle-utilization persistence table for a later organization-scoped ingestion path.

It does not enable utilization ingestion, scheduler behavior, broad Motive sync, Fleet Dashboard KPIs, Daily Brief attention, vehicle-driver assignment inference, alerts, or checkpoint advancement.

## Existing Evidence

Production contract work has verified only the controlled temporary request shape for:

`GET /v1/vehicle_utilization`

The production-observed success envelope used:

- top-level keys `pagination` and `vehicle_idle_rollups`
- item wrapper `vehicle_idle_rollup`
- metrics `utilization`, `idle_time`, `idle_fuel`, `driving_time`, and `driving_fuel`
- vehicle identity path `vehicle.id`
- unit metadata path `vehicle.metric_units`

The observed item did not expose a provider utilization record ID or true provider reporting-period start/end fields. Request dates remain request context until Motive semantics are confirmed.

## Schema Hardening

The historical `motive_vehicle_utilization` table existed before durable utilization ingestion was certified. It kept organization ownership and a tentative period uniqueness constraint, but it did not fully represent the production-observed vehicle-idle-rollup metrics or a safe internal vehicle association.

The schema is hardened additively with:

- `motive_vehicle_id` as an optional FK to the existing organization-owned Motive vehicle row
- `request_window_start` and `request_window_end` as request-context dates, not certified provider reporting periods
- `idle_time`, `driving_time`, `idle_fuel`, and `driving_fuel`
- `metric_units`
- `parser_version`

Existing `reporting_period_start` and `reporting_period_end` remain nullable and deferred. They must not be populated as authoritative reporting-period fields until provider semantics are resolved.

## Future Writer Constraints

A future ingestion writer must:

- associate `vehicle.id` only to an existing `MotiveVehicleRecord` in the same organization
- never auto-create vehicles from utilization payloads
- preserve legitimate zero metric values separately from missing or `NULL` values
- store observed request-window context without claiming it is the provider reporting period
- keep source payload metadata sanitized and avoid raw provider payloads
- update checkpoints only after all durable persistence for the completed ingestion unit succeeds

The existing nullable uniqueness constraint is not sufficient by itself for a future writer. Before writes are enabled, the writer must enforce a non-null idempotency contract that is consistent with Motive's confirmed reporting-period and rollup-cardinality semantics.

## Deferred Semantics

The following remain deferred and must not be inferred in this slice:

- `end_date` inclusive or exclusive meaning
- whether each rollup spans the full requested window, one day, or another interval
- no-activity vehicle behavior
- `pagination.total` meaning
- unit conversion or normalization
- durable reporting-period natural key
- checkpoint window advancement strategy
