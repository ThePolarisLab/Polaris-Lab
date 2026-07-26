# ADR-024 — Runtime Configuration, Health, and Workspace Context

- **Status:** Accepted
- **Date:** 2026-07-21
- **Updated:** 2026-07-26
- **Milestone:** PGE-008.0A / PGE-008.0B

## Context

The Chief of Staff application contained environment-specific assumptions in source code, including fixed CORS origins, a fixed frontend API URL, static service metadata, and a hard-coded executive user. Polaris needs reproducible development, staging, and founding-builder deployments without editing application code.

## Decision

1. Runtime identity and permitted frontend origins are supplied through environment variables.
2. The backend exposes `GET /health` as the machine-readable readiness contract.
3. Health output includes the runtime environment, organization context, API status, and database connectivity.
4. Health checks never expose credentials or secret values.
5. Frontend runtime context is built once in `runtimeConfig.js` and contains the API base URL plus active workspace identity.
6. Frontend components communicate through `apiClient.js`; direct component-level `fetch()` calls are not permitted.
7. Executive workspace requests derive the active user from runtime configuration rather than source-code constants.
8. CI executes backend runtime tests, frontend runtime/workspace tests, and a clean frontend production build.

## Backend environment variables

- `POLARIS_ENV`
- `POLARIS_SERVICE_NAME`
- `POLARIS_VERSION`
- `POLARIS_ORGANIZATION_SLUG`
- `POLARIS_CORS_ORIGINS`

## Frontend environment variables

- `VITE_API_BASE_URL`
- `VITE_WORKSPACE_USER_NAME`
- `VITE_WORKSPACE_ORGANIZATION`
- `VITE_WORKSPACE_NAME`

## Runtime boundary

The Python application under `chief-of-staff/` remains the operational web application and HTTP authority. The TypeScript intelligence domains under `src/` remain a separate library boundary. They may be integrated only through explicit adapters or versioned HTTP contracts; importing domain internals directly into the Python runtime or React components is not an accepted integration path.

## Consequences

- Development, staging, and builder profiles can use the same source artifact.
- Deployment systems can determine readiness from a stable endpoint.
- Mor Logistics is represented as configuration rather than a permanent source-code assumption.
- Executive and Builder workspaces use the same runtime and API-client foundations.
- A future authentication provider, settings provider, or secrets manager can replace environment loading without changing component contracts.
- Frontend runtime assumptions are covered by automated tests.

## Governance

The controlled Mor Logistics builder profile remains observer/advisory by default. External-system mutations require a separately reviewed capability, explicit authorization, audit records, and a dedicated production-readiness decision.
