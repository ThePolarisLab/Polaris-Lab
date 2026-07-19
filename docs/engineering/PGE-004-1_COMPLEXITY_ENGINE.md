# PGE-004.1 — Complexity Engine

## Status

Implemented on `feature/pge-004-1-complexity-engine`.

## Purpose

PGE-004.1 gives Polaris deterministic, explainable maintainability signals for Python functions and methods. The engine parses source with Python's standard `ast` module and never executes repository code.

## Metrics

For every function and method, Polaris reports:

- cyclomatic complexity, beginning at 1;
- maximum control-flow nesting;
- lines of code;
- parameter and local-variable counts;
- branches, loops, returns, try blocks, and match statements;
- asynchronous constructs;
- an Excellent, Good, Moderate, High, or Critical rating.

Complexity increases for conditionals, loops, exception handlers, match cases, boolean decision points, and comprehensions. Nested function bodies are measured independently rather than being charged to their parent callable.

## Deterministic recommendations

The first recommendation engine deliberately uses transparent rules:

- high complexity → Extract Method;
- excessive nesting → Guard Clauses;
- excessive parameters → Parameter Object;
- excessive length → Split Function.

Each recommendation includes a confidence value. These values express confidence that the measured signal supports the recommendation; they are not guarantees that a refactor is appropriate without human review.

## API

```http
GET /api/v1/refactoring/complexity?path=<python-file>&ref=<git-ref>
```

The endpoint reads the requested repository file through the existing GitHub Engine and returns a `GitHubOperationResult` containing file metrics, thresholds, callable details, and recommendations.

## Defaults

- Moderate complexity: 11
- High complexity: 16
- Critical complexity: 21
- Maximum preferred nesting: 4
- Maximum preferred parameters: 5
- Maximum preferred callable length: 50 lines

Thresholds are represented by `ComplexityThresholds` and can be overridden by internal callers.

## Design decision

The engine is deterministic and AST-based before any LLM enhancement. This keeps analysis fast, testable, explainable, and safe. Future refactoring advice can enrich these signals, but should preserve the measured evidence in its output.

## Extension path

PGE-004.2 can consume these metrics for code-smell detection. PGE-004.3 can combine smells and dependency information into richer recommendations. PGE-004.4 can aggregate callable results into repository health reports and trends.
