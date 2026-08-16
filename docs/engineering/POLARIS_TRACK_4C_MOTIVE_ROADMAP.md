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

The subsequent zero-item controlled schema capture returned `top_level_type=object`, `top_level_keys=["pagination","vehicle_idle_rollups"]`, `item_container_key=vehicle_idle_rollups`, `item_count_observed=0`, and `pagination_keys=["page_no","per_page","total"]`. PR #135 then bounded the temporary verifier to up to three existing organization-owned stored vehicle IDs in one provider request. The post-PR #135 controlled production request returned HTTP 200 with `provider_vehicle_selected_count=3`, `item_container_key=vehicle_idle_rollups`, `item_wrapper_key=vehicle_idle_rollup`, and `item_count_observed=1`.

The non-empty item schema observed keys `driving_fuel`, `driving_time`, `idle_fuel`, `idle_time`, `utilization`, and `vehicle`; nested vehicle schema keys `id`, `make`, `metric_units`, `model`, `number`, `vin`, and `year`; vehicle identity path `vehicle.id`; pagination keys `page_no`, `per_page`, and `total`; unit metadata path `vehicle_idle_rollups[].vehicle_idle_rollup.vehicle.metric_units`; and no provider utilization record ID path. This disproves relying on the old `vehicle_utilization` fixture key as production-certified for success responses. It also shows the production item does not expose true reporting-period start/end fields; the earlier generic period detector incorrectly treated `driving_time` and `idle_time` metric fields as provider period fields. Request-window period identity still requires design review, and broad utilization ingestion remains HOLD/uncertified.

The next non-persistent implementation layer parses the production-observed `vehicle_idle_rollups` envelope into an internal contract and performs read-only association from `vehicle.id` to an existing organization-owned Motive vehicle. It does not write utilization rows, create vehicles, mutate checkpoints, add a sync route, or treat request dates as authoritative reporting periods while Motive Support clarification remains pending.

The first persistence-readiness slice hardens the existing `motive_vehicle_utilization` table additively for the production-observed metrics, optional internal vehicle FK, parser version, and request-window context. It still does not ingest utilization, populate reporting periods, advance checkpoints, enable scheduling, or certify unresolved provider semantics.

The semantics-certification gate uses current official Motive documentation to classify the documented `vehicle_idle_rollups` rollup summary schema as provider-contract compatible. It certifies metric meanings (`utilization` as percent; `idle_time` and `driving_time` as seconds; fuel metrics in the provider-selected unit system) and confirms `start_date` / `end_date` as the request-window summary scope. Durable ingestion remains blocked because `end_date` boundary behavior, row cardinality/no-activity behavior, exact company rollup timezone, durable idempotency, and checkpoint advancement are still unresolved.

The bounded evidence gate adds a separate manual read-only probe for `GET /v1/vehicle_utilization`. It selects up to three stored organization-owned vehicles and makes exactly three provider calls for day A, day B, and the combined A-through-B window. It returns only sanitized cardinality, no-activity-shape, pagination, and additive metric-composition classifications. It does not persist utilization rows, advance checkpoints, request page 2, enable scheduling, or create Dashboard / Daily Brief attention.

The completed bounded production evidence selected three vehicles and observed one returned selected-vehicle rollup in each of the day A (`2026-08-12`), day B (`2026-08-13`), and combined (`2026-08-12` through `2026-08-13`) windows. No duplicate or unexpected vehicles were observed, `pagination.total` matched the one returned item, and the returned vehicle's additive metrics matched exactly across the two single days and combined window. Two requested vehicles were absent in all windows; absence remains `provider_rollup_absent` only and must not be treated as zero activity, inactive state, or a durable row.

