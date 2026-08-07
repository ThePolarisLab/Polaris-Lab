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

No driver, utilization, IFTA, HOS, safety, trip, fuel, maintenance, webhook, scheduled polling, broad sync, or executive KPI ingestion is enabled.

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

## Pagination and Retry Boundary

Vehicle ingestion starts at `page_no=1` with `per_page=100`, uses `pagination.total` when returned, stops when retrieved records reach total, stops on an empty page, and enforces a maximum-page guard to prevent infinite loops.

For retryable `429`, provider `5xx`, timeout, or network failures, Polaris uses bounded retries with exponential backoff and jitter and honors `Retry-After` when present. Polaris does not retry `401` or `403` and does not invent numeric Motive quota limits or reset windows.

## Provider Contract Confirmed by Motive Support

Motive API Support case 11006147 confirmed:

- Company API Key is recommended for Mor Logistics' internal single-company server-to-server integration.
- Company API Key requests use organization-scoped access.
- Required endpoints are `GET /v1/vehicles`, `GET /v1/users`, `GET /v1/vehicle_utilization`, `GET /v1/driver_utilization`, and `GET /v1/ifta/summary`.
- User pagination uses `per_page` maximum 100, one-based `page_no`, and `pagination.total`.
- Rate-limit handling must handle `429`, honor `Retry-After` when present, use exponential backoff with jitter, avoid immediate retry loops, avoid excessive concurrency, and use pagination, caching, batching, incremental date ranges, and multi-ID requests where supported.

## Deferred Resource List

- broad resource synchronization
- recurring polling
- driver/user ingestion and driver role filtering until real provider role fields are observed or officially documented
- vehicle utilization
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

Motive webhooks are available, but no webhook routes, subscriptions, or handlers are implemented in Track 4C.2A.

Future webhooks should complement scheduled reconciliation sync, not replace it. Webhook ingestion will require signature or authentication validation, organization routing, event deduplication, replay protection, event persistence, retry handling, delivery audit trail, and dead-letter handling.
