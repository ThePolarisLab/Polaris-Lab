# Motive v1 / v1.1 Punch List

## v1 Foundation

- Company API Key is the selected Motive production authentication architecture for Mor Logistics' internal server-to-server integration.
- Backend configuration uses secure Render environment variable `MOTIVE_API_KEY`.
- The Motive request header is `X-API-Key: <secret>` and is constructed only at the HTTP boundary.
- Motive status APIs return metadata only and never expose the key, request headers, tokens, client secrets, OAuth state, or authorization headers.
- Frontend connector card shows administrator-managed configuration and never accepts or displays the key.
- Limited verification uses `GET /v1/vehicles?per_page=1&page_no=1` with at most one record read.
- Manual vehicle-only ingestion uses `POST /api/v1/motive/sync/vehicles` and `GET /v1/vehicles?per_page=100&page_no=N`.
- Vehicle upserts are tenant-owned and idempotent through `(organization_id, provider_vehicle_id)`.
- Vehicle checkpoints advance only after successful durable persistence.
- Manual company-user ingestion uses `POST /api/v1/motive/sync/users` and `GET /v1/users?per_page=100&page_no=N`.
- User upserts are tenant-owned and idempotent through organization-owned provider user identity.
- User checkpoints advance only after successful durable persistence.
- Driver classification is not certified; Polaris does not expose a driver count or driver KPI from `/v1/users` records.
- Temporary vehicle-utilization contract verification reached Motive and initially received HTTP 400 with provider JSON key `error_message`; PR #127 confirmed no obvious code-path bug for top-level string `error_message`, PR #129 added semantic-only fixed boolean diagnostics without raw provider text exposure, post-PR #129 production evidence pointed only to a date/range invalid-or-rejected concept, and PR #131 confirmed the two-completed-calendar-day date window did not change that semantic evidence.
- PR #132 removed `X-Time-Zone` only from the temporary vehicle-utilization verifier while preserving provider vehicle selection, the two-completed-calendar-day window, query parameter names, `per_page=1`, `page_no=1`, backend-only `X-API-Key`, no `X-User-Id`, max provider attempts = 1, no retry, no persistence, and no checkpoint mutation; the post-PR #132 controlled production request returned HTTP 200 with sanitized `status=success`, `endpoint=/v1/vehicle_utilization`, `provider_vehicle_selected=true`, and `vehicle_id_redacted=true`.
- System Health is Healthy only after successful API-key verification.
- Evidence is Available only after successful verification and does not claim broad ingestion.
- Existing OAuth runtime routes are disabled for active production behavior.
- OAuth schema is retained unless cleanup receives a separate migration safety review.
- No utilization ingestion, IFTA, HOS, safety, trips, fuel, maintenance, broad sync, KPIs, webhooks, or complete production certification claims.

## v1.1 Candidate Work

- Keep vehicle-utilization ingestion on HOLD and uncertified even though the exact temporary request shape is now verified. Complete broad sync design for vehicle utilization, driver utilization, and IFTA summary only after durable persistence mapping, identity/period semantics, units, checkpoint strategy, unknown vehicle handling, KPI interpretation, and production ingestion certification are designed and verified.
- Resolve vehicle-utilization `X-User-Id` requirements only after an authoritative Fleet Admin/Fleet Manager provider user identity contract is verified.
- Define driver filtering only from real provider role fields observed in sanitized production responses or official documentation.
- Implement durable resource sync with checkpoint advancement only after successful persistence.
- Add scheduled reconciliation with bounded retry, `Retry-After`, exponential backoff with jitter, low concurrency, batching, caching, and incremental date ranges.
- Add webhook ingestion only after signature/authentication requirements are verified.
- Add production evidence certification criteria beyond vehicle/user-only ingestion.

## Deferred

Driver classification, authoritative `X-User-Id` Fleet Admin/Fleet Manager candidate selection, vehicle utilization ingestion beyond the verified temporary request contract, driver utilization, IFTA summary, HOS, safety, DVIR, fault codes, trips, maintenance, fuel purchases, webhooks, executive fleet KPIs, frontend fleet dashboard, scheduled polling, broad synchronization, and future multi-tenant OAuth architecture remain out of scope for Track 4C.2C0.
