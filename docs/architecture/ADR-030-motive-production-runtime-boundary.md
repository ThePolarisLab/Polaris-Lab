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
- `POLARIS_FRONTEND_URL`

The Motive client secret, authorization codes, access tokens, refresh tokens, OAuth state values, and authorization headers must never be logged, returned, committed, or documented with real values. Access and refresh tokens are encrypted in tenant-owned credential storage.

## Production Hosts

- Frontend: `https://polaris-executive.onrender.com`
- Backend API: `https://polaris-executive-api.onrender.com`

The Motive OAuth callback must reach FastAPI on the backend API host, not the React frontend host.

## Redirect URI

`MOTIVE_REDIRECT_URI` must exactly match the Success Redirect URI configured in the Motive Developer Portal. The canonical production value is:

```text
https://polaris-executive-api.onrender.com/api/v1/motive/oauth/callback
```

The FastAPI route is:

```text
GET /api/v1/motive/oauth/callback
```

The backend stores the exact redirect URI used to issue the OAuth state and reuses that stored value during token exchange. It does not normalize trailing slashes or substitute a later environment value after state issuance.

After callback processing, the backend redirects the user to the frontend connector page with hash routing:

```text
https://polaris-executive.onrender.com/#executive/connectors?motive=<status>
```

## Verification Boundary

The only live provider operation allowed in this increment is:

```text
GET https://api.gomotive.com/v1/companies
Accept: application/json
Authorization: Bearer <access token>
```

This proves only OAuth token usability and endpoint reachability. It does not certify production data availability, completeness, rate-limit behavior, broad synchronization readiness, or KPI readiness.

## Deferred

- exact rate-limit contract
- full driver-list contract
- broad synchronization
- recurring polling
- webhooks
- HOS, safety, DVIR, fault codes, trips, maintenance, and fuel purchases
- executive KPI calculations
- frontend fleet dashboard