The writer-contract gate defines a read-only fail-closed durable-writer contract at `GET /api/v1/motive/fleet/vehicle-utilization-writer-contract`. A future writer may persist only returned, validated rollups mapped to exactly one organization-owned Motive vehicle. The preferred Polaris-owned idempotency boundary is `organization_id + motive_vehicle_id + request_window_start + request_window_end`; it is now certified as a future replay identity under Polaris's fixed canonical metric policy. Durable writes must request `X-Metric-Units: true`, require returned `vehicle.metric_units == true`, and never create parallel imperial rows or silently convert units. This policy is separate from bounded production observations, which confirmed consistent unit context but intentionally did not expose the Boolean value. Request-window dates remain separate from provider reporting-period fields. Scheduled daily ingestion remains blocked until the exact company-configured Motive rollup timezone is known. The vehicle-utilization pagination contract for `GET /v1/vehicle_utilization` is now certified against official Motive documentation, and a reusable read-only paginator exists for future writer use (see `MOTIVE_UTILIZATION_PAGINATION_CONTRACT.md`); broad write ingestion remains blocked pending the durable writer transaction, database uniqueness enforcement, and checkpoint advancement implementation.

The database identity gate adds Alembic migration `202608150001`, which creates the `uq_motive_vehicle_util_org_vehicle_request_window` unique constraint on `motive_vehicle_utilization` for `organization_id + motive_vehicle_id + request_window_start + request_window_end`, enforcing at the database level the replay identity the writer-contract gate certified. The four identity columns remain nullable for backward compatibility with historical/pre-contract rows; the migration's duplicate preflight fails closed (raising a sanitized error with only a duplicate-group count) if any fully-populated group already violates the identity, and it performs no backfill, no deduplication, and no row deletion. The legacy `uq_motive_vehicle_util_org_period` reporting-period constraint is retained unchanged and is not certified as a future writer identity. This is enforcement only: `writer_enabled`, `persistence_enabled`, `checkpoint_advancement_enabled`, `scheduled_ingestion_enabled`, and `broad_sync_enabled` all remain `false`. See `MOTIVE_UTILIZATION_DATABASE_IDENTITY.md` for full detail.

The writer-transaction gate adds the internal, all-or-nothing database writer transaction primitive `app.motive.vehicle_utilization_writer.write_vehicle_utilization_transaction`. It makes zero Motive HTTP calls, receives already-parsed/validated rollups, re-validates every writer precondition (organization/request context, per-rollup organization and request-window match, no duplicate or unexpected returned vehicle, canonical `metric_units == true` unit policy, certified `motive_vehicle_idle_rollup_v1` parser/`/v1/vehicle_utilization` source provenance), resolves tenant-owned `MotiveVehicleRecord` associations without ever auto-creating a vehicle, and validates the whole batch before staging any row. It owns exactly one commit and rolls back the entire transaction on any failure, including on the database uniqueness constraint firing as a final concurrency guard. Identical replays are a no-op; conflicting replays and updates to an existing row both fail closed (`records_updated` stays `0` in this gate). It never mutates `MotiveSyncCheckpoint` or `MotiveSyncHistory`, and there is still no `POST /api/v1/motive/sync/vehicle-utilization` route or any other way to reach it publicly. See `MOTIVE_UTILIZATION_WRITER_TRANSACTION.md` for the full contract and test matrix.

The controlled-write-validation gate adds the first caller of that writer transaction: the feature-flagged `POST /api/v1/motive/verify/vehicle-utilization-write` route (`Permission.CONNECTOR_WRITE`), disabled by default via `MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED` and requiring an explicit `{"confirm": true}` request body. It connects the certified pagination reader to the certified writer transaction for exactly one fixed, previously-observed historical day (`2026-08-13`), across up to three deterministic stored organization vehicles (the existing `_vehicles_for_utilization_contract` selection), making at most one Motive provider request (`per_page=100`, `page_no=1`, `X-Metric-Units: true`) and never fetching a second page even on malformed pagination metadata. It persists only provider-returned rollups via the unmodified writer transaction, never writes `MotiveSyncCheckpoint` or `MotiveSyncHistory`, and returns a sanitized result/error shape only. This is still not the normal production sync route: there is no `/sync/vehicle-utilization` route, no scheduler, and no automatic date progression. Production validation execution itself (`production_validation_executed`) is explicitly deferred to a separate step after this gate merges. See `MOTIVE_UTILIZATION_CONTROLLED_WRITE_VALIDATION.md` for the full contract and test matrix.

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
