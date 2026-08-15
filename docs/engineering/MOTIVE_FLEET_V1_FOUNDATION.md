# Motive / Fleet Operations V1 Foundation

Motive Fleet Operations V1 follows the established Polaris path:

source -> module -> exception/attention logic -> executive dashboard -> Daily Brief -> drill-down.

This foundation does not add a fleet dashboard, broad synchronization, automatic Motive sync, or Daily Brief attention. It exposes a read-only production contract and persistence gate from existing tenant-owned Motive state.

## Confirmed

- Production runtime: `chief-of-staff` Python/FastAPI.
- Authentication: administrator-managed Motive Company API Key at the backend provider boundary.
- OAuth production behavior is disabled; OAuth tables remain dormant reference architecture.
- Vehicle ingestion uses `GET /v1/vehicles` with one-based `page_no`, `per_page=100`, and existing retry/rate-limit handling.
- Company-user ingestion uses `GET /v1/users` with one-based `page_no`, `per_page=100`, and existing retry/rate-limit handling.
- Vehicle records are persisted by `organization_id + provider_vehicle_id`.
- Company-user records are persisted by `organization_id + provider_driver_id`; the column name remains historical, while driver classification is not certified.
- Existing `motive_sync_history` and `motive_sync_checkpoints` remain the source of feed/run health and checkpoint safety.

## Derived

- `total_known_vehicles`: count of organization-scoped `motive_vehicles` rows.
- `total_known_company_users`: count of organization-scoped stored `/v1/users` rows.

These are safe foundation counts, not fleet utilization or driver-availability KPIs.

## Deferred

- Vehicle active/inactive business-state semantics.
- Driver classification.
- Vehicle/driver association.
- Vehicle-utilization reporting-period and cardinality semantics.
- Driver utilization.
- IFTA summary ingestion.
- Fleet operational exceptions.
- Motive-generated Dashboard or Daily Brief attention.
- Broad or automatic Motive synchronization.

## Foundation Endpoint

`GET /api/v1/motive/fleet/foundation`

The endpoint is authenticated, organization-scoped, read-only, and returns:

- confirmed contracts;
- derived metric counts;
- deferred semantics;
- existing vehicle/user persistence state;
- checkpoint safety state;
- Dashboard/Daily Brief integration boundary;
- security flags.

It does not return provider vehicle IDs, user IDs, VINs, emails, raw provider payloads, headers, secrets, or Motive API keys.

## Vehicle Contract Certification

`GET /api/v1/motive/fleet/vehicle-contract`

The vehicle contract endpoint certifies the current `GET /v1/vehicles` persisted field subset for Fleet Operations V1. It exposes field definitions, `CONFIRMED` / `DERIVED` / `DEFERRED` classifications, organization-scoped vehicle counts, and completeness percentages for persisted fields only.

See `docs/engineering/MOTIVE_VEHICLE_CONTRACT_CERTIFICATION.md`.

## Driver / User Contract Certification

`GET /api/v1/motive/fleet/driver-contract`

The driver/user contract endpoint certifies the current `GET /v1/users` persisted field subset for Fleet Operations V1. It exposes field definitions, `CONFIRMED` / `DERIVED` / `DEFERRED` classifications, organization-scoped company-user counts, and completeness percentages for persisted fields and selected metadata keys only.

`/v1/users` returns company users; Motive provider role is certified as a literal discriminator, but MOR driver classification, active-driver business state, HOS/availability, and vehicle-driver association remain deferred.

See `docs/engineering/MOTIVE_DRIVER_CONTRACT_CERTIFICATION.md`.

## Driver Classification Certification

`GET /api/v1/motive/fleet/driver-classification`

The driver-classification endpoint computes read-only counts from `provider_payload_metadata.role`. It certifies only `role == "driver"` as a Motive driver-role user. Recognized non-driver roles are `fleet_user` and `admin`; missing or undocumented roles remain unknown.

This does not certify MOR active/employed/available/working driver state, HOS readiness, dispatch status, or vehicle assignment.

See `docs/engineering/MOTIVE_DRIVER_CLASSIFICATION_CERTIFICATION.md`.

## Vehicle Utilization Schema Hardening

The vehicle-utilization schema-hardening slice prepares the existing `motive_vehicle_utilization` table for future ingestion by adding production-observed metric columns, request-window context, parser version, and an optional reference to the existing organization-owned Motive vehicle row.

This does not enable utilization ingestion, certify reporting-period semantics, advance checkpoints, create Fleet KPIs, or create Daily Brief attention.

See `docs/engineering/MOTIVE_UTILIZATION_SCHEMA_HARDENING.md`.

## Vehicle Utilization Semantics Certification

`GET /api/v1/motive/fleet/vehicle-utilization-semantics`

The vehicle-utilization semantics endpoint certifies the official Motive `GET /v1/vehicle_utilization` provider schema and metric meanings for Fleet Operations V1. The documented `vehicle_idle_rollups` response is provider-schema compatible, and the request `start_date` / `end_date` values are confirmed as the provider summary request scope.

This does not certify durable reporting-period identity, `end_date` boundary behavior, rollup cardinality, no-activity behavior, exact company rollup timezone, checkpoint advancement, or any Fleet KPI / Daily Brief attention.

See `docs/engineering/MOTIVE_UTILIZATION_SEMANTICS_CERTIFICATION.md`.

## Vehicle Utilization Bounded Evidence

`POST /api/v1/motive/verify/vehicle-utilization-evidence`

The bounded evidence endpoint is a manual, authenticated, organization-scoped, read-only probe. It selects up to three stored Motive vehicles and performs exactly three provider calls against `GET /v1/vehicle_utilization` to compare day A, day B, and the combined A-through-B window.

The endpoint returns only sanitized slot labels, counts, booleans, and evidence classifications. It does not expose provider vehicle IDs, VINs, vehicle numbers, raw payloads, headers, or metric values.

This does not enable utilization ingestion, write utilization records, certify durable period identity, advance checkpoints, create Fleet KPIs, or create Daily Brief attention.

See `docs/engineering/MOTIVE_UTILIZATION_BOUNDED_EVIDENCE.md`.

## Vehicle Utilization Writer Contract

`GET /api/v1/motive/fleet/vehicle-utilization-writer-contract`

The writer-contract endpoint is a read-only gate for future durable Motive utilization ingestion. It records the completed bounded production evidence and defines the fail-closed row policy for a future writer.

Future writes are limited to returned rollups that map to exactly one existing organization-owned Motive vehicle and pass the certified parser/envelope checks. Missing requested vehicles are classified only as `provider_rollup_absent`; Polaris must not synthesize zero utilization rows, no-activity state, or inactive vehicle state from absence alone.

The candidate writer identity is the Polaris-owned key `organization_id + motive_vehicle_id + request_window_start + request_window_end`. Request-window dates remain distinct from provider reporting-period fields, which are still deferred because Motive did not return item-level reporting-period start/end fields.

This endpoint does not call Motive, persist utilization rows, add a migration, advance checkpoints, enable scheduling, create Fleet KPIs, or create Dashboard / Daily Brief attention.

## Dashboard / Daily Brief Boundary

Healthy or normal Motive foundation state must stay quiet. Future Motive management attention should be aggregated only after the underlying provider semantics are reliable, for example:

`Fleet Operations requires attention`

not a raw list of trucks, users, trips, utilization rows, or provider payloads.
