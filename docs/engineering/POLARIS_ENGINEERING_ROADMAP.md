# Polaris Engineering Roadmap

Status: Active
Owner: Polaris Lab
Last updated: 2026-07-30

## Purpose

This roadmap is the engineering source of truth for Polaris. It records completed capabilities, near-term priorities, release targets, engineering standards, and the definition of done for future work.

Polaris is being developed as an AI-enabled operating system and Chief of Staff platform with a disciplined, evidence-first engineering process.

## Current Baseline

### Completed

- ARC-001 — Architecture baseline
- PGE-001 — GitHub Engine
- PGE-002 — Repository Intelligence
- PGE-003 — Code Understanding Engine v1
- PGE-003.1 — Configurable analysis limits
- PGE-003.2 — Large-file chunked analysis
- GitHub Actions backend test workflow
- Phase 1 Security Gate
- Phase 1.1 Tenant Isolation Hardening
- Phase 1.2 Integration Verification
- Phase 2 Database Gate
- Phase 2.1 Persistent Deployment Hardening

### In progress

- Phase 3A QuickBooks Production Adapter — live read-only QuickBooks Online adapter, company verification, resource/report reads, safe sync, and operator smoke-test runbook for Issue #61.

### Current engineering capabilities

Polaris can currently:

- inspect the approved GitHub repository;
- list branches and repository metadata;
- retrieve repository trees and file contents;
- search repository code;
- inspect commit history;
- parse Python source without executing it;
- identify imports, classes, functions, methods, constants, decorators, docstrings, signatures, and direct calls;
- produce deterministic plain-English module explanations;
- analyze large Python files in syntax-aware chunks;
- enforce configurable analysis limits with a hard safety ceiling;
- run backend, frontend, TypeScript, security, runtime, and database lifecycle checks in GitHub Actions;
- enforce Alembic schema lifecycle for staging and production startup;
- operate hosted staging/production on persistent PostgreSQL with generic public health responses.

## Product Direction

Polaris will evolve through five engineering stages:

1. Repository awareness
2. Code understanding
3. Cross-file architectural reasoning
4. Refactoring and impact analysis
5. Controlled engineering automation

The platform must remain explainable, reviewable, testable, and safe at every stage.

## Near-Term Priorities

### Phase 3A — QuickBooks Production Adapter and Read-Only Verification

Goal: connect Polaris safely to the live QuickBooks Online company for Mor Logistics through a tenant-bound, read-only adapter after the persistent PostgreSQL prerequisite.

Planned outcomes:

- Python-owned OAuth, encrypted credential storage, refresh-token rotation, and live Intuit HTTPS calls;
- company identity verification against `MOR LOGISTICS MANITOBA LIMITED` before accepting synchronized data;
- paginated reads for company, customers, vendors, accounts, invoices, payments, bills, purchases, and journal entries;
- report reads for Profit and Loss, Balance Sheet, Cash Flow, Aged Receivables, and Aged Payables;
- full and incremental read-only sync into Polaris financial cache;
- safe verification endpoint and connector health states;
- production smoke-test runbook and Issue #61 evidence checklist;
- no accounting writes.

Scope boundaries:

- do not implement Motive or modify Issue #62;
- do not implement Outlook;
- do not add QuickBooks accounting writes;
- do not migrate API versioning;
- do not commit production credentials or put them in CI.

### PGE-003.3 — Cross-file Dependency Resolution

Goal: understand how Python modules and symbols relate across the repository.

Planned outcomes:

- module import graph;
- reverse dependency lookup;
- symbol definition index;
- symbol reference lookup;
- cross-file call relationships where statically resolvable;
- dependency and impact API endpoints;
- deterministic repository-wide dependency reports.

Scope boundaries:

- static analysis only;
- no source execution;
- unresolved dynamic imports must be reported honestly;
- ambiguous references must not be presented as certain.

### PGE-004 — Refactoring Advisor

Goal: identify maintainability risks and recommend safe improvements.

Planned outcomes:

- oversized function detection;
- duplicated structure detection;
- dead-code candidates;
- circular dependency detection;
- high-coupling modules;
- refactoring proposals with evidence and risk notes.

### PGE-005 — Impact Analysis

Goal: estimate what may be affected before a code change is made.

Planned outcomes:

- affected modules;
- affected APIs;
- affected tests;
- dependency depth;
- risk classification;
- recommended validation plan.

### PGE-006 — Documentation Generator

Goal: generate and maintain engineering documentation from verified source facts.

Planned outcomes:

- module documentation;
- API catalogs;
- dependency reports;
- architecture diagrams;
- change summaries;
- synchronized Markdown documentation.

### PGE-009 — Sandboxed Runtime Analysis

Goal: add optional runtime evidence without weakening static-analysis safety.

Required safeguards:

- isolated container;
- no production secrets;
- restricted or disabled networking;
- read-only repository mount;
- CPU, memory, and time limits;
- temporary filesystem;
- explicit approval before execution;
- complete execution logs.

## Release Roadmap

### v0.5 — Intelligent Engineering Assistant

Exit criteria:

- PGE-003.3 complete;
- repository-wide dependency graph available;
- automated backend tests passing;
- architecture and API documentation updated;
- no unresolved critical defects.

### v0.6 — Self-Understanding Codebase

Exit criteria:

- PGE-004 complete;
- repository-wide code-quality findings available;
- documented false-positive handling;
- baseline technical-debt report generated.

### v0.7 — Refactoring and Impact Analysis

Exit criteria:

- PGE-005 complete;
- change-impact reports available before implementation;
- affected-test recommendations included;
- risk scoring documented and tested.

### v0.8 — Engineering Knowledge Graph

Exit criteria:

- persistent relationships between repositories, modules, symbols, APIs, tests, and engineering decisions;
- searchable engineering memory;
- traceable evidence for generated conclusions.

### v0.9 — Controlled Engineering Automation

Exit criteria:

- guarded change proposals;
- branch creation and pull-request workflow automation;
- mandatory CI and review gates;
- no direct uncontrolled writes to main.

### v1.0 — Polaris Chief of Staff Platform

Exit criteria:

- stable engineering, operational, and executive workflows;
- documented security model;
- versioned database lifecycle with tested recovery procedures;
- persistent production database verified across deploy/restart;
- production QuickBooks read-only verification completed for Issue #61;
- Motive and Outlook decisions completed or explicitly deferred;
- release checklist completed;
- production-readiness review approved.

## Engineering Workflow

Every work item follows this sequence:

1. Discover
2. Design
3. Build
4. Verify
5. Document
6. Review
7. Merge
8. Clean branches

No feature is complete merely because code exists.

## Definition of Done

A work item is complete only when all applicable conditions are met:

- implementation matches the approved scope;
- automated tests are added or updated;
- the full relevant test suite passes locally or in CI;
- security and failure behavior are considered;
- public interfaces are documented;
- architecture documentation is updated when needed;
- the pull request accurately describes the change;
- CI passes;
- the change is reviewed;
- the change is merged into main;
- obsolete local and remote branches are removed;
- main is clean and synchronized after merge.

## Quality Gates

Before merge:

- no failing CI checks;
- no unresolved critical review comments;
- no known secret committed to the repository;
- no unapproved production-side effect;
- backward compatibility considered;
- error handling covered;
- tests demonstrate the intended behavior.

Before release:

- release notes prepared;
- version and documentation aligned;
- rollback approach documented;
- critical workflows tested;
- known limitations recorded;
- repository state clean;
- hosted production storage is persistent and backed up;
- live integration smoke tests have operator evidence where required.

## Safety Principles

Polaris engineering follows these rules:

- evidence before assumption;
- least privilege;
- read-only by default;
- explicit approval before writes or execution;
- no source execution inside static-analysis engines;
- no production secrets in tests or documentation;
- deterministic analysis where practical;
- uncertainty must be reported rather than hidden;
- main must remain stable.

## Technical-Debt Priorities

Near-term quality work includes:

- complete Phase 3A QuickBooks production adapter and live operator verification;
- implement external production identity provider before broad rollout;
- expand backend coverage beyond the GitHub and code-understanding engines;
- add API endpoint tests;
- add frontend tests;
- add linting, formatting, and type-checking gates;
- review stale branches;
- improve release versioning;
- strengthen configuration validation;
- introduce structured logging and operational diagnostics.

## Work Classification

- ARC — Architecture
- PGE — Polaris GitHub and engineering intelligence
- INT — Integrations
- OPS — Operations
- INF — Infrastructure
- DOC — Documentation
- SEC — Security

## Decision Rule

When speed conflicts with safety, correctness, traceability, or maintainability, Polaris will choose the safer and more reviewable path unless the Builder explicitly approves a documented exception.
