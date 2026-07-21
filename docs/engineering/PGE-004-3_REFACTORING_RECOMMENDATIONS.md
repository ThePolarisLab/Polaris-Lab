# PGE-004.3 — Refactoring Recommendation Engine

## Status

Implementation in progress.

## Purpose

Convert deterministic complexity and code-smell findings into a prioritized, evidence-backed refactoring action plan.

## Delivered scope

- `PythonRefactoringAdvisor`
- configurable recommendation policy
- deterministic priority scoring
- grouping of repeated findings into one actionable recommendation
- structured evidence, confidence, source range, rationale, and rank
- `GET /api/v1/refactoring/recommendations`
- unit tests

## Guardrails

The engine does not rewrite source code, execute analyzed code, invent findings, or use hidden AI scoring. Recommendations are derived only from PGE-004.2 findings.

## Deferred

Automatic patch generation, repository-wide sequencing, effort estimation, and AI-authored explanations remain outside this milestone.

## Verification

```bash
cd chief-of-staff/backend
pytest tests/test_refactoring_advisor.py tests/test_refactoring_smells.py tests/test_refactoring_complexity.py
```
