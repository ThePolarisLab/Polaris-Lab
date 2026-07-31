# Production Authentication Requirements

Polaris backend APIs are protected by the provider-neutral security model in `chief-of-staff/backend/app/security`. Phase 3B adds an internal-launch production authentication path without re-enabling the development local token endpoint.

The route inventory for this gate is maintained in `docs/security/route-security-matrix.md`. Tenant ownership rules are maintained in `docs/security/tenant-isolation.md`. First-admin operator steps are maintained in `docs/security/production-auth-bootstrap.md`.

## Public endpoints

The following endpoints are intentionally public or public at the bearer-auth layer:

- `GET /`
- `GET /health`
- `GET /api/v1/auth/bootstrap/status`
- `POST /api/v1/auth/bootstrap`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
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

Development and test:

1. Development and test clients may request `POST /api/v1/auth/local/token` with an `identity_id` and `organization_id`.
2. The backend validates that the environment is `development` or `test`.
3. The local provider signs a short-lived token with `POLARIS_LOCAL_AUTH_SECRET`.
4. `SecurityService` authenticates the token subject and verifies active organization membership.

Production and staging:

1. An operator configures `POLARIS_BOOTSTRAP_ADMIN_EMAIL`, `POLARIS_BOOTSTRAP_SECRET`, and `POLARIS_SESSION_SECRET` in Render.
2. `POST /api/v1/auth/bootstrap` creates the fixed Mor Logistics organization and `mor-admin` owner identity after validating the one-time bootstrap secret.
3. The bootstrap writes a persistent completion marker and rejects all repeat attempts.
4. The operator removes `POLARIS_BOOTSTRAP_SECRET` from Render after success.
5. Users sign in with `POST /api/v1/auth/login` using email and password.
6. Passwords are verified against bcrypt hashes.
7. The backend issues a short-lived signed access token and a random refresh token stored only as a SHA-256 hash.
8. `POST /api/v1/auth/refresh` rotates refresh tokens. Reuse of an old refresh token is rejected.
9. `POST /api/v1/auth/logout` revokes the current server-side session.
10. `401` responses trigger refresh once in the frontend; if refresh fails, the frontend clears the session. `403` responses keep the session but render a forbidden state.

External identity-provider integration remains a later release phase before broad human-user rollout.

## Frontend session handling

The frontend API client stores session material in browser session storage where available, falling back to local storage only in constrained test/runtime contexts. It sends the access token and active organization on protected calls.

Static bearer tokens must not be embedded in production frontend bundles. Protected workspaces do not render unless both an access token and organization ID are present.

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

The `owner` and `admin` roles receive read and write permissions required for connector and financial verification. The `platform_admin` role remains reserved for platform-wide tenant administration.

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

Phase 3B migration `202607300002` creates production password/session/bootstrap tables and aligns `organization_memberships.id` with the ORM string ID model without deleting membership rows.

## Required Environment Variables

Development/test:

```text
POLARIS_ENV=development|test
POLARIS_LOCAL_AUTH_SECRET=<optional in development, required in test suites when deterministic tokens are needed>
POLARIS_SESSION_SECRET=<test/dev signing secret when exercising production session routes>
DATABASE_URL=<optional SQLite URL; defaults to sqlite:///./polaris.db>
POLARIS_AUTO_CREATE_SCHEMA=<optional explicit dev/test schema bootstrap toggle>
```

Production/staging:

```text
POLARIS_ENV=production|staging
DATABASE_URL=<required persistent PostgreSQL database URL>
POLARIS_AUTO_CREATE_SCHEMA=false
POLARIS_CORS_ORIGINS=<allowed frontend origins>
POLARIS_FRONTEND_URL=<deployed frontend origin>
POLARIS_SESSION_SECRET=<minimum 32 characters>
POLARIS_ACCESS_TOKEN_TTL_SECONDS=900
POLARIS_REFRESH_TOKEN_TTL_SECONDS=1209600
POLARIS_BOOTSTRAP_ADMIN_EMAIL=<required until first admin is created>
POLARIS_BOOTSTRAP_SECRET=<required only until first admin is created; remove after success>
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
- first bootstrap succeeds only with configured strong secret;
- second bootstrap is rejected;
- password hashes are not plaintext;
- login failures are rate-limited;
- refresh token rotation rejects replay;
- logout revokes server session;
- inactive identities are rejected;
- inactive or missing organization memberships are rejected;
- cross-organization requests are denied;
- tenant-owned database queries filter by organization ID;
- connector sync and disconnect require `connector.write`;
- QuickBooks OAuth state cannot be reused or raced;
- QuickBooks production verification exposes no tokens, client secrets, OAuth codes, raw OAuth state, encryption keys, or realm IDs;
- frontend requests include auth headers;
- frontend clears expired sessions on failed refresh;
- frontend displays forbidden state on `403`;
- local-token issuance is unavailable outside `development` and `test`;
- the default `polaris-dev-only` secret cannot be used silently in production;
- `alembic upgrade head` is run before managed application startup;
- managed application startup rejects stale or unversioned schemas;
- a verified backup exists before production migrations;
- public `/` and `/health` contain only generic status.