# Motive Vehicle Contract Certification

This Fleet Operations V1 certification covers the current Polaris `GET /v1/vehicles` ingestion contract only.

It does not enable broad Motive sync, Fleet UI redesign, Fleet exception logic, vehicle utilization, driver utilization, IFTA ingestion, location polling, Dashboard attention, or Daily Brief attention.

## Source Contract

- Provider endpoint: `GET /v1/vehicles`
- Authentication: backend-only Motive Company API Key
- Polaris route for manual ingestion: `POST /api/v1/motive/sync/vehicles`
- Pagination: one-based `page_no`, `per_page=100`
- Persistence identity: `organization_id + provider_vehicle_id`
- Checkpoint rule: advance only after successful durable persistence
- Raw provider payload: not returned by API and not persisted

Official Motive documentation describes `GET /v1/vehicles` as the endpoint for listing company vehicles. It documents vehicle fields including `id`, `number`, `status`, `vin`, `make`, `model`, `year`, `license_plate_state`, related availability details, timestamps, and related current-driver metadata. Polaris certifies only the subset that is both useful for Fleet V1 and represented by the current persisted contract.

## Confirmed Fields

| Polaris field | Provider path | Persistence field | Safe for Fleet UI | Safe for Dashboard / Daily Brief | Notes |
| --- | --- | --- | --- | --- | --- |
| `provider_vehicle_id` | `vehicle.id` | `provider_vehicle_id` | No | No | Tenant-scoped identity only; do not expose provider IDs publicly. |
| `vehicle_number` | `vehicle.number` | `unit_number` | Yes | No | Fleet display identifier. |
| `vin` | `vehicle.vin` | `vin` | Yes | No | Sensitive vehicle identifier; detail/search/export contexts only. |
| `make` | `vehicle.make` | `make` | Yes | No | Vehicle spec field. |
| `model` | `vehicle.model` | `model` | Yes | No | Vehicle spec field. |
| `year` | `vehicle.year` | `year` | Yes | No | Provider documents year as string; Polaris stores a valid integer or null. |
| `license_plate` | `vehicle.license_plate_number` | `license_plate` | Yes | No | Plate number only; jurisdiction is not persisted. |
| `provider_status` | `vehicle.status` | `status` | Yes | No | Literal Motive status only. |

## Derived Fields

| Polaris field | Source | Notes |
| --- | --- | --- |
| `observed_at` | `vehicle.updated_at`, `vehicle.last_updated_at`, or `vehicle.created_at` | Sync observation timestamp for freshness/bookkeeping, not a business state. |

## Deferred Fields / Semantics

| Field or semantic | Reason |
| --- | --- |
| MOR active/inactive business state | Motive `status` is only certified as a provider literal. Do not infer active truck, available truck, dispatched truck, or moving truck. |
| Vehicle-driver association | Current-driver metadata is not certified as durable assignment semantics for Fleet V1. |
| Location/current position | Belongs to `/v1/vehicle_locations`, not this certified ingestion path. |
| Odometer | Belongs to location/telemetry contracts, not current `/v1/vehicles` persistence. |
| Engine hours | Belongs to location/telemetry contracts, not current `/v1/vehicles` persistence. |
| Fuel type | Documented by Motive but not persisted by current Polaris vehicle schema. |
| Metric units | Documented by Motive but not persisted by current Polaris vehicle schema. |
| License plate state/province | Documented by Motive but not persisted by current Polaris vehicle schema. |
| Fleet exceptions and Daily Brief attention | Deferred until operational semantics are independently certified. |

## Read API

`GET /api/v1/motive/fleet/vehicle-contract`

The endpoint returns:

- certified field definitions;
- classification as `CONFIRMED`, `DERIVED`, or `DEFERRED`;
- organization-scoped vehicle count;
- organization-scoped completeness counts and percentages for persisted fields;
- security and Dashboard/Daily Brief boundary flags.

The endpoint does not return provider vehicle IDs, VIN values, plate values, raw Motive payloads, headers, secrets, Motive API keys, or cross-tenant data.

## Completeness

Completeness is calculated from existing `motive_vehicles` rows for the authenticated organization only. A missing value remains missing. Polaris must not fabricate VINs, plate values, years, status values, driver associations, locations, or operational states.

## Dashboard / Daily Brief Boundary

Normal Motive vehicle contract health is intentionally quiet. Fleet Dashboard and Daily Brief attention remain disabled until a later PR certifies exception semantics.
