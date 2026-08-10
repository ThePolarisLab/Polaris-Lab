# Polaris Track 4C: Motive Roadmap

## 4C.1E: Company API Key Production Foundation

- Keep `chief-of-staff/` as the only production runtime.
- Replace active Motive OAuth production behavior with Company API Key authentication for Mor Logistics' single-company server-to-server integration.
- Read the production key only from secure backend configuration: `MOTIVE_API_KEY`.
- Retain tenant-owned Motive foundation tables, sync history, checkpoints, normalized internal contracts, organization isolation, idempotency constraints, safe status APIs, frontend connector status, System Health mapping, Evidence mapping, and safe logging controls.
- Use limited read-only verification only: `GET /v1/vehicles?per_page=1&page_no=1`.
- Disable active OAuth connect/callback behavior while retaining deployed OAuth schema unless cleanup is separately reviewed.

## 4C.2A: Vehicle Read-Only Production Ingestion

- Adds manual vehicle-only ingestion using `POST /api/v1/motive/sync/vehicles`.
- Uses the confirmed endpoint `GET /v1/vehicles?per_page=100&page_no=N` with Company API Key authentication at the backend HTTP boundary.
- Persists only tenant-owned vehicle records in `motive_vehicles` using `(organization_id, provider_vehicle_id)` as the idempotent provider identity.
- Reuses existing `motive_sync_history` and `motive_sync_checkpoints`; checkpoints advance only after successful durable persistence.
- Exposes safe vehicle sync metadata on Motive status: last vehicle sync time/status, records stored, records read, and pages read.
- Keeps broad sync disabled and production certification false; this track certifies only vehicle endpoint connectivity, pagination, idempotent vehicle upserts, manual vehicle sync, and safe metadata.

## 4C.2B: Company User Read-Only Production Ingestion

- Adds manual company-user ingestion using `POST /api/v1/motive/sync/users`.
- Uses the confirmed endpoint `GET /v1/users?per_page=100&page_no=N` with Company API Key authentication at the backend HTTP boundary.
- Uses Motive support's confirmed pagination contract: `per_page` maximum 100, one-based `page_no`, and `pagination.total`.
- Persists tenant-owned company-user records using `(organization_id, provider_user_id)` as the provider identity. The existing storage column name remains `provider_driver_id` until a separately reviewed schema cleanup is justified.
- Does not classify every `/v1/users` row as a driver. Driver classification remains `unknown` and `driver_classification_certified=false` until Motive documents or production samples certify a role/type discriminator.
- Exposes safe user sync metadata only: last user sync time/status, records stored, records read, pages read, and driver-classification certification state.
- Keeps broad sync disabled and production certification false; this track certifies only `/v1/users` connectivity, pagination, idempotent company-user upserts, manual user sync, and safe metadata.

## 4C.2C+: Provider Contract Completion and Sync Design

Track 4C.2C0 verified the temporary `GET /v1/vehicle_utilization` provider request contract after PR #132 removed `X-Time-Zone`. The successful controlled production request used one stored provider vehicle ID, the two-completed-calendar-day window introduced by PR #131, `per_page=1`, `page_no=1`, backend-only `X-API-Key`, no `X-User-Id`, exactly one provider attempt, no retry, no persistence, and no checkpoint mutation. This verifies only that exact temporary request shape and strongly supports that `X-Time-Zone: America/Winnipeg` caused the earlier provider rejection.

Before broader sync is implemented, Polaris must complete design and verification for:

- durable vehicle-utilization persistence mapping, identity/period semantics, units, checkpoint strategy, unknown vehicle handling, KPI interpretation, and production ingestion certification
- driver filtering based on real provider role fields observed in sanitized provider data or official documentation
- durable ingestion for driver utilization and IFTA summary
- production-safe batching and incremental date ranges per resource
- webhook authentication/signature contract
- production evidence certification criteria beyond vehicle/user-only persistence

## Confirmed Provider Inputs

Motive support confirmed the production Company API Key path, required endpoints, users pagination (`per_page` maximum 100, one-based `page_no`, `pagination.total`), and rate-limit guidance: handle `429`, honor `Retry-After` when present, use exponential backoff with jitter, avoid immediate retry loops, avoid excessive concurrency, and use pagination, caching, batching, incremental ranges, and multi-ID requests where supported.

For vehicles, Track 4C.2A uses the confirmed `/v1/vehicles` endpoint with `per_page=100` and one-based `page_no`; it uses `pagination.total` when returned, stops on empty pages, and enforces a maximum-page guard.

For company users, Track 4C.2B uses the confirmed `/v1/users` endpoint with `per_page=100` and one-based `page_no`; it uses `pagination.total` when returned, stops on empty pages, and enforces a maximum-page guard. Driver role classification is not certified.

## Later Tracks

- driver classification after role filtering is verified
- vehicle utilization, driver utilization, and IFTA summary ingestion
- broad synchronization and scheduled reconciliation
- webhooks with delivery audit trail and dead-letter handling
- executive fleet KPIs
- frontend fleet dashboard
- HOS, safety, DVIR, fault codes, trips, maintenance, and fuel purchases
- future multi-tenant OAuth architecture if Polaris becomes a multi-company or App Marketplace integration
