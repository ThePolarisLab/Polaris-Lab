# ADR-030: Motive Production Runtime Boundary

## Status

Accepted for Track 4C.1E.

## Decision

`chief-of-staff/` is the only production runtime for Motive. The TypeScript Hermes Motive connector under `src/hermes/connectors/motive/` remains reference material only and is not integrated into production.

Track 4C.1E converts the active Motive production authentication path to the Motive Company API Key confirmed for Mor Logistics Manitoba Limited. This replaces the OAuth 2.0 production path from PRs #115-#118. OAuth remains dormant reference architecture only for a possible future multi-tenant or Motive App Marketplace integration.

The PR retains the architecture-neutral Motive foundation: tenant-owned Motive tables, sync history, checkpoints, normalized internal contracts, organization isolation, idempotency constraints, safe status concepts, frontend connector status, System Health mapping, Evidence mapping, and safe logging/redaction controls. It does not implement broad synchronization, executive KPI calculations, webhooks, or fleet dashboards.

## Authentication Boundary

The selected production authentication method is a Motive Company API Key for Mor Logistics' internal server-to-server integration.

Runtime configuration uses:

```text
MOTIVE_API_KEY
```

Credential precedence for this increment is the secure Render backend environment variable. The browser never submits, receives, or displays the key. The connector constructs the provider header only at the HTTP boundary:

```text
X-API-Key: <secret>
```

The API key, request headers containing the key, and key-like values must never be logged, returned, committed, documented with real values, or displayed. Status reads report only safe metadata such as `key_present`, `configured_by_administrator`, credential source, connection status, and last verification time.

The existing OAuth schema is not destructively dropped in this PR because OAuth migrations may already be deployed. OAuth runtime routes are disabled for production behavior and documented only as deferred future multi-tenant architecture.

## Verification Boundary

The only live provider operation allowed in this increment is a narrow read-only Company API Key verification probe:

```text
GET https://api.gomotive.com/v1/vehicles?per_page=1&page_no=1
Accept: application/json
X-API-Key: <secret>
```

This proves only API-key presence, authentication, and endpoint reachability. It does not certify production data availability, completeness, rate-limit behavior, broad synchronization readiness, or KPI readiness.

## Confirmed Provider Contract

Motive API Support case 11006147 confirmed:

- Company API Key is recommended for Mor Logistics' single-company server-to-server integration.
- OAuth 2.0 is mainly for multi-tenant or App Marketplace integrations where multiple fleets authorize an app.
- Company API Key requests use organization-scoped access.
- Required endpoints: `GET /v1/vehicles`, `GET /v1/users`, `GET /v1/vehicle_utilization`, `GET /v1/driver_utilization`, and `GET /v1/ifta/summary`.
- User pagination uses `per_page` up to 100, one-based `page_no`, and `pagination.total`.
- Rate-limit handling must handle `429`, honor `Retry-After` when present, use exponential backoff with jitter, avoid immediate retry loops, avoid excessive concurrency, and prefer pagination, caching, batching, incremental date ranges, and multi-ID requests where supported.

## Deferred

- broad synchronization and scheduled polling
- driver role filtering until real provider role fields are observed or officially documented
- webhooks
- HOS, safety, DVIR, fault codes, trips, maintenance, and fuel purchases
- executive KPI calculations
- frontend fleet dashboard
- future multi-tenant OAuth architecture
