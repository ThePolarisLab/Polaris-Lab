# QuickBooks Online Production Adapter

Phase 3A implements a tenant-bound, read-only QuickBooks Online adapter for the live Mor Logistics company: `MOR LOGISTICS MANITOBA LIMITED`.

## Runtime Ownership

Python FastAPI is the authoritative production runtime for QuickBooks. See `docs/architecture/ADR-026-quickbooks-runtime-ownership.md`.

Python owns OAuth, token encryption, refresh-token rotation, credential persistence, live Intuit HTTPS calls, synchronization orchestration, production verification, financial cache writes, and API exposure. Hermes owns connector/evidence/checkpoint contracts and mocked/sandbox tests, but it does not own production refresh tokens or realm IDs in this phase.

## Deployment Prerequisite

Production QuickBooks verification requires the Phase 2.1 persistent deployment baseline:

- `DATABASE_URL` must point to persistent Render PostgreSQL, not temporary SQLite.
- Alembic migrations must run before application startup.
- `/` and `/health` must remain generic public status endpoints.
- Detailed system and connector health must remain authenticated and tenant-bound.

Do not authorize QuickBooks or run live sync while using `sqlite:////tmp/polaris.db`.

## Security Boundary

No Intuit client secret, access token, refresh token, authorization code, raw OAuth state, encryption key, or realm/company ID may be committed to source control, written to logs, included in Hermes evidence, or returned by an API response.

QuickBooks credentials are stored encrypted at rest in `quickbooks_oauth_credentials` and keyed by `organization_id`. Every protected QuickBooks route derives organization context from `AuthenticatedPrincipal.organization_id`.

## Required Deployment Configuration

Set these values in Render or the deployment secret manager:

- `DATABASE_URL=<Render PostgreSQL Internal Database URL>`
- `POLARIS_QBO_ENVIRONMENT=production`
- `POLARIS_QBO_CLIENT_ID`
- `POLARIS_QBO_CLIENT_SECRET`
- `POLARIS_QBO_REDIRECT_URI`
- `POLARIS_QBO_OAUTH_STATE_SECRET`
- `POLARIS_QBO_TOKEN_ENCRYPTION_KEY`
- `POLARIS_QBO_EXPECTED_COMPANY_NAME=MOR LOGISTICS MANITOBA LIMITED`
- `POLARIS_FRONTEND_URL`

Optional transport settings:

- `POLARIS_QBO_MINOR_VERSION`, default `75`
- `POLARIS_QBO_REQUEST_TIMEOUT_SECONDS`, default `20`
- `POLARIS_QBO_MAX_ATTEMPTS`, default `3`
- `POLARIS_QBO_RETRY_BASE_SECONDS`, default `0.25`

Do not configure production refresh tokens or realm IDs manually in GitHub. Polaris obtains them through OAuth and stores them encrypted in the production database.

## OAuth Flow

1. A user with `connector.write` calls `/api/v1/connectors/quickbooks/oauth/authorize-url` through the authenticated frontend.
2. Polaris creates a signed, persisted, expiring, single-use OAuth state bound to the active organization and identity.
3. The frontend navigates to the returned Intuit authorization URL.
4. Intuit redirects to `/api/v1/connectors/quickbooks/oauth/callback`.
5. The callback validates state, exchanges the authorization code, stores the encrypted refresh token by organization, fetches CompanyInfo, and accepts the credential only if the company matches `MOR LOGISTICS MANITOBA LIMITED` after harmless case/whitespace normalization.

## Supported Read-Only Resources

- CompanyInfo
- Customers
- Vendors
- Accounts
- Invoices
- Payments
- Bills
- Purchases
- Journal Entries

Entity reads use QuickBooks query pagination with `STARTPOSITION` and `MAXRESULTS`. Incremental reads use `MetaData.LastUpdatedTime` where QuickBooks supports it. Resources without reliable incremental semantics use safe bounded refresh behavior documented in sync history.

## Supported Reports

- Profit and Loss
- Balance Sheet
- Cash Flow
- Aged Receivables
- Aged Payables

Reports preserve provider metadata and row hierarchy in tenant-owned financial snapshots. Dashboard metrics parse report values with Decimal-safe string handling.

## Sync Behavior

`POST /api/v1/qbo/sync?mode=full` performs a read-only full refresh into Polaris-owned financial cache tables. `POST /api/v1/qbo/sync?mode=incremental` uses the last successful checkpoint where supported.

Sync behavior:

- records start and completion time;
- stores resource counts by resource;
- stores report availability;
- preserves the last successful checkpoint if a run fails;
- does not advance checkpoints on failed runs;
- rejects duplicate concurrent sync for the same organization;
- writes zero records to QuickBooks.

## Verification Status

`GET /api/v1/qbo/verification` returns only safe status metadata. `POST /api/v1/qbo/verification` actively verifies refresh, company identity, resource reads, and report reads. Both are protected and tenant-bound.

Safe status may include:

- organization ID;
- expected and verified company names;
- verification status;
- authorization status;
- refresh status;
- last successful sync time;
- record counts;
- report availability;
- checkpoint status;
- last safe error summary;
- whether reauthorization is required.

It never returns tokens, client secrets, authorization codes, raw OAuth state, encryption keys, raw exception traces, or realm IDs.

## Health States

QuickBooks health can report:

- `not_configured`
- `authorization_required`
- `connected_unverified`
- `company_mismatch`
- `healthy`
- `degraded`
- `rate_limited`
- `synchronization_failed`
- `reauthorization_required`

Public system health does not expose QuickBooks details. Detailed connector health requires authentication, organization context, and connector permissions.

## Production Smoke Test

Follow `docs/integrations/quickbooks-production-runbook.md`. Production smoke testing is manual and protected. CI uses mocks only and never receives production Intuit credentials.

## Disconnect

`DELETE /api/v1/connectors/quickbooks/oauth/connection` requires `connector.write`, attempts provider token revocation, and deletes only the credential for the active organization. If provider revocation is unavailable, local encrypted credential deletion still proceeds safely.
