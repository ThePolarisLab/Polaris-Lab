# Motive Production Rollout Plan

## Track 4C.1A: OAuth Foundation

Implemented scope:

- Python Motive connector shell in `chief-of-staff/`
- OAuth 2.0 authorization URL and callback foundation
- encrypted organization-scoped access and refresh token storage
- tenant-owned Motive persistence tables
- normalized internal contracts
- limited read-only verification using `GET /v1/companies`
- safe status and diagnostics

No broad Motive synchronization is enabled.

## Render Environment Configuration

Production hosts:

- Frontend: `https://polaris-executive.onrender.com`
- Backend API: `https://polaris-executive-api.onrender.com`

Configure these backend environment variables in Render:

```text
MOTIVE_CLIENT_ID=<Motive OAuth client id>
MOTIVE_CLIENT_SECRET=<Motive OAuth client secret>
MOTIVE_REDIRECT_URI=https://polaris-executive-api.onrender.com/api/v1/motive/oauth/callback
POLARIS_FRONTEND_URL=https://polaris-executive.onrender.com
```

Do not place real client IDs or client secrets in source, docs, tests, PR text, logs, or GitHub Actions.

## Motive Developer Portal

The Success Redirect URI must exactly match the backend callback route:

```text
https://polaris-executive-api.onrender.com/api/v1/motive/oauth/callback
```

Do not use `https://polaris-executive.onrender.com` for the OAuth callback. The frontend host is only the post-callback user destination, using hash routing:

```text
https://polaris-executive.onrender.com/#executive/connectors
```

## Callback Diagnostic Verification

After deploying the Motive OAuth logging visibility fix, run one new Motive authorization attempt and capture only sanitized Motive diagnostic lines from Render logs.

Search for these exact phrases:

```text
MOTIVE OAUTH CALLBACK
step=CALLBACK_START
step=TOKEN_RECEIVED
step=EXCEPTION
failing_step=
step=DB_COMMIT_SUCCESS
```

The Uvicorn access log for `GET /api/v1/motive/oauth/callback` must not show raw OAuth query values. The callback request target should either omit the query string or show sensitive values redacted, for example:

```text
/api/v1/motive/oauth/callback?code=[REDACTED]&state=[REDACTED]
```

Never paste authorization codes, OAuth state values, access tokens, refresh tokens, client secrets, or authorization headers into tickets, PR comments, docs, or chat.

## Track 4C.1B Prerequisites

Before live sync is implemented, Polaris needs Motive support or documentation confirmation for:

- exact rate-limit behavior, including headers and retry guidance
- complete driver-list endpoint contract
- expected pagination behavior for each enabled resource
- production-safe handling for `429` without documented retry windows
- token revocation endpoint availability, if remote revocation is required

## Deferred Resource List

- driver list synchronization
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

## Webhook Design Note

Motive webhooks are available, but no webhook routes, subscriptions, or handlers are implemented in Track 4C.1A.

Future webhooks should complement scheduled reconciliation sync, not replace it. Webhook ingestion will require signature or authentication validation, organization routing, event deduplication, replay protection, event persistence, retry handling, delivery audit trail, and dead-letter handling.
