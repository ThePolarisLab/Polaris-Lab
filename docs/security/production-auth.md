# Production Authentication Requirements

Polaris backend APIs are protected by the provider-neutral security model in `chief-of-staff/backend/app/security`.

The route inventory for this gate is maintained in `docs/security/route-security-matrix.md`.

## Public endpoints

The following endpoints are intentionally public:

- `GET /`
- `GET /health`
- `POST /api/v1/auth/local/token` in `development` and `test` only
- `GET /api/v1/connectors/quickbooks/oauth/callback`

The QuickBooks callback is public only because Intuit redirects cannot carry Polaris bearer headers. It must validate signed, unexpired, single-use OAuth state that was created by an authenticated connector manager.

## Required request headers

Protected API requests require:

```text
Authorization: Bearer <access-token>
X-Polaris-Organization: <organization-id>
```

The bearer credential is validated by the configured authentication provider and resolved to an active `Identity`. The organization header is checked against an active `OrganizationMembership`. Cross-organization access fails closed through membership lookup and, where the route contains an `organization_id` path parameter, `require_organization_path_match`.

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

Initial route groups use these permissions:

- organization reads and fleet reads: `organization.read`
- organization creation/listing and admin organization inspection: `organization.manage`
- identity reads: `identity.read`
- identity and membership mutations: `identity.manage`
- connector/GitHub/QuickBooks read operations: `connector.read`
- connector sync, connector disconnect, GitHub writes, and QuickBooks OAuth initiation: `connector.manage`
- dashboard, memory, missions, reasoning, work context, team notes, and financial executive summary: `executive.read`
- events and system inspection: `organization.read`

Write-sensitive routes should continue to move toward method-level permissions as API-001 adoption proceeds.

## QuickBooks OAuth state

QuickBooks authorization initiation requires `connector.manage`. The generated OAuth state is:

- signed with `POLARIS_QBO_OAUTH_STATE_SECRET`;
- stored with the initiating principal identity;
- stored with the initiating organization ID and configured organization slug;
- valid for 10 minutes;
- consumed exactly once by the callback.

The callback stores tokens only for the organization slug recorded in the consumed state. If company verification fails, the stored credential for that slug is deleted.

## Required Environment Variables

Development/test:

```text
POLARIS_ENV=development|test
POLARIS_LOCAL_AUTH_SECRET=<optional in development, required in test suites when deterministic tokens are needed>
```

Production/staging:

```text
POLARIS_ENV=production|staging
POLARIS_LOCAL_AUTH_SECRET=<minimum 32 characters; must not be polaris-dev-only>
POLARIS_CORS_ORIGINS=<allowed frontend origins>
```

QuickBooks OAuth:

```text
POLARIS_QBO_CLIENT_ID
POLARIS_QBO_CLIENT_SECRET
POLARIS_QBO_REDIRECT_URI
POLARIS_QBO_OAUTH_STATE_SECRET=<minimum 32 characters>
POLARIS_QBO_TOKEN_ENCRYPTION_KEY=<Fernet key>
POLARIS_FRONTEND_URL
POLARIS_ORGANIZATION_SLUG
```

## Release gate

A production release must verify:

- every protected route rejects missing bearer credentials;
- every protected route rejects missing organization context;
- inactive identities are rejected;
- inactive or missing organization memberships are rejected;
- cross-organization requests are denied;
- connector sync and disconnect require `connector.manage`;
- QuickBooks OAuth state cannot be reused;
- frontend requests include auth headers;
- frontend clears expired sessions on `401`;
- frontend displays forbidden state on `403`;
- local-token issuance is unavailable outside `development` and `test`;
- the default `polaris-dev-only` secret cannot be used silently in production.
