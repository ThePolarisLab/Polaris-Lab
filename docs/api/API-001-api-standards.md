# API-001 — Polaris API Standards

**Status:** Proposed  
**Version:** 1.0  
**Owner:** Polaris Architecture  
**Applies to:** Internal services, Executive Workspace APIs, connector-facing APIs, and future partner APIs

## 1. Purpose

This document defines the standard contract for APIs across Polaris. Its purpose is to make every API predictable, secure, traceable, evolvable, and suitable for executive-grade business workflows.

Polaris APIs must support the product mission:

> Capture data once. Connect everything. Turn information into executive decisions.

## 2. Architectural position

Polaris currently follows a modular-monolith-first architecture. API boundaries must still reflect domain ownership so that high-value domains can later be extracted without redesigning contracts.

API layers:

1. **Experience APIs** — optimized for Executive Workspace and administrative interfaces.
2. **Domain APIs** — finance, fleet, dispatch, fuel, maintenance, safety, HR, and intelligence.
3. **Connector APIs** — synchronization, connection health, credentials, mappings, and external-system events.
4. **Platform APIs** — identity, permissions, audit, notifications, configuration, and observability.

Business rules belong in domain services, not controllers, route handlers, connectors, or UI code.

## 3. Protocol and representation

- External and browser-consumed APIs use HTTPS and JSON.
- UTF-8 is required.
- JSON field names use `snake_case`.
- Resource names use plural nouns.
- Timestamps use ISO 8601 in UTC, for example `2026-07-29T16:30:00Z`.
- Dates without times use `YYYY-MM-DD`.
- Durations use ISO 8601 duration notation where practical.
- Boolean fields use `true` and `false`, never `0`, `1`, `yes`, or `no`.
- Monetary amounts are represented as decimal strings plus an ISO 4217 currency code.

Example:

```json
{
  "amount": "1250.75",
  "currency": "CAD"
}
```

Floating-point numbers must not be used for financial calculations.

## 4. Base path and versioning

Publicly consumed REST endpoints use:

```text
/api/v1/{resource}
```

Rules:

- Major breaking changes require a new path version.
- Additive fields are non-breaking.
- Removing or renaming fields is breaking.
- Changing field meaning, units, validation, authorization, or nullability can be breaking.
- Deprecated fields must remain available for at least one supported release cycle unless security or legal risk requires faster removal.
- Deprecation must be documented and exposed through response headers where applicable.

Internal function signatures and event schemas must also be explicitly versioned when consumed across domain boundaries.

## 5. Resource design

Use resource-oriented URLs:

```text
GET    /api/v1/customers
POST   /api/v1/customers
GET    /api/v1/customers/{customer_id}
PATCH  /api/v1/customers/{customer_id}
DELETE /api/v1/customers/{customer_id}
```

Nested routes are allowed only when the parent relationship is essential:

```text
GET /api/v1/loads/{load_id}/stops
```

Avoid deep nesting beyond one parent-child relationship. Prefer filters for broader relationships.

Actions that do not fit CRUD use explicit verbs:

```text
POST /api/v1/connectors/{connector_id}/sync
POST /api/v1/invoices/{invoice_id}/send
POST /api/v1/alerts/{alert_id}/acknowledge
```

## 6. Identifiers

- API resources expose stable Polaris identifiers.
- IDs are opaque strings; clients must not infer meaning from their format.
- External-system IDs are stored separately and exposed only where traceability is required.
- Client-supplied idempotency keys are required for operations that may create duplicate financial or operational records.

Example header:

```text
Idempotency-Key: 2f669d1c-42c4-4bf1-bd26-b3e177cdca4e
```

## 7. Request standards

### 7.1 Validation

Every request must be validated for:

- schema,
- type,
- required fields,
- allowed values,
- business invariants,
- organization scope,
- permissions.

Invalid requests return a structured error response. Validation errors must identify the relevant field without exposing sensitive internal details.

### 7.2 Partial updates

Use `PATCH` for partial updates. Omitted fields remain unchanged. A field explicitly set to `null` is cleared only when the schema permits null values.

### 7.3 Concurrency

Mutable resources should expose a `version` or ETag. Conflicting updates return `409 Conflict` or `412 Precondition Failed`.

## 8. Response envelope

Single-resource success:

```json
{
  "data": {
    "id": "pol_load_004219",
    "status": "in_transit"
  },
  "meta": {
    "request_id": "req_01J5Y7P6M6R9K2"
  }
}
```

Collection success:

```json
{
  "data": [],
  "meta": {
    "request_id": "req_01J5Y7P6M6R9K2",
    "page": 1,
    "page_size": 50,
    "total": 0
  },
  "links": {
    "next": null,
    "previous": null
  }
}
```

A `204 No Content` response must not include a body.

## 9. Pagination, filtering, sorting, and search

Standard query parameters:

