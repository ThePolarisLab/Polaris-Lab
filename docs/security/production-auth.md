# Production Authentication Requirements

Polaris backend APIs are protected by the provider-neutral security model in `chief-of-staff/backend/app/security`.

The route inventory for this gate is maintained in `docs/security/route-security-matrix.md`. Tenant ownership rules are maintained in `docs/security/tenant-isolation.md`.

## Public endpoints

The following endpoints are intentionally public:

- `GET /`
- `GET /health`
- `POST /api/v1/auth/local/token` in `development` and `test` only
- `GET /api/v1/connectors/quickbooks/oauth/callback`

Public `/` and `/health` responses expose only generic status. Detailed system health, runtime info, version details, database status, organization metadata, connector metadata, company identity, and financial status require authenticated tenant-bound routes.

The QuickBooks callback is public only because Intuit redirects cannot carry Polaris bearer headers. It must validate signed, unexpired, single-use OAuth state that was created by an authenticated connector manager.

## Required request headers

Protected API requests require:

```text
Authorization: Bearer <access-token>
X-Polaris-Organization: <organization-id>
```

The bearer credential is validated by the configured authentication provider and resolved to an active `Identity`. The organization header is checked against an active `OrganizationMembership`. Cross-organization access fails closed through membership lookup, path-boundary checks, and tenant-owned query filters.

## Authentication flow

1. Development and test clients request `POST /api/v1/auth/local/token` with an `identity_id` and `organization_id`.
2. The backend validates that the environment is `development` or `test`.
3. The local provider signs a short-lived token with `POLARIS_LOCAL_AUTH_SECRET`.
4. `SecurityService` authenticates the token subject and verifies active organization membership.
5. The frontend stores the token and organization context for the current browser session and sends both headers on protected calls.
6. `401` responses clear the frontend session. `403` responses keep the session but render a forbidden state.

Production must replace local-token login with the approved identity-provider flow before human-user release. The local provider remains a development bootstrap mechanism only.

## Frontend session handling

The frontend API client sends auth context from local storage first, then from runtime fallback values:

```text
VITE_POLARIS_ACCESS_TOKEN
VITE_POLARIS_ORGANIZATION_ID
```

Runtime fallback values are for local controlled environments. Static bearer tokens must not be embedded in production frontend bundles. Protected workspaces do not render unless both an access token and organization ID are present.

## Permission model

Phase 1.1 uses split read/write permissions:

- `platform.admin`: platform tenant administration; can create/list/inspect all organizations.
- `organization.read`: organization profile, fleet reads, event health/metrics.
- `organization.write`: organization-owned fleet mutations.
- `identity.read`: visible identities and memberships for the active organization.
- `identity.write`: identity creation and membership mutation.
- `connector.read`: connector health/status and non-financial connector inspection.
- `connector.write`: connector sync/lifecycle, OAuth initiation/disconnect, and active verification.
- `financial.read`: QuickBooks financial reads, cache status, and financial summaries.
- `financial.write`: QuickBooks financial sync/cache writes.
- `executive.read`: dashboard, memory, missions, reasoning, work context, and team note reads.
- `executive.write`: memory, mission, and team-note mutations.

The legacy `*.manage` enum names remain compatibility aliases for `*.write`, but route documentation should use the canonical split names.

## Tenant isolation

For protected API routes, `AuthenticatedPrincipal.organization_id` is the source of truth. Tenant-owned rows use `organization_id` foreign keys and every query over tenant-owned data must filter by the principal organization.

Do not use `settings.organization_slug` or `POLARIS_ORGANIZATION_SLUG` as an authorization or persistence boundary. The slug is local/bootstrap metadata only and must not be exposed as public health metadata.

## Database lifecycle

Staging and production must use persistent PostgreSQL and run migrations before application startup:

```bash
alembic upgrade head
alembic current
```

The backend refuses to start in `production` or `staging` if the database is unversioned or not at Alembic head. Development and test may explicitly create isolated schemas through `POLARIS_AUTO_CREATE_SCHEMA`; that behavior is not available in managed environments.

