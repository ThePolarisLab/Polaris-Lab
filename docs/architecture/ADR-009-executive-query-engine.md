# ADR-009: Executive Query Engine

## Status

Accepted for PGE-009.9.

## Context

The Executive Read Model now receives deterministic projections from provider-specific evidence. Athena, dashboards, APIs, and future SDKs need a stable way to consume that model without depending on connector details or storage implementations.

## Decision

Hermes exposes a provider-neutral Executive Query Engine composed of:

1. Typed query contracts for filters, sorting, pagination, context, and results.
2. An `ExecutiveQueryRepository` abstraction.
3. An adapter over the existing `ExecutiveRepository`.
4. Business-oriented query methods for customers, fleet, finance, operations, tasks, alerts, and the executive dashboard.
5. Mandatory organization scoping on every query and direct entity read.

The query engine returns immutable page results and dashboard DTOs. Deterministic stable sorting is used so identical repository state and query input produce identical ordering.

## Consequences

- Athena does not read repositories or connectors directly.
- Storage engines may add indexed implementations without changing the public query API.
- Organization isolation is enforced at the query boundary.
- Query limits are bounded to prevent unintentional unbounded reads.
- The in-memory adapter evaluates filters in process; durable adapters can translate the same contracts into native database queries.

## Initial capabilities

- Equality, inequality, range, membership, and case-insensitive text filters.
- Nested field paths such as `lifetimeRevenue.amount`.
- Multi-column sorting.
- Offset/limit pagination.
- Customer risk queries.
- Fleet availability and utilization queries.
- Latest financial snapshot query.
- Load, task, and alert queries.
- Cross-domain executive dashboard summary.

## Deferred

- Cursor pagination.
- Aggregation DSL and grouped metrics.
- Query planning and index hints.
- Distributed caching.
- Authorization policy evaluation beyond organization isolation.
- Full-text and semantic search.
- Durable SQL/document-store adapters.