```text
?page=1&page_size=50
?sort=-created_at,name
?status=active
?created_from=2026-07-01&created_to=2026-07-31
?q=laredo
```

Rules:

- Default page size: 50.
- Maximum page size: 200 unless a domain ADR approves otherwise.
- Large or frequently changing datasets should use cursor pagination.
- Sort fields and filter fields must be allow-listed.
- Search must not silently broaden organization scope.

## 10. Error model

All errors use the same structure:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request could not be processed.",
    "details": [
      {
        "field": "due_date",
        "reason": "must be on or after invoice_date"
      }
    ],
    "request_id": "req_01J5Y7P6M6R9K2"
  }
}
```

Required HTTP status usage:

| Status | Meaning |
|---|---|
| `200` | Successful read or update |
| `201` | Resource created |
| `202` | Asynchronous operation accepted |
| `204` | Successful operation with no body |
| `400` | Malformed or invalid request |
| `401` | Authentication required or invalid |
| `403` | Authenticated but not authorized |
| `404` | Resource not found in permitted scope |
| `409` | Conflict, duplicate, or invalid state transition |
| `412` | Concurrency precondition failed |
| `422` | Semantically invalid data when more precise than `400` |
| `429` | Rate limit exceeded |
| `500` | Unexpected server failure |
| `503` | Dependency or service temporarily unavailable |

Internal stack traces, secrets, SQL, tokens, and vendor payloads must never be returned to clients.

## 11. Authentication and authorization

- Human users authenticate through the approved identity provider.
- Service-to-service calls use short-lived credentials or workload identity.
- Every request is scoped to an organization unless explicitly designated as platform administration.
- Authorization is enforced server-side for every operation.
- Role checks alone are insufficient where record-level or field-level policy is required.
- Cross-organization access is denied by default.
- Sensitive operations require audit events.

Required contextual claims include:

- subject,
- organization,
- roles or permissions,
- token issuer,
- issued and expiry times.

## 12. Multi-tenancy

Every tenant-owned record must be associated with an `organization_id` internally. Clients must not be trusted to establish organization scope merely by sending an organization identifier.

Tenant isolation must be enforced in repositories or data-access policies and tested with negative authorization tests.

## 13. Auditability and traceability

Every request receives a correlation identifier.

Recommended headers:

```text
X-Request-ID
X-Correlation-ID
Traceparent
```

Audit records are required for:

- authentication and authorization changes,
- connector credential changes,
- financial mutations,
- load and dispatch state changes,
- safety and compliance changes,
- exports of sensitive data,
- administrative actions,
- AI-assisted actions that modify records.

Audit logs must record who, what, when, organization, source, result, and relevant before/after references without storing secrets.

## 14. Asynchronous operations

Operations that may exceed normal request latency return `202 Accepted` and a job resource.

```json
{
  "data": {
    "job_id": "job_01J5Y80R9A0TQ1",
    "status": "queued",
    "status_url": "/api/v1/jobs/job_01J5Y80R9A0TQ1"
  }
}
```

Jobs must be idempotent where possible and expose:

- queued time,
- start time,
- completion time,
- progress,
- result summary,
- failure code,
- retry state.

Connector full syncs, bulk imports, report generation, and large exports should normally use this pattern.

## 15. Rate limiting and quotas

- Rate limits are applied by identity, organization, endpoint class, and risk level.
- Responses include retry guidance.
- Vendor API quotas must be protected by connector-level throttling.
- Critical operational ingestion may use separate quotas from interactive dashboards.

Example:

```text
Retry-After: 60
```

## 16. Caching

- APIs must define whether responses are cacheable.
- Sensitive or user-specific responses default to `Cache-Control: no-store`.
- Reference data may use ETags and conditional requests.
- KPI responses must include an `as_of` timestamp and data-freshness information.

Example KPI metadata:

```json
{
  "data": {
    "value": "18.4",
    "unit": "percent"
  },
  "meta": {
    "as_of": "2026-07-29T16:30:00Z",
    "source_freshness": "current",
    "request_id": "req_01J5Y7P6M6R9K2"
  }
}
```

## 17. File exports and imports

- Large exports are asynchronous.
- Download links must be short-lived and scoped.
- Import APIs must support validation-only mode before commit.
- Import results must report accepted, rejected, and warning counts.
- Uploaded content must be scanned and size-limited.
- CSV and spreadsheet imports must define locale, date, decimal, and encoding expectations explicitly.

## 18. Webhooks

Outbound webhooks must include:

- event identifier,
- event type,
- schema version,
- organization identifier,
- occurrence time,
- payload,
- cryptographic signature.

Delivery requirements:

- at-least-once delivery,
- exponential retry,
- replay protection,
- idempotent consumer guidance,
- delivery logs,
- dead-letter handling,
- secret rotation.

Webhook consumers must not assume ordered delivery unless a specific event contract guarantees it.

## 19. Event compatibility

REST APIs and domain events are separate contracts. An event records a fact that occurred; it is not a command disguised as a fact.

Example event name:

```text
finance.invoice.paid.v1
```

Events must include:

- `event_id`,
- `event_type`,
- `event_version`,
- `occurred_at`,
- `organization_id`,
- `source`,
- `correlation_id`,
- `data`.

Consumers must tolerate additive fields.

## 20. Connector API requirements

Every connector API must expose or support:

- connection status,
- authentication state without exposing credentials,
- capability discovery,
- last successful sync,
- current sync state,
- records processed,
- errors and retry state,
- full sync,
- incremental sync,
- disconnect or revoke,
- mapping version,
- health checks.

Suggested resources:

```text
GET  /api/v1/connectors
GET  /api/v1/connectors/{connector_id}
POST /api/v1/connectors/{connector_id}/test
POST /api/v1/connectors/{connector_id}/sync
GET  /api/v1/connectors/{connector_id}/sync-jobs
GET  /api/v1/connectors/{connector_id}/health
POST /api/v1/connectors/{connector_id}/disconnect
```

## 21. KPI and executive-intelligence APIs

Every KPI response must be explainable and traceable. It must define:

- value,
- unit,
- period,
- comparison period,
- trend,
- status,
- calculation version,
- source systems,
- freshness,
- drill-down link.

AI-generated recommendations must include:

- recommendation text,
- evidence references,
- confidence or reliability indicator,
- generation time,
- model or rule version,
- whether human approval is required,
- permitted actions.

An AI response must not present an unsupported conclusion as a verified fact.

## 22. OpenAPI and documentation

- Every HTTP API must be represented in OpenAPI.
- The generated specification must be validated in CI.
- Examples must be executable or schema-valid.
- Each endpoint documents authorization, errors, idempotency, pagination, and data freshness where relevant.
- Code and API documentation must change in the same pull request.
- Published contracts must identify status: experimental, beta, stable, deprecated, or retired.

## 23. Testing requirements

Minimum test coverage by contract:

1. schema validation,
2. successful requests,
3. authentication failure,
4. authorization denial,
5. tenant-isolation denial,
6. invalid state transitions,
7. idempotency,
8. concurrency conflicts,
9. pagination and filters,
10. error-shape consistency,
11. dependency failure behavior,
12. audit-event creation.

Contract tests are required for domain boundaries and connectors. Breaking API changes require explicit migration tests.

## 24. Observability and service objectives

APIs must emit structured logs and metrics for:

- request count,
- latency,
- error rate,
- status code,
- endpoint,
- organization-safe identifier,
- dependency latency,
- retry count,
- rate-limit events.

Sensitive fields must be redacted.

Initial target for ordinary interactive reads:

- p95 server response time under 500 ms, excluding third-party dependencies,
- no synchronous vendor API calls on primary dashboard paths unless explicitly approved,
- graceful degradation when non-critical dependencies fail.

Targets are proposed and must be validated against real production workloads before becoming release gates.

## 25. Security baseline

APIs must:

- enforce TLS,
- validate content type and size,
- use parameterized data access,
- apply least privilege,
- protect against mass assignment,
- prevent insecure direct-object references,
- restrict CORS,
- rotate secrets,
- redact logs,
- verify webhook signatures,
- reject expired or replayed credentials,
- receive dependency and vulnerability scanning.

Security-sensitive exceptions require an ADR and explicit approval.

## 26. Change governance

An API change requires:

- identified owner,
- affected consumers,
- compatibility classification,
- updated OpenAPI schema,
- tests,
- migration plan for breaking changes,
- documentation,
- release-note entry.

Breaking changes to stable APIs require an ADR.

## 27. Definition of done

An API is complete only when:

- its business purpose is documented,
- domain ownership is clear,
- authentication and authorization are implemented,
- organization isolation is tested,
- schemas and examples are published,
- errors follow the standard model,
- audit and observability requirements are met,
- idempotency and concurrency are addressed,
- automated tests pass,
- documentation matches implementation,
- no secrets or sensitive data are exposed.

## 28. Adoption plan

1. Apply API-001 to all new endpoints immediately after acceptance.
2. Inventory existing APIs and classify deviations.
3. Add a shared response/error library.
4. Generate and validate OpenAPI in CI.
5. Add tenant-isolation and authorization contract tests.
6. Migrate existing endpoints incrementally; do not break working consumers merely to achieve cosmetic consistency.
7. Record justified exceptions in ADRs or the technical-debt register.

## 29. Decision summary

Polaris adopts consistent, versioned, resource-oriented APIs with strong tenant isolation, structured errors, idempotent mutations, explicit traceability, OpenAPI contracts, and explainable KPI and AI responses.

This document describes the proposed standard. It does not claim that every existing endpoint currently complies. Repository verification and incremental adoption are required before declaring full implementation.