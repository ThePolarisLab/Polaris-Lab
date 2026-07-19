# ADR-008: Atlas Explainability Engine

## Status

Accepted

## Context

The Graph Query Engine returns structured paths, but executive users need concise explanations that show what was connected, how it was connected, and which evidence supports the result.

## Decision

Atlas will use a deterministic Explainability Engine that converts a `GraphPath` into:

- a concise summary,
- a step-by-step narrative,
- structured evidence references,
- per-step confidence,
- and an overall path confidence.

The overall confidence is the minimum confidence among the path relationships. This conservative rule prevents a weak link from being hidden by stronger links elsewhere in the path.

Explanation output remains structured as well as human-readable so Athena and future interfaces can format it without re-running graph traversal.

## Consequences

### Positive

- Explanations are reproducible and auditable.
- Every narrative remains tied to graph entities and relationships.
- Consumers can display summaries, detailed steps, or evidence independently.
- Conservative confidence communicates the weakest evidential link.

### Trade-offs

- Natural-language output is template based rather than generative.
- Relationship vocabulary directly affects narrative readability.
- Rich source citations and Executive Memory evidence links require later integration.

## Scope

PGE-006.5 covers deterministic graph-path explanations. Release verification, package versioning, release notes, and final Atlas acceptance remain for PGE-006.6.
