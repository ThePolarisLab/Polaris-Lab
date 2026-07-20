# ADR-009: Decision Model Core

- Status: Proposed
- Date: 2026-07-20
- Milestone: PGE-007.1

## Context

Polaris v0.7 requires a durable, explainable representation of executive decisions. Executive Memory preserves why prior choices were made, while Atlas provides entities, relationships, paths, and evidence narratives. Decision Intelligence needs a domain model that can combine those capabilities without coupling decision logic to a specific database or scoring algorithm.

## Decision

Introduce a typed Decision Model Core containing decisions, options, evidence, constraints, risks, recommendations, outcomes, confidence, lifecycle status, and versioning.

The initial implementation uses:

- explicit component identifiers and validated cross-references;
- confidence values constrained to the inclusive range 0–1;
- immutable defensive copies at repository boundaries;
- a repository abstraction with an in-memory implementation;
- lifecycle states from draft through implementation or supersession;
- metadata records for future Atlas and Executive Memory references.

## Consequences

The model is storage-independent and ready for future evaluation, recommendation, explanation, and persistence services. It intentionally does not define option-scoring weights or automated approval policy; those belong to later PGE-007 milestones.

## Follow-up

PGE-007.2 will introduce evidence evaluation and option scoring. PGE-007.3 will add recommendation generation and explainable trade-off analysis.
