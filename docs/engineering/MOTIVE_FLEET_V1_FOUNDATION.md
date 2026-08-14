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

## Dashboard / Daily Brief Boundary

Healthy or normal Motive foundation state must stay quiet. Future Motive management attention should be aggregated only after the underlying provider semantics are reliable, for example:

`Fleet Operations requires attention`

not a raw list of trucks, users, trips, utilization rows, or provider payloads.
