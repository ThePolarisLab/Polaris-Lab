# Motive Production Rollout Plan

## Track 4C.1E: Company API Key Production Foundation

Implemented scope:

- Python Motive connector shell in `chief-of-staff/`
- active Company API Key authentication using secure backend configuration
- tenant-owned Motive persistence tables retained from the foundation work
- sync history and checkpoint contracts retained
- normalized internal contracts retained
- limited read-only verification using `GET /v1/vehicles?per_page=1&page_no=1`
- frontend connector card/status activation for API-key verification only
- System Health and Evidence mappings that require successful verification before reporting availability
- safe Motive logging and query redaction controls retained

## Track 4C.2A: Vehicle-Only Manual Ingestion

Implemented scope:

- read-only vehicle listing using `GET /v1/vehicles?per_page=100&page_no=N`
- manual backend route `POST /api/v1/motive/sync/vehicles`
- tenant-owned upserts into `motive_vehicles`
- idempotency through `(organization_id, provider_vehicle_id)`
- sync history for resource `vehicles`
- checkpoint advancement only after successful vehicle persistence
- safe Motive status metadata for last vehicle sync, pages read, records read, and records stored
- minimal frontend `Sync Vehicles` action on the existing connector card

## Track 4C.2B: Company-User Manual Ingestion

Implemented scope:

- read-only company-user listing using `GET /v1/users?per_page=100&page_no=N`
- manual backend route `POST /api/v1/motive/sync/users`
- tenant-owned upserts for company users in the existing Motive identity persistence table
- idempotency through organization-owned provider user identity
- sync history for resource `users`
- checkpoint advancement only after successful user persistence
- safe Motive status metadata for last user sync, pages read, records read, records stored, and driver classification certification
- minimal frontend `Sync Users` action on the existing connector card

Driver classification is not certified in Track 4C.2B. The `/v1/users` endpoint returns company users, and Polaris must not treat every row as a driver until Motive documents or production samples certify the role/type discriminator.

No utilization, IFTA, HOS, safety, trip, fuel, maintenance, webhook, scheduled polling, broad sync, executive KPI ingestion, or driver KPI exposure is enabled.

## Track 4C.2C0: Vehicle Utilization Contract Verification

Implemented scope:

- temporary engineering-only backend route `POST /api/v1/motive/verify/vehicle-utilization-contract`
- selects exactly one existing organization-owned stored Motive vehicle inside deployed Polaris
- performs exactly one read-only provider request to `GET /v1/vehicle_utilization`
- uses `vehicle_ids[]`, `start_date`, `end_date`, `per_page=1`, and `page_no=1`
- uses a two-completed-calendar-day window in `America/Winnipeg`
- returns only sanitized schema metadata: envelope keys, item keys, identity paths, period fields, pagination keys, metric presence/types/nullability, unit field names, and schema compatibility
- redacts the provider vehicle ID and never returns metric values, VIN, plate, request headers, API key, or raw provider payload
- performs no utilization persistence, checkpoint mutation, frontend activation, polling, broad sync, KPI calculation, or schema migration

Live production verification evidence:

- the Polaris endpoint executed and reached Motive successfully
- Motive returned HTTP 400
- the latest sanitized response showed provider JSON key `error_message`
- raw provider error text remains intentionally suppressed from API responses and logs
- PR #127 confirmed no obvious code-path bug for a top-level string `error_message`; the remaining unknown category is most likely unmatched provider wording or an alternate safe shape such as string-array content
- PR #129 adds semantic-only HTTP 400 diagnostics using fixed Polaris-owned booleans; it does not expose provider text, hashes, message length, IDs, headers, query values, or payloads
- Post-PR #129 production evidence still returned Motive HTTP 400 with semantic flags `mentions_date_context=true` and `mentions_invalid_or_rejected=true`, while header, user, vehicle, permission, required/missing, and parameter flags remained false
- The follow-up date-window verification experiment changes only the temporary verifier date window from a same-day completed-date probe to `start_date` one completed calendar day before `end_date`, where `end_date` is the previous completed calendar day in `America/Winnipeg`
- semantic classification and semantic flags are used only to identify the missing provider-contract requirement before a future controlled verification call
- `X-User-Id` is documented by Motive as a possible Fleet Admin/Fleet Manager context header, but Polaris does not yet have an authoritative organization-safe provider user candidate
- do not claim `X-User-Id` is required for Mor Logistics until a later controlled production verification proves that category

Track 4C.2C vehicle-utilization ingestion remains on HOLD and uncertified until the sanitized live contract result is reviewed and the existing `motive_vehicle_utilization` identity/period mapping is certified.

## Render Environment Configuration

Configure this backend environment variable in Render:

```text
MOTIVE_API_KEY=<Motive Company API Key from secure Motive/Render configuration>
```

Do not place the real API key in source, docs, tests, fixtures, PR text, comments, logs, screenshots, or GitHub Actions. The frontend must never accept or display the API key.

The OAuth environment variables from PRs #115-#118 are no longer required for active Motive production behavior:

- `MOTIVE_CLIENT_ID`
- `MOTIVE_CLIENT_SECRET`
- `MOTIVE_REDIRECT_URI`

Leave deployed OAuth database schema in place unless a separate migration safety review approves cleanup.

## Vehicle Sync Runbook

After deployment:

1. Confirm `MOTIVE_API_KEY` is configured in the backend Render service.
2. Confirm Motive verification has succeeded.
3. Open the executive connectors page.
4. Click `Sync Vehicles`.
5. Confirm the backend performs paginated read-only requests only:

```text
GET https://api.gomotive.com/v1/vehicles?per_page=100&page_no=1
Accept: application/json
X-API-Key: <secret>
```

6. Confirm status metadata updates with last vehicle sync time/status, pages read, records read, and vehicle records stored.
7. Confirm Render logs do not contain the API key, `X-API-Key` value, raw request headers, authorization headers, or raw provider payloads.

## User Sync Runbook

After deployment:

1. Confirm `MOTIVE_API_KEY` is configured and Motive verification has succeeded.
2. Open the executive connectors page.
3. Click `Sync Users`.
4. Confirm the backend performs paginated read-only requests only:

```text
GET https://api.gomotive.com/v1/users?per_page=100&page_no=1
Accept: application/json
X-API-Key: <secret>
```

5. Confirm status metadata updates with last user sync time/status, pages read, records read, user records stored, and `driver_classification_certified=false`.
6. Confirm no driver count, driver KPI, HOS, safety, utilization, or broad-ingestion claim is exposed.
7. Confirm Render logs do not contain the API key, `X-API-Key` value, raw request headers, authorization headers, or raw provider payloads.

## Vehicle Utilization Contract Verification Runbook

After deployment:

1. Confirm at least one Motive vehicle has already been stored for the active organization.
2. Invoke `POST /api/v1/motive/verify/vehicle-utilization-contract` from an authenticated engineering context with connector-write permission.
3. Confirm the backend performs only this provider request shape:

```text
GET https://api.gomotive.com/v1/vehicle_utilization?vehicle_ids[]=<redacted stored vehicle id>&start_date=<one completed calendar day before end_date>&end_date=<previous completed date>&per_page=1&page_no=1
Accept: application/json
X-Time-Zone: America/Winnipeg
X-API-Key: <secret>
```

4. Confirm the response contains only sanitized field/type/schema metadata on success.
5. If Motive returns HTTP 400, confirm the response contains only sanitized diagnostic fields: `provider_error_keys`, `provider_error_code` when safe, `provider_error_message_category`, fixed Polaris-owned `provider_error_message`, and `provider_error_semantics` booleans.
6. Confirm raw provider error text, provider IDs, VINs, plates, emails, query values, headers, and secrets are not returned.
7. Confirm no row is written to `motive_vehicle_utilization` and no sync checkpoint changes.
8. Confirm Render logs contain only `MOTIVE VEHICLE UTILIZATION CONTRACT VERIFY` with organization ID, HTTP status, response type, item count, and schema compatibility.
9. Do not treat this endpoint as production ingestion or KPI certification.

## Pagination and Retry Boundary

Vehicle and user ingestion start at `page_no=1` with `per_page=100`, use `pagination.total` when returned, stop when retrieved records reach total, stop on an empty page, and enforce a maximum-page guard to prevent infinite loops.

For retryable `429`, provider `5xx`, timeout, or network failures, Polaris uses bounded retries with exponential backoff and jitter and honors `Retry-After` when present. Polaris does not retry `401` or `403` and does not invent numeric Motive quota limits or reset windows.

The vehicle-utilization contract verification route is stricter than ingestion: it makes one provider request per invocation and does not retry. It returns sanitized errors for `400`, `401`, `403`, `429`, provider `5xx`, timeout/network failure, or malformed responses.

## Provider Contract Confirmed by Motive Support

Motive API Support case 11006147 confirmed:

- Company API Key is recommended for Mor Logistics' internal single-company server-to-server integration.
- Company API Key requests use organization-scoped access.
- Required endpoints are `GET /v1/vehicles`, `GET /v1/users`, `GET /v1/vehicle_utilization`, `GET /v1/driver_utilization`, and `GET /v1/ifta/summary`.
- User pagination uses `per_page` maximum 100, one-based `page_no`, and `pagination.total`.
- Vehicle utilization query parameters are `vehicle_ids[]`, `start_date`, `end_date`, `per_page`, and `page_no`.
- Vehicle utilization documented headers include `X-Time-Zone`, `X-Metric-Units`, and `X-User-Id`; Polaris sends `X-Time-Zone: America/Winnipeg` for the contract verification probe, sends `X-Metric-Units` only if explicitly configured, and does not send `X-User-Id` until an authoritative Fleet Admin/Fleet Manager provider user identity is verified.
- Vehicle utilization documented metrics include `utilization`, `idle_time`, `idle_fuel`, `driving_time`, and `driving_fuel`.
- Rate-limit handling must handle `429`, honor `Retry-After` when present, use exponential backoff with jitter, avoid immediate retry loops, avoid excessive concurrency, and use pagination, caching, batching, incremental date ranges, and multi-ID requests where supported.

## Deferred Resource List

- broad resource synchronization
- recurring polling
- driver role filtering until real provider role fields are observed or officially documented
- authoritative `X-User-Id` Fleet Admin/Fleet Manager candidate selection for vehicle utilization
- vehicle utilization ingestion pending 4C.2C0 live contract review
- driver utilization
- IFTA summary
- HOS
- safety events
- DVIR
- fault codes
- trips
- maintenance
- fuel purchases
- webhooks
- executive KPI calculations
- frontend fleet dashboard
- future multi-tenant OAuth architecture

## Webhook Design Note

Motive webhooks are available, but no webhook routes, subscriptions, or handlers are implemented in Track 4C.2C0.

Future webhooks should complement scheduled reconciliation sync, not replace it. Webhook ingestion will require signature or authentication validation, organization routing, event deduplication, replay protection, event persistence, retry handling, delivery audit trail, and dead-letter handling.
