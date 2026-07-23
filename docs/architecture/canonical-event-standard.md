# IA-002 — Canonical Event Catalog and Schema Standard

**Status:** Draft implementation baseline  
**Milestone:** PGE-008.3  
**Architecture:** Constitution-first, event-driven, connector-first

## Purpose

Define the vendor-neutral event contract used by Polaris services, connectors, workflows, Executive Memory, and Athena.

## Naming

Canonical event names use lowercase dotted segments and terminate with a major version:

```text
<domain>.<entity>.<action>.v<major>
```

Examples:

- `github.commit.observed.v1`
- `finance.invoice.created.v1`
- `communication.email.received.v1`
- `athena.recommendation.generated.v1`

Breaking schema changes require a new major version. Compatible optional fields may be added without renaming the event.

## Required envelope

Every event includes:

- `event_id`
- `event_type`
- `event_version`
- `occurred_at`
- `recorded_at`
- `severity`
- `classification`
- `payload`
- `metadata`

Tenant-aware production events should also include `organization_id` and `tenant_id` before leaving a connector boundary.

## Traceability

The envelope supports:

- `correlation_id` for a business transaction or workflow
- `causation_id` for the event or command that caused this event
- `trace_id` for end-to-end technical tracing
- `idempotency_key` for duplicate-safe ingestion

## Source, actor, and subject

- `source` identifies the authoritative service or connector.
- `actor` identifies the human or system responsible for the action.
- `subject` identifies the primary business object described by the event.

The legacy `connector` and `entity` fields remain temporarily available for compatibility while existing connectors migrate.

## Security classification

Supported classifications are:

1. `public`
2. `internal`
3. `confidential`
4. `restricted`

Consumers must enforce tenant isolation and authorization independently of event transport.

## Immutability and time

Canonical events are immutable after creation. Timestamps must be timezone-aware and are normalized to UTC.

## Initial catalog

| Domain | Event | Owner |
|---|---|---|
| GitHub | `github.commit.observed.v1` | GitHub Connector |
| Organization | `organization.profile.created.v1` | Organization Service |
| Identity | `identity.user.created.v1` | Identity Service |
| Connector | `connector.sync.completed.v1` | Connector Runtime |
| Communication | `communication.email.received.v1` | Communications Gateway |
| Finance | `finance.invoice.created.v1` | Finance Domain Service |
| Memory | `memory.record.stored.v1` | Executive Memory Service |
| Athena | `athena.recommendation.generated.v1` | Athena Orchestrator |

## Current boundary

PGE-008.3 establishes the canonical in-process contract and migrates the GitHub connector. Persistence, distributed delivery, schema registry storage, replay orchestration, and dead-letter queues remain future increments.

## Verification

- Canonical names reject invalid or unversioned event types.
- Naive timestamps are rejected.
- Event instances are immutable.
- Existing Event Bus behavior remains intact.
- GitHub commit events carry structured source, subject, version, and idempotency data.
