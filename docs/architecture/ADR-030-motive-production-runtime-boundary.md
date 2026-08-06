# ADR-030: Motive Production Runtime Boundary

## Status

Accepted for Track 4C.1A.

## Decision

`chief-of-staff/` is the only production runtime for Motive. The TypeScript Hermes Motive connector under `src/hermes/connectors/motive/` remains reference material only and is not integrated into production.

Track 4C.1A implements a Python Motive OAuth 2.0 foundation in `chief-of-staff/backend/app/connectors/` with tenant-owned persistence and one limited read-only verification operation. It does not implement production synchronization, executive KPI calculations, webhooks, or frontend fleet dashboards.

## Authentication Boundary

OAuth 2.0 is the selected permanent production authentication architecture for Motive. The prior API-key design in Draft PR #115 was superseded before merge and is not represented in the final migration.

Runtime configuration uses environment variables only:

- `MOTIVE_CLIENT_ID`
- `MOTIVE_CLIENT_SECRET`
- `MOTIVE_REDIRECT_URI`

The Motive client secret, authorization codes, access tokens, refresh tokens, and authorization headers must never be logged, returned, committed, or documented with real values. Access and refresh tokens are encrypted in tenant-owned credential storage.

## Verification Boundary

The only live provider operation allowed in this increment is:

```text
GET https://api.gomotive.com/v1/companies
Accept: application/json
Authorization: Bearer <access token>
```

This proves only OAuth token usability and endpoint reachability. It does not certify production data availability, completeness, rate-limit behavior, broad synchronization readiness, or KPI readiness.

## Redirect URI

`MOTIVE_REDIRECT_URI` must exactly match the URI configured in the Motive Developer Portal. Production should use the canonical API host and callback route:

```text
https://<canonical-api-host>/api/v1/motive/callback
```

## Deferred

- exact rate-limit contract
- full driver-list contract
- broad synchronization
- recurring polling
- webhooks
- HOS, safety, DVIR, fault codes, trips, maintenance, and fuel purchases
- executive KPI calculations
- frontend fleet dashboard
