# Motive Driver / User Contract Certification

This Fleet Operations V1 certification covers the current Polaris `GET /v1/users` ingestion contract only.

It does not enable broad Motive sync, Fleet UI redesign, Fleet exception logic, driver utilization, HOS, dispatch state, vehicle assignment, Dashboard attention, or Daily Brief attention.

## Source Contract

- Provider endpoint: `GET /v1/users`
- Authentication: backend-only Motive Company API Key
- Polaris route for manual ingestion: `POST /api/v1/motive/sync/users`
- Pagination: one-based `page_no`, `per_page=100`
- Persistence identity: `organization_id + provider_driver_id`
- Current table: `motive_drivers`
- Table naming caveat: the table stores Motive company users; driver classification remains deferred.
- Checkpoint rule: advance only after successful durable persistence
- Raw provider payload: not returned by API and not persisted

Official Motive documentation describes `GET /v1/users` as returning company users whose roles may include `driver`, `fleet_user`, or `admin`. It also documents query parameters such as `role`, `status`, `duty_status`, `updated_after`, `per_page`, and `page_no`.

## Confirmed Fields

| Polaris field | Provider path | Persistence field | Safe for Fleet UI | Safe for Dashboard / Daily Brief | Notes |
| --- | --- | --- | --- | --- | --- |
| `provider_user_id` | `user.id` | `provider_driver_id` | No | No | Tenant-scoped identity only; do not expose provider IDs publicly. |
| `first_name` | `user.first_name` | none | No | No | Used only to derive `name` when needed. |
| `last_name` | `user.last_name` | none | No | No | Used only to derive `name` when needed. |
| `email` | `user.email` | `email` | Yes | No | Personal information; not returned by contract endpoint. |
| `username` | `user.username` | `provider_payload_metadata.username` | No | No | Metadata only; not a dedicated column. |
| `provider_role` | `user.role` | `provider_payload_metadata.role` | Yes | No | Literal Motive role, such as `driver`, `fleet_user`, or `admin`. |
| `provider_status` | `user.status` | `status` | Yes | No | Literal Motive user status only. |

## Derived Fields

| Polaris field | Source | Notes |
| --- | --- | --- |
| `full_name` | `user.name` or `user.first_name + user.last_name` | Personal information; suitable only for future Fleet contexts that intentionally show user records. |
| `observed_at` | `user.updated_at`, `user.last_updated_at`, or `user.created_at` | Sync observation timestamp for freshness/bookkeeping, not employment or availability state. |

## Deferred Fields / Semantics

| Field or semantic | Reason |
| --- | --- |
| Driver classification | `/v1/users` returns all company users. Provider role can identify rows whose literal role is `driver`, but Polaris does not certify every stored row as a MOR driver. |
| MOR active/inactive driver state | Motive `status` is certified only as a provider literal. Do not infer employed, active, available, dispatched, HOS-ready, or currently working. |
| Vehicle-driver association | Current `/v1/users` ingestion does not persist vehicle assignment or certify durable association semantics. |
| Phone | Documented by Motive, but Polaris does not persist phone numbers in the current user contract. |
| Duty status | Documented by Motive as a filter/driver field, but not persisted by current Polaris user ingestion. |
| Driver license | Sensitive and not persisted by current Polaris user ingestion. |
| Fleet exceptions and Daily Brief attention | Deferred until operational semantics are independently certified. |

## Driver vs Company User Boundary

Motive documentation supports a literal provider role field with values including `driver`, `fleet_user`, and `admin`. That is enough to certify `provider_role` as a provider literal.

It is not enough to treat every row in `motive_drivers` as a MOR driver because the current endpoint returns all company users and the table name is historical. Future Fleet work may use `provider_role == "driver"` as one input to a driver-filtering design, but that must be implemented in a separate PR with explicit tests and UI copy.

## Read API

`GET /api/v1/motive/fleet/driver-contract`

The endpoint returns:

- certified field definitions;
- classification as `CONFIRMED`, `DERIVED`, or `DEFERRED`;
- organization-scoped company-user count;
- organization-scoped completeness counts and percentages for persisted fields and selected metadata keys;
- driver/user boundary flags;
- security and Dashboard/Daily Brief boundary flags.

The endpoint does not return provider user IDs, email values, phone values, raw Motive payloads, headers, secrets, Motive API keys, or cross-tenant data.

## Completeness

Completeness is calculated from existing `/v1/users` rows for the authenticated organization only. A missing value remains missing. Polaris must not fabricate names, email addresses, roles, status values, driver classifications, vehicle assignments, duty status, HOS state, or availability state.

## Dashboard / Daily Brief Boundary

Normal Motive driver/user contract health is intentionally quiet. Fleet Dashboard and Daily Brief attention remain disabled until a later PR certifies exception semantics.
