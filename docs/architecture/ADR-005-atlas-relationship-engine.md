# ADR-005: Atlas Relationship Engine

## Status

Accepted for PGE-006.2.

## Context

Atlas entities are useful only when Polaris can express how they are connected. Relationships must be typed, explainable, versioned, and queryable without coupling the domain to a specific graph database.

## Decision

Introduce an explicit relationship domain model with:

- stable relationship identity;
- source and target entity identifiers;
- a controlled relationship vocabulary;
- confidence, lifecycle status, metadata, and timestamps;
- validation that rejects malformed and self-referential edges;
- a repository interface with an in-memory implementation;
- query filters for source, target, type, and status.

The first implementation remains persistence-agnostic. A durable graph adapter can implement the same repository contract later.

## Consequences

### Positive

- Relationships become auditable first-class records.
- Atlas can evolve toward graph traversal without rewriting callers.
- Tests remain deterministic and fast.
- Storage technology remains replaceable.

### Trade-offs

- The initial controlled vocabulary requires deliberate extension.
- Entity existence is not yet enforced across repository boundaries.
- Multi-hop traversal belongs to a later Atlas milestone.

## Follow-up

PGE-006.3 will combine entities and relationships into graph traversal and integrity services.
