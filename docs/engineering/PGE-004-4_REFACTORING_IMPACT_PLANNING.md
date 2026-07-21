# PGE-004.4 — Refactoring Impact Analysis and Execution Planning

## Purpose

PGE-004.4 turns PGE-004.3 recommendations into a deterministic, dependency-aware execution plan. It estimates the likely direction of benefit, effort, risk, complexity reduction, and technical-debt reduction without changing source code.

## Components

- `PlanningPolicy`: configurable integer weights and risk thresholds.
- `RefactoringExecutionPlanner`: consumes `PythonRefactoringAdvisor` output.
- Stable topological ordering: prerequisites always precede dependent work.
- Validation: missing prerequisites and circular dependencies fail explicitly.
- Explainability: each step includes evidence, rationale, confidence, dependencies, and impact estimates.

## API

```text
GET /api/v1/refactoring/execution-plan?path=app/example.py&ref=main
```

The endpoint returns a `GitHubOperationResult` containing:

- aggregate plan metrics;
- ordered execution steps;
- benefit, effort, and risk values;
- directional complexity and technical-debt reduction estimates;
- source recommendation metrics;
- safety guardrails.

## Determinism

For identical source and policy inputs, the planner returns identical ordering and estimates. Ordering is resolved by dependencies first, then priority, benefit, source line, and action text.

## Safety

The planner never executes analyzed source, writes patches, or modifies repository files. Its estimates are directional planning aids and are explicitly marked as such.

## Tests

Coverage includes:

- impact and priority calculation;
- deterministic execution ordering;
- prerequisite ordering;
- missing dependency rejection;
- circular dependency rejection;
- empty-plan behavior;
- invalid policy validation.
