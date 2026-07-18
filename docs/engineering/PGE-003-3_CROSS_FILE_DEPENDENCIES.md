# PGE-003.3 — Cross-file Dependency Resolution

## Status

Implemented on `feature/pge-003-3-cross-file-dependencies`.

## Purpose

PGE-003.3 extends Polaris from isolated-file analysis to deterministic Python project analysis. It resolves imports between repository modules and produces a repository-level dependency model without importing or executing repository code.

## API

```http
GET /api/v1/code-understanding/project?root=chief-of-staff/backend&ref=main&max_files=200
```

Parameters:

- `root`: optional repository subtree to analyze;
- `ref`: branch, tag, or commit reference;
- `max_files`: safety limit from 1 to 500 Python files.

## Output

The project analysis response includes:

- module and path inventory;
- internal dependency graph;
- reverse dependencies;
- import-level dependency records;
- external dependency names;
- unresolved relative imports;
- package summaries;
- entry modules with no inbound dependencies;
- leaf modules with no outbound internal dependencies;
- strongly connected dependency cycles;
- project metrics.

## Resolution rules

Polaris maps Python paths to dotted module names:

- `app/main.py` becomes `app.main`;
- `app/services/__init__.py` becomes `app.services`;
- relative imports are resolved from the importing module's package;
- `from package import module` first checks `package.module`, then `package`;
- unresolved absolute imports are reported as external dependencies.

## Safety and limits

- Source is parsed with Python's AST and is never executed.
- Only UTF-8 `.py` files are considered.
- `__pycache__` content is ignored.
- A truncated GitHub repository tree is rejected.
- The endpoint reads at most `max_files` files.
- The endpoint maximum is 500 files.
- Existing per-file source limits remain enforced by `PythonCodeAnalyzer`.

## Known boundaries

This milestone performs static module-level import resolution. It does not yet resolve:

- dynamic imports through `importlib`;
- imports assembled from strings;
- runtime path mutation;
- optional imports selected by environment;
- symbol usage across files;
- namespace packages without repository file evidence;
- dependencies in non-Python languages.

These boundaries are deliberate. Runtime behavior belongs in the future sandboxed-analysis milestone, while symbol-level impact analysis belongs in later PGE milestones.

## Definition of done

PGE-003.3 is complete when:

- project analysis is available through the API;
- absolute and relative internal imports resolve deterministically;
- reverse dependencies and cycles are generated;
- external dependencies are separated from internal dependencies;
- file-count and existing source-size limits are enforced;
- unit tests cover graphs, relative imports, cycles, roots, limits, and invalid syntax;
- CI passes.
