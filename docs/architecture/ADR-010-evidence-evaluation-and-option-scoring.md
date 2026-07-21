# ADR-010: Evidence Evaluation and Option Scoring

- Status: Proposed
- Date: 2026-07-21
- Milestone: PGE-007.2

## Context

PGE-007.1 introduced typed decisions, options, evidence, constraints, and risks, but intentionally left scoring policy undefined. Decision Intelligence now needs a reproducible way to compare options while preserving explainability and Builder authority.

## Decision

Introduce a deterministic `DecisionEvaluator` that:

- evaluates only evidence explicitly linked to an option;
- combines evidence direction, relevance, confidence, and quality;
- scores benefits, drawbacks, linked risks, and mandatory constraints;
- normalizes component scores to `0..1`;
- uses configurable weights that must be non-negative and sum to `1`;
- returns ranked options with score breakdowns, warnings, and evidence-level explanations;
- does not create recommendations, approvals, or outcomes.

The evaluator remains storage-independent and accepts the PGE-007.1 `Decision` aggregate directly.

## Consequences

### Positive

- Identical inputs and weights produce identical rankings.
- Every score can be traced to declared inputs.
- Missing evidence, critical risks, mandatory constraints, and ties remain visible.
- Future recommendation generation can consume a stable scoring contract.

### Costs and limitations

- Count-based benefit and drawback scoring is intentionally simple.
- Evidence direction currently depends on explicit metadata and defaults linked evidence to supportive.
- Correlated evidence is not yet de-duplicated.
- Weight selection remains a governance choice rather than an automatically learned policy.

## Guardrail

A high option score is analytical evidence, not authorization. PGE-007.3 may generate a recommendation, but final decision authority remains outside the evaluator.

## Follow-up

PGE-007.3 will convert evaluation results into explainable recommendations and trade-off analysis. Later work may add criterion-specific scoring, evidence provenance validation, sensitivity analysis, and persistence.
