# ADR-030: Motive Production Runtime Boundary

## Status

Accepted for Track 4C.1A.

## Decision

`chief-of-staff/` is the only production runtime for Motive. The TypeScript Hermes Motive connector under `src/hermes/connectors/motive/` remains reference material only and is not integrated into production.

Track 4C.1A implements a Python Motive API-key foundation in `chief-of-staff/backend/app/connectors/` with tenant-owned persistence and one limited read-only verification operation. It does not implement production synchronization, executive KPI calculations, webhooks, or frontend fleet dashboards.

## Authentication Boundary

The initial production authentication method is Motive API key using the `X-API-Key` header. OAuth 2.0 is recognized as supported by Motive documentation, but OAuth storage and token lifecycle are out of scope for this PR.

Credential replacement must happen through secure configuration or encrypted organization-scoped credential storage without code changes. The temporary Internal test-mode API key must never be committed, logged, pasted into PR text, or used in tests.

## Verification Boundary

The only live provider operation allowed in this increment is:

```text
GET https://api.gomotive.com/v1/vehicles?per_page=1&page_no=1
X-API-Key: <loaded from secure storage>
```

This proves only authentication and endpoint reachability. It does not certify production data availability, completeness, rate-limit behavior, or KPI readiness.

## Deferred

- production credential approval
- full driver-list contract
- exact rate-limit contract
- broad synchronization
- recurring polling
- webhooks
- HOS, safety, DVIR, fault codes, trips, maintenance, and fuel purchases
- executive KPI calculations
- frontend fleet dashboard
