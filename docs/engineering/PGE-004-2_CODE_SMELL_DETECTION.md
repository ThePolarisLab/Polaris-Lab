# PGE-004.2 — Code Smell Detection

**Status:** In progress  
**Owner:** Polaris Lab  
**Started:** 2026-07-20

## Goal

Extend the deterministic Refactoring Advisor with explainable Python code-smell findings that are safe, testable, and suitable for later recommendation and repository-health layers.

## First implementation scope

The initial detector reports:

- long methods;
- deep nesting;
- long parameter lists;
- too many local variables;
- too many return paths;
- large classes;
- unexplained numeric literals (magic numbers).

Each finding includes its type, severity, confidence, source location, measurable evidence, and a deterministic recommendation.

## Deferred analysis

The following require repository-wide or data-flow evidence and remain deferred rather than being reported with weak confidence:

- duplicate-code detection;
- dead-code detection;
- feature envy;
- cross-module god-object analysis.

## Architecture

```text
GitHub repository file
        |
        v
GitHubClient safe text read
        |
        v
Python AST parse (no source execution)
        |
        +--> Complexity Engine metrics
        |
        +--> Code Smell rules
        |
        v
Structured evidence-backed findings
```

Implementation:

```text
chief-of-staff/backend/app/refactoring/smells.py
```

API:

```text
GET /api/v1/refactoring/smells?path=<python-file>&ref=<git-ref>
```

## Safety principles

- Source is parsed but never imported or executed.
- Findings are deterministic.
- Thresholds are explicit and validated.
- Unsupported repository-wide conclusions are deferred.
- Uncertainty is represented through confidence rather than hidden.

## Definition of done

- detector implementation complete;
- API endpoint available;
- unit tests cover clean and positive cases;
- invalid syntax and threshold failures are controlled;
- CI passes;
- documentation is current;
- pull request reviewed and merged into `main`.
