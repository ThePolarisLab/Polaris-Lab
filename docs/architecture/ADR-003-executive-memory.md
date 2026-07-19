# ADR-003: Executive Memory as a Ranked, Scoped Repository

- Status: Accepted
- Date: 2026-07-19
- Release: Polaris v0.5.0

## Context

Athena Core can orchestrate a request and persist a decision through the `MemoryService` port, but v0.4.0 does not define durable memory records, retrieval rules, or ranking behavior. Polaris needs an explicit memory boundary before adding databases, embeddings, or a knowledge graph.

## Decision

Executive Memory is implemented as a domain service over a replaceable `MemoryRepository`.

A memory record contains:

- a stable identifier and memory kind;
- user, project, and organization scope;
- title, content, tags, and optional metadata;
- creation and update timestamps;
- normalized importance from 0 to 1.

Retrieval is deterministic in v0.5.0. Candidate records are filtered by scope and ranked using:

- 55% lexical relevance;
- 25% recency decay;
- 20% stored importance.

The default in-memory repository exists for deterministic tests and local development. Persistent database and vector-search adapters can be added without changing Athena's orchestration contract.

## Consequences

### Positive

- Memory behavior is testable without infrastructure.
- User and organizational boundaries are explicit.
- Ranking is explainable and reproducible.
- Persistence technology remains replaceable.
- Athena continues to depend only on the `MemoryService` port.

### Trade-offs

- Lexical scoring does not capture semantic similarity.
- In-memory storage is not durable across processes.
- Importance is policy-driven and may need calibration.

## Guardrails

- A query must always include `userId`.
- Repository implementations must enforce user scope.
- Scores and importance values must remain within 0 and 1.
- Memory adapters must not expose repository-specific behavior to Athena Core.
- Semantic retrieval may augment, but must not silently replace, explainable scoring without a future ADR.
