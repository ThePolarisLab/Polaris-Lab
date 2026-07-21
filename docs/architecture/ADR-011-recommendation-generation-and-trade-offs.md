# ADR-011: Recommendation Generation and Explainable Trade-offs

- Status: Proposed
- Date: 2026-07-21
- Milestone: PGE-007.3

## Context

PGE-007.1 introduced a durable decision model and PGE-007.2 introduced deterministic evidence evaluation and option scoring. Polaris now needs a recommendation layer that can explain why one option leads, show where alternatives remain stronger, and refuse to manufacture certainty when evidence is weak or scores are tied.

## Decision

Introduce a storage-independent `DecisionRecommendationEngine` that consumes a `Decision` and its `DecisionEvaluationResult`.

The engine:

- uses explicit policy thresholds for minimum score, minimum margin, evidence sufficiency, and warning tolerance;
- preserves ties and narrow margins as `review_required` outcomes;
- reports missing evidence as `insufficient_evidence`;
- generates structured rationale and dimension-level trade-off comparisons;
- calculates bounded confidence from score strength, margin, evidence coverage, and visible warning penalties;
- never mutates, approves, rejects, or implements the source decision;
- never introduces hidden AI-generated scoring criteria.

## Consequences

Recommendations remain reproducible and auditable. Executive users receive a clear preferred option only when policy gates are satisfied, while uncertainty and competing strengths remain visible. Future natural-language or AI explanation layers may summarize these structures but must not alter the deterministic result.

## Follow-up

A later milestone may persist recommendation snapshots, integrate Atlas and Executive Memory evidence references, and add human approval workflows. Those capabilities must remain separate from deterministic recommendation generation.
