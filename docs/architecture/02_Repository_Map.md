# ARC-001 — Verified Repository Map

**Status:** Complete  
**Baseline date:** 2026-07-20

## Major repository areas

```text
Polaris-Lab/
├── chief-of-staff/                 # legacy operational full-stack application
│   ├── backend/                    # FastAPI, SQLAlchemy, domain and integration modules
│   └── frontend/                   # React/Vite presentation
├── src/                            # current TypeScript intelligence platform
│   ├── athena/                     # orchestration and service ports
│   ├── memory/                     # Executive Memory
│   ├── atlas/                      # entities, relationships, graph, queries, explanations
│   └── decision/                   # Decision Intelligence domain model
├── tests/                          # TypeScript domain and release verification tests
├── docs/
│   ├── architecture/               # living architecture baseline and ADRs
│   ├── engineering/                # roadmap and milestone documentation
│   ├── releases/                   # release notes and verification records
│   └── knowledge-base/             # operational engineering history
├── .github/workflows/              # automated verification
├── package.json                    # TypeScript package and release scripts
└── CHANGELOG.md                    # release history
```

The exact repository tree will evolve. This map defines ownership boundaries rather than promising that every file path remains permanent.

## Domain ownership

### Athena

Athena is the orchestration entry point. It owns request interpretation, execution planning, service coordination, response construction, and telemetry contracts. Athena should depend on domain ports rather than concrete storage implementations.

### Executive Memory

Executive Memory owns scoped memory records, retrieval, ranking, lifecycle operations, ownership enforcement, and Athena memory integration.

### Atlas

Atlas owns knowledge representation and graph reasoning:

- typed entities;
- typed relationships;
- graph integrity;
- bounded traversal and shortest paths;
- evidence-backed explanations.

### Decision Intelligence

Decision Intelligence owns typed decisions, options, evidence, constraints, risks, recommendations, outcomes, lifecycle rules, and repository contracts.

### Engineering Intelligence

The engineering area owns repository access and deterministic source analysis:

- PGE-001 GitHub Engine;
- PGE-002 Repository Intelligence;
- PGE-003 Code Understanding;
- PGE-003.1 configurable limits;
- PGE-003.2 large-file chunking;
- PGE-003.3 cross-file dependencies;
- PGE-004.1 Complexity Engine.

Future code-smell detection and recommendation work should extend these verified analysis foundations instead of creating an unrelated analysis stack.

## Legacy application boundary

`chief-of-staff/` remains a verified application area with operational APIs, persistence, presentation, and integrations. New work must not assume its Python models or SQLite persistence are automatically shared with the TypeScript domains. Any cross-runtime integration requires an explicit contract and ADR when material.

## Test and CI boundary

Tests are part of each domain's definition of done. Release verification scripts and GitHub Actions are repository-wide quality gates. A milestone is not complete merely because implementation code exists.

## Documentation boundary

- Architecture documents describe current boundaries and enduring rules.
- ADRs explain important decisions and trade-offs.
- Engineering milestone documents describe implementation scope.
- Release notes describe shipped capability.
- Knowledge-base logs preserve chronological decisions and commitments.

## Maintenance rule

When a change introduces a domain, changes ownership, adds a persistence technology, changes a security boundary, or creates a new public integration, this map and the relevant ADR must be reviewed.