# ARC-001 — Polaris System Overview

**Status:** Complete  
**Repository:** `ThePolarisLab/Polaris-Lab`  
**Baseline date:** 2026-07-20

## Purpose

ARC-001 records the verified architectural baseline for Polaris and establishes the rule that major capabilities must have an explicit architectural home, test strategy, security boundary, and documentation impact.

## Current system

Polaris now contains two related implementation areas:

1. **Legacy Chief of Staff application** — a Python/FastAPI backend, React/Vite frontend, SQLite/SQLAlchemy persistence, operational dashboards, work context, memory, reasoning, missions, and GitHub integration.
2. **Current TypeScript intelligence platform** — Athena orchestration, Executive Memory, Atlas knowledge-graph capabilities, and Decision Intelligence domain services with deterministic contracts, repository abstractions, tests, ADRs, and release verification.

The repository is therefore a transitional modular platform rather than a single uniform runtime. New work must clearly identify whether it extends the legacy application, the TypeScript intelligence core, shared documentation, or an integration boundary.

## Verified capability layers

```text
Polaris Platform
├── Experience and operational application
│   ├── React/Vite presentation
│   └── FastAPI operational APIs
├── Athena orchestration
│   ├── request and context contracts
│   ├── intent classification and planning
│   └── replaceable service ports
├── Executive Memory
│   ├── scoped memory contracts
│   ├── lifecycle and retrieval
│   └── Athena adapter
├── Atlas knowledge platform
│   ├── Entity Engine
│   ├── Relationship Engine
│   ├── Knowledge Graph Core
│   ├── Graph Query Engine
│   └── Explainability Engine
├── Decision Intelligence
│   ├── typed decision model
│   ├── options, evidence, risks, and recommendations
│   └── repository contract and in-memory implementation
├── Engineering intelligence
│   ├── GitHub Engine
│   ├── Repository Intelligence
│   ├── Code Understanding
│   ├── Cross-file dependency analysis
│   └── Complexity Engine
└── Governance and evidence
    ├── ADRs
    ├── engineering roadmap
    ├── release notes and verification
    └── knowledge-base daily logs
```

## Architectural principles

- Domain logic should remain independent from transport and storage where practical.
- Repository interfaces should separate domain behavior from persistence choices.
- Static-analysis engines must not execute analyzed source code.
- External integrations require explicit configuration, bounded operations, error translation, and least privilege.
- Deterministic evidence is preferred before AI-generated interpretation.
- `main` remains stable; material work uses feature branches, pull requests, CI, review, and documented completion.

## Current architectural direction

Polaris will continue as a modular platform with bounded domains rather than prematurely splitting into distributed services. Runtime and persistence choices may differ by domain, but public contracts, ownership, tests, and integration boundaries must remain explicit.

## Completion statement

ARC-001 is complete when these baseline documents are merged. Future architectural changes must update this baseline or add an ADR rather than reopening ARC-001.