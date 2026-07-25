# ADR-010: Athena Reasoning Engine

- Status: Accepted
- Date: 2026-07-25
- Milestone: PR #60

## Context

Hermes now provides provider-neutral executive knowledge through its read model, projection engine, and query engine. Polaris needs a reasoning layer that converts that trusted knowledge into explainable and actionable executive insights without coupling Athena to connector implementations.

## Decision

Athena will use a deterministic, evidence-first reasoning engine composed of:

1. **Reasoning context** scoped to one organization and objective.
2. **Pluggable rules** that produce structured findings.
3. **Evidence evaluation** using strength, reliability, completeness, and coverage.
4. **Confidence assessment** with explicit reasons and missing-evidence conflicts.
5. **Priority assessment** using impact, urgency, and confidence.
6. **Recommendation policies** that may attach practical actions to findings.
7. **Executive insights** containing the finding, evidence, confidence, priority, explanation, and optional recommendation.

The core engine is intentionally storage-neutral and model-neutral. Hermes or another adapter supplies structured evidence; Athena does not query provider APIs directly.

## Guarantees

- Evidence from another organization is rejected.
- Duplicate evidence identifiers are rejected.
- Inputs are normalized and outputs are deterministically ordered.
- Missing evidence lowers confidence and is disclosed.
- A finding with no evidence cannot receive positive confidence.
- Recommendations remain separate policies rather than hidden engine behavior.

## Confidence model

For each evidence item:

`strength weight × reliability × completeness`

The average evidence score is multiplied by referenced-evidence coverage. Scores are clamped to the range 0–1 and classified as low, medium, or high.

This first model is deliberately transparent. Future statistical or learned confidence models may be added behind the same contract, but they must preserve traceability.

## Consequences

### Positive

- Athena conclusions are inspectable and testable.
- New domain rules can be added without changing the orchestration core.
- Dashboards, APIs, and briefings receive stable structured output.
- Organization isolation is enforced at the reasoning boundary.

### Trade-offs

- Rule authors must explicitly identify supporting evidence.
- The v1 confidence model does not infer causality.
- Conflict detection currently reports missing references; semantic contradictions are deferred.

## Deferred

- Temporal trend and causal reasoning
- Semantic contradiction detection
- Scenario simulation
- Learned ranking models
- Persistent reasoning traces
- Human approval and action execution

These belong in later Athena milestones and must not weaken evidence traceability.