Existing legacy adoption with unowned tenant rows may use `POLARIS_TENANT_BACKFILL_ORGANIZATION_ID` only after backup and ownership review. No-organization legacy bootstrap requires all three variables documented in `docs/database/tenant-backfill-plan.md` and must be removed after the migration succeeds.

## QuickBooks OAuth state

QuickBooks authorization initiation requires `connector.write`. The generated OAuth state is:

- signed with `POLARIS_QBO_OAUTH_STATE_SECRET`;
- stored with the initiating principal identity;
- stored with the initiating organization ID;
- valid for 10 minutes;
- consumed exactly once through an atomic conditional update.

The callback stores tokens only for the organization ID recorded in the consumed state. Phase 3A then verifies CompanyInfo against the configured Mor Logistics company before accepting synchronized financial data. If company verification fails, the stored credential for that organization is deleted.

## Required Environment Variables

Development/test:

```text
POLARIS_ENV=development|test
POLARIS_LOCAL_AUTH_SECRET=<optional in development, required in test suites when deterministic tokens are needed>
DATABASE_URL=<optional SQLite URL; defaults to sqlite:///./polaris.db>
POLARIS_AUTO_CREATE_SCHEMA=<optional explicit dev/test schema bootstrap toggle>
```

Production/staging:

```text
POLARIS_ENV=production|staging
DATABASE_URL=<required persistent PostgreSQL database URL>
POLARIS_AUTO_CREATE_SCHEMA=false
POLARIS_LOCAL_AUTH_SECRET=<minimum 32 characters; must not be polaris-dev-only>
POLARIS_CORS_ORIGINS=<allowed frontend origins>
POLARIS_FRONTEND_URL=<deployed frontend origin>
```

Existing database adoption:

```text
POLARIS_TENANT_BACKFILL_ORGANIZATION_ID=<optional existing organization ID for verified legacy single-target backfills>
POLARIS_TENANT_BACKFILL_ORGANIZATION_SLUG=<optional one-time no-organization legacy bootstrap slug>
POLARIS_TENANT_BACKFILL_ORGANIZATION_NAME=<optional one-time no-organization legacy bootstrap display name>
```

QuickBooks production adapter:

```text
POLARIS_QBO_ENVIRONMENT=production
POLARIS_QBO_CLIENT_ID
POLARIS_QBO_CLIENT_SECRET
POLARIS_QBO_REDIRECT_URI
POLARIS_QBO_OAUTH_STATE_SECRET=<minimum 32 characters>
POLARIS_QBO_TOKEN_ENCRYPTION_KEY=<Fernet key>
POLARIS_QBO_EXPECTED_COMPANY_NAME=MOR LOGISTICS MANITOBA LIMITED
POLARIS_QBO_MINOR_VERSION=75
POLARIS_QBO_REQUEST_TIMEOUT_SECONDS=20
POLARIS_QBO_MAX_ATTEMPTS=3
POLARIS_QBO_RETRY_BASE_SECONDS=0.25
```

Sandbox mode is allowed only in `development` or `test`. `POLARIS_ORGANIZATION_SLUG` is no longer used for QuickBooks credential ownership.

## Release gate

A production release must verify:

- every protected route rejects missing bearer credentials;
- every protected route rejects missing organization context;
- inactive identities are rejected;
- inactive or missing organization memberships are rejected;
- cross-organization requests are denied;
- tenant-owned database queries filter by organization ID;
- connector sync and disconnect require `connector.write`;
- QuickBooks OAuth state cannot be reused or raced;
- QuickBooks production verification exposes no tokens, client secrets, OAuth codes, raw OAuth state, encryption keys, or realm IDs;
- frontend requests include auth headers;
- frontend clears expired sessions on `401`;
- frontend displays forbidden state on `403`;
- local-token issuance is unavailable outside `development` and `test`;
- the default `polaris-dev-only` secret cannot be used silently in production;
- `alembic upgrade head` is run before managed application startup;
- managed application startup rejects stale or unversioned schemas;
- a verified backup exists before production migrations;
- public `/` and `/health` contain only generic status.
