# ADR-004: Atlas Entity Engine

- Status: Proposed
- Date: 2026-07-19
- Milestone: PGE-006.1

## Context

Executive Memory stores and retrieves historical knowledge, but Polaris needs a stable domain language for people, projects, documents, decisions, systems, releases, and other organizational objects. Atlas requires typed entities before relationships and graph traversal can be implemented.

## Decision

Atlas will use a shared `AtlasEntity` model with:

- a stable identifier;
- a closed, extensible entity-type vocabulary;
- normalized names and tags;
- metadata owned by the entity;
- lifecycle status;
- creation and update timestamps;
- monotonic version numbers.

Entities are created and updated through `EntityFactory`, validated by `EntityValidator`, and persisted behind the `EntityRepository` contract. The first implementation is an in-memory repository with defensive copying.

## Consequences

### Positive

- All future Atlas nodes share a consistent identity model.
- Relationship and graph layers can depend on a small stable contract.
- Validation happens before knowledge enters the graph.
- Repository implementations can change without changing domain consumers.

### Trade-offs

- The initial entity vocabulary is deliberately constrained.
- Metadata remains schemaless until entity-specific schemas are introduced.
- The in-memory repository is not durable and is intended for domain verification only.

## Follow-up

PGE-006.2 will introduce typed relationships between Atlas entities. Persistent graph storage will be evaluated in a later Atlas milestone.
