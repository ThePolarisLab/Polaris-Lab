# PGE-007.3 — Recommendation Generation and Explainable Trade-off Analysis

## Status

Implementation candidate under review.

## Purpose

Convert deterministic PGE-007.2 option evaluations into bounded, explainable recommendations without approving decisions or hiding ambiguity.

## Delivered capability

- deterministic recommendation policy;
- minimum score and score-margin gates;
- evidence sufficiency checks;
- tie preservation;
- warning-aware confidence calculation;
- structured rationale;
- dimension-by-dimension trade-off comparison;
- explicit `recommended`, `review_required`, and `insufficient_evidence` outcomes;
- immutable analysis that does not mutate the source decision;
- unit tests for decisive recommendations, ties, missing evidence, invalid policies, and mismatched evaluations.

## Guardrails

The engine does not approve, reject, implement, or otherwise mutate a decision. It does not introduce hidden AI criteria. A recommendation is emitted only when deterministic evidence and policy gates support it. Ties, narrow margins, insufficient evidence, and unresolved warnings remain visible.

## Verification

```bash
npm test -- --runInBand tests/decision-intelligence/DecisionRecommendationEngine.test.ts
npm run verify:release
```

## Completion criteria

- TypeScript tests pass;
- release verification passes;
- ADR-011 is accepted;
- PR is reviewed and merged into `main`;
- feature branch is deleted after local synchronization.
