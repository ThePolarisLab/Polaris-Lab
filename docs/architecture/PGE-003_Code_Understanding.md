# PGE-003 — Code Understanding Engine

## Status

Implementation candidate for review.

## Purpose

PGE-003 converts Python source code into deterministic structural intelligence. It builds on PGE-002, which safely retrieves repository files, and uses Python's standard abstract syntax tree parser rather than an external AI service.

## Capabilities

PGE-003 v1 extracts:

- module and object docstrings;
- imports and aliases;
- module-level functions;
- classes, inheritance and methods;
- parameters, return annotations and decorators;
- uppercase module constants;
- direct function and method calls;
- basic source metrics;
- a deterministic plain-English module explanation.

## API

### Analyze a Python file

`GET /api/v1/code-understanding/analyze`

Parameters:

- `path`: repository path to a Python file;
- `ref`: branch, tag or commit reference, defaulting to `main`.

### Explain a Python file

`GET /api/v1/code-understanding/explain`

Returns a concise structural explanation generated from the analysis.

## Safety and limits

- Source retrieval remains restricted by the PGE-001 repository allowlist.
- PGE-003 v1 accepts `.py` files only.
- Analysis is limited to 1 MB of UTF-8 source.
- Syntax errors are returned as controlled engine errors.
- The analyzer does not execute imported or analyzed code.
- No write access is required for analysis.

## Architecture

```text
API request
    |
    v
Code Understanding API
    |
    +--> PGE-002 GitHubClient.read_file()
    |
    v
PythonCodeAnalyzer
    |
    +--> ast.parse()
    +--> structure extraction
    +--> call graph extraction
    +--> deterministic explanation
```

## Current boundaries

PGE-003 v1 does not yet provide cross-file symbol resolution, repository-wide dependency graphs, duplicate detection, dead-code detection or AI-generated semantic interpretation. Those capabilities should be added only after the deterministic foundation is verified.

## Verification

Unit tests cover structural extraction, imports, constants, class and method analysis, direct calls, explanations, syntax errors and source-size enforcement. The existing backend GitHub Actions workflow runs the complete backend test suite for pull requests.
