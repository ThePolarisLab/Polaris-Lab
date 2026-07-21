# ADR-012: Deterministic Refactoring Recommendation Engine

- Status: Proposed
- Date: 2026-07-21
- Milestone: PGE-004.3

## Context

PGE-004.1 measures Python complexity and PGE-004.2 reports local, evidence-backed code smells. Polaris now needs to turn those findings into an ordered action plan without introducing opaque scoring or automatic source modification.

## Decision

Introduce `PythonRefactoringAdvisor` as a deterministic layer over code-smell findings. It groups findings by target and recommended action, calculates priority from explicit severity weights, preserves source evidence and confidence, and returns a ranked plan.

The advisor exposes its policy and guardrails in output. It does not execute or rewrite source code and does not infer unsupported repository-wide problems.

## Consequences

Recommendation output is repeatable, explainable, and auditable. Priority policy can evolve without changing the underlying smell detector. Automatic patch generation and cross-file planning remain separate future concerns.
