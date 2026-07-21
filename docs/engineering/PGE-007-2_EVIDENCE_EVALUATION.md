# PGE-007.2 — Evidence Evaluation and Option Scoring

## Status

Implementation candidate under review.

## Purpose

PGE-007.2 extends the Decision Model Core with deterministic evaluation of linked evidence and explainable option scoring. It ranks options without automatically approving or recommending a decision.

## Delivered capabilities

- validates configurable scoring weights;
- evaluates linked evidence by direction, relevance, confidence, and quality;
- scores benefits, drawbacks, risks, and mandatory constraints;
- normalizes all scoring dimensions to the range `0..1`;
- ranks options deterministically;
- reports ties and missing-evidence conditions;
- returns structured score breakdowns, evidence assessments, explanations, and warnings;
- supports fixed clocks for reproducible tests.

## Default weights

| Dimension | Weight |
| --- | ---: |
| Evidence | 0.40 |
| Benefits | 0.15 |
| Drawbacks | 0.10 |
| Risks | 0.20 |
| Constraints | 0.15 |

Weights must be finite, non-negative, and sum to `1`.

## Evidence metadata

Evidence may optionally contain:

```ts
metadata: {
  relevance: 0.9,
  quality: 0.8,
  optionDirections: {
    "option-id": "supports" | "opposes" | "neutral"
  }
}
```

Absent direction metadata defaults to `supports` for linked evidence. This is explicit, deterministic behavior and may be tightened in a later evidence-ingestion milestone.

## Guardrails

- The evaluator does not mutate decisions.
- It does not create a recommendation or approval.
- It does not use an LLM or hidden scoring criteria.
- It reports incomplete evidence and ties instead of inventing certainty.
- PGE-007.3 remains responsible for recommendation generation and trade-off narratives.

## Verification

```bash
npm test -- --runInBand tests/decision-intelligence/DecisionEvaluator.test.ts
npm run verify:release
```
