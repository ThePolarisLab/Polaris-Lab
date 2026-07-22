# ADR-024 — Runtime Configuration and Health Contract

- **Status:** Accepted
- **Date:** 2026-07-21
- **Milestone:** PGE-008.0A

## Context

The Chief of Staff application contained environment-specific assumptions in source code, including fixed CORS origins and static service metadata. Polaris needs reproducible development, staging, and founding-builder deployments without editing application code.

## Decision

1. Runtime identity and permitted frontend origins are supplied through environment variables.
2. The backend exposes `GET /health` as the machine-readable readiness contract.
3. Health output includes the runtime environment, organization context, API status, and database connectivity.
4. Health checks never expose credentials or secret values.
5. CI must execute backend runtime tests and a clean frontend production build.

## Environment variables

- `POLARIS_ENV`
- `POLARIS_SERVICE_NAME`
- `POLARIS_VERSION`
- `POLARIS_ORGANIZATION_SLUG`
- `POLARIS_CORS_ORIGINS`

## Consequences

- Development, staging, and builder profiles can use the same source artifact.
- Deployment systems can determine readiness from a stable endpoint.
- Mor Logistics is represented as configuration rather than a permanent source-code assumption.
- A future settings provider or secrets manager can replace environment loading without changing the public health contract.

## Follow-up

Frontend API URL and active-user context remain to be externalized in the next PGE-008.0A increment.
