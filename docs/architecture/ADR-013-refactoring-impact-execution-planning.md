# ADR-013: Deterministic Refactoring Impact and Execution Planning

- Status: Accepted
- Date: 2026-07-21
- Milestone: PGE-004.4

## Context

PGE-004.1 measures complexity, PGE-004.2 detects code smells, and PGE-004.3 converts findings into prioritized recommendations. Polaris still needs a safe way to estimate impact, expose dependencies, and order recommended work without automatically rewriting source code.

## Decision

Polaris will provide a deterministic `RefactoringExecutionPlanner` that consumes the existing recommendation engine output and produces:

- dependency-aware execution order;
- directional benefit, effort, risk, complexity-reduction, and technical-debt estimates;
- evidence and rationale for every step;
- explicit guardrails confirming that source is neither executed nor modified.

Ordering uses a stable topological sort. Missing prerequisites and dependency cycles are rejected with explicit errors. Estimates are policy-driven and directional rather than predictive guarantees.

## Consequences

### Positive

- Recommendations become actionable implementation plans.
- Ordering remains repeatable and explainable.
- Circular and missing dependencies fail safely.
- Athena can later orchestrate a stable planning interface.

### Trade-offs

- Impact estimates are heuristics, not measured post-refactoring outcomes.
- The dependency catalogue must be expanded as new recommendation types are introduced.
- The planner does not generate or apply patches.

## API

`GET /api/v1/refactoring/execution-plan?path=<python-file>&ref=<git-ref>`

## Guardrails

The planner is deterministic, does not execute analyzed source, does not modify source, and labels all impact estimates as directional.
