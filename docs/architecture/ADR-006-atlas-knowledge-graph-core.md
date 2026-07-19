# ADR-006: Atlas Knowledge Graph Core

## Status

Accepted

## Context

PGE-006.1 introduced typed entities and PGE-006.2 introduced typed relationships. Atlas now needs a service boundary that combines both repositories, enforces graph integrity, and exposes graph-oriented queries without coupling callers to storage details.

## Decision

Introduce a `KnowledgeGraph` service that coordinates `EntityRepository` and `RelationshipRepository`.

The service will:

- create entities through the existing entity factory;
- create relationships only when both endpoint entities exist;
- expose incoming, outgoing, and bidirectional neighbor lookup;
- filter neighbor traversal by relationship type;
- prevent entity deletion while incident relationships exist;
- expose a consistent graph snapshot;
- preserve repository abstractions so persistent graph storage can replace in-memory storage later.

## Consequences

### Positive

- Dangling relationships are prevented at the graph boundary.
- Entity and relationship engines remain independently testable.
- Callers receive graph-oriented operations rather than repository-specific behavior.
- Future path finding and multi-hop traversal can build on the same service.

### Trade-offs

- Neighbor lookup currently scans relationships and performs repository lookups, which is appropriate for the in-memory milestone but not optimized for large graphs.
- Deletion is restrictive by design; cascading deletion is deferred until policy and audit requirements are defined.
- Multi-hop traversal and shortest-path queries are deferred to PGE-006.4.

## Follow-up

PGE-006.4 will add graph query and traversal algorithms, including bounded multi-hop paths and explainable traversal results.
