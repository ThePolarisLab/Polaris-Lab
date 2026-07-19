# ADR-007: Atlas Graph Query Engine

## Status

Accepted

## Context

The Atlas Knowledge Graph Core supports direct neighbor lookup, but executive questions often require following chains of relationships. Atlas needs deterministic, bounded, explainable multi-hop traversal without infinite loops.

## Decision

Implement a repository-agnostic `GraphQueryEngine` over `KnowledgeGraph` using breadth-first search.

The engine provides:

- bounded traversal with a configurable maximum depth;
- shortest-path discovery;
- incoming, outgoing, or bidirectional traversal;
- relationship-type constraints;
- cycle protection through a visited-entity set;
- explicit path steps containing the source entity, relationship, target entity, and traversal direction.

The default maximum depth is three and the hard safety limit is twenty.

## Consequences

### Positive

- Breadth-first search guarantees the shortest unweighted path.
- Query traces are directly explainable to Athena and users.
- Depth and type constraints bound cost and reduce irrelevant results.
- The engine remains independent of the persistence implementation.

### Trade-offs

- The current implementation performs repository-backed neighbor reads at each expansion.
- Relationship confidence does not yet influence path ranking.
- All relationships are currently treated as equal-cost edges.

## Follow-up

PGE-006.5 will turn path traces into human-readable explanations and evidence chains. Future milestones may add weighted paths, pagination, query planning, and persisted graph indexes.
