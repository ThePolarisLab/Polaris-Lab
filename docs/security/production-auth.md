# Production Authentication Requirements

Polaris backend APIs are protected by the provider-neutral security model in `chief-of-staff/backend/app/security`.

## Public endpoints

The following endpoints are intentionally public:

- `GET /`
- `GET /health`
- `POST /api/v1/auth/local/token` in `development` and `test` only

All operational routers are mounted with FastAPI permission dependencies in `chief-of-staff/backend/app/main.py`.

## Required request headers

Protected API requests require:

```text
Authorization: Bearer <access-token>
X-Polaris-Organization: <organization-id>
```

The bearer credential is validated by the configured authentication provider and resolved to an active `Identity`. The organization header is then checked against an active `OrganizationMembership`. Cross-organization access must fail closed.

## Frontend runtime configuration

The frontend API client sends auth context from local storage first, then from runtime environment fallback values:

```text
VITE_POLARIS_ACCESS_TOKEN
VITE_POLARIS_ORGANIZATION_ID
```

Interactive production deployments should replace env-token bootstrapping with the approved identity-provider login flow. Static tokens must not be embedded in production frontend bundles.

## Permission model

Initial route groups use these permissions:

- organization APIs: `organization.read` or `organization.manage`
- identity APIs: `identity.manage`
- connector and QuickBooks APIs: `connector.manage`
- dashboard, memory, missions, reasoning, work context, and team notes: `executive.read`
- events and system inspection: `organization.read`

Write-sensitive routes should be split into method-level permissions as the API standardization work continues.

## Release gate

A production release must verify:

- every protected route rejects missing bearer credentials;
- every protected route rejects missing organization context;
- inactive identities are rejected;
- inactive or missing organization memberships are rejected;
- cross-organization requests are denied;
- frontend requests include auth headers;
- local-token issuance is unavailable outside `development` and `test`.
