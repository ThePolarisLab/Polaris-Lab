# Motive Authentication and Permissions

## Confirmed Production Decision

Motive API Support case 11006147 confirmed that Mor Logistics Manitoba Limited has a production Company API Key under the label `Internal OS` and that Company API Key authentication is recommended for this single-company server-to-server integration.

OAuth 2.0 is no longer the active Polaris production authentication path for Motive. OAuth remains deferred reference architecture only for a possible future multi-tenant or Motive App Marketplace integration where multiple fleets authorize an application.

## Runtime Configuration

Use the secure backend environment variable:

```text
MOTIVE_API_KEY
```

Do not place the real key value in source, tests, fixtures, docs, GitHub Actions, PR text, comments, logs, screenshots, or examples. Do not ask for the key in chat or PR comments.

For Track 4C.1E, credential precedence is:

1. Secure Render backend environment variable `MOTIVE_API_KEY`.
2. No database API-key fallback.

Tenant-owned encrypted credential tables may be used in a future multi-company product migration, but this PR does not implement parallel credential sources.

## Request Authentication

Motive Company API Key requests use:

```text
X-API-Key: <secret>
```

The connector constructs this header only at the HTTP boundary. Status APIs, frontend metadata, logs, exceptions, and sync history must never include the key or a full request-header dictionary containing the key.

## Safe Status Metadata

Safe metadata may include:

- `authentication_method=company_api_key`
- `credential_source=render_environment`
- `configured_by_administrator`
- `key_present`
- `connection_status`
- `last_verified_at`
- `authorization_required`
- `records_read`
- `production_sync_enabled=false`
- `production_certified=false`

## Confirmed Endpoint Surface

| Resource | Endpoint | Track 4C.1E Status |
| --- | --- | --- |
| Vehicles | `GET /v1/vehicles` | Used for narrow verification with `per_page=1&page_no=1` |
| Users | `GET /v1/users` | Contract confirmed; broad sync deferred |
| Vehicle utilization | `GET /v1/vehicle_utilization` | Contract confirmed; broad sync deferred |
| Driver utilization | `GET /v1/driver_utilization` | Contract confirmed; broad sync deferred |
| IFTA summary | `GET /v1/ifta/summary` | Contract confirmed; broad sync deferred |

## Confirmed User Pagination

Motive support confirmed:

```text
GET /v1/users?per_page=100&page_no=1
```

- `per_page` maximum is 100.
- `page_no` is one-based.
- `pagination.total` reports total available records.
- Pagination should continue until the retrieved count reaches `pagination.total` or an empty page is returned.

The endpoint returns all company users, not only drivers. Polaris must define driver filtering only from real provider role fields observed in sanitized production data or official documentation. Do not invent role names.

## Verification Request

```text
GET https://api.gomotive.com/v1/vehicles?per_page=1&page_no=1
Accept: application/json
X-API-Key: <secret>
```

The verification request reads at most one vehicle, does not paginate, does not persist broad vehicle data, and records only safe status/history metadata.

## Error and Rate-Limit Handling

- `200`: `connected`
- `401`: `authorization_required`
- `403`: `authorization_required` or `permission_denied`
- `429`: `rate_limited`
- timeout: `provider_timeout`
- provider `5xx`: `provider_unavailable`
- malformed response: `provider_contract_error`

Rate-limit guidance from Motive support: handle `429`, honor `Retry-After` when present, use bounded exponential backoff with jitter, avoid immediate retry loops, avoid excessive concurrency, and prefer pagination, caching, batching, incremental date ranges, and multi-ID requests where supported. Polaris does not invent Motive numeric quotas or reset windows.

## Deferred

- broad production synchronization
- recurring polling
- webhooks
- OAuth multi-tenant architecture
- HOS, safety, DVIR, fault codes, trips, maintenance, and fuel purchases
- executive KPI calculations
- frontend fleet dashboard
