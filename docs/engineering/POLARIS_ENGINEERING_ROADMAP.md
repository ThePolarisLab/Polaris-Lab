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
- Phase 3A QuickBooks Production Adapter implementation

### In progress

- Phase 3B Production Authentication Bootstrap — first-admin onboarding, password sessions, refresh rotation, deployed frontend login, and operator runbook needed before live QuickBooks OAuth verification.

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
- operate hosted staging/production on persistent PostgreSQL with generic public health responses;
- provide a tenant-bound QuickBooks production adapter implementation awaiting authenticated live operator verification.

## Product Direction

Polaris will evolve through five engineering stages:

1. Repository awareness
2. Code understanding
3. Cross-file architectural reasoning
4. Refactoring and impact analysis
5. Controlled engineering automation

The platform must remain explainable, reviewable, testable, and safe at every stage.

## Near-Term Priorities

### Phase 3B — Production Authentication Bootstrap

Goal: unblock internal production use and live QuickBooks verification without weakening the Security Gate or enabling development local tokens in production.

Planned outcomes:

- one-time bootstrap for `org-mor-logistics` and `mor-admin` using Render-managed admin email and strong bootstrap secret;
- bcrypt password credential storage;
- signed short-lived access tokens;
- hashed refresh tokens with rotation and replay rejection;
- logout/session revocation;
- login rate limiting;
- deployed frontend email/password login and first-admin bootstrap screen;
- production auth operator runbook and route matrix updates.

Scope boundaries:

- do not set `POLARIS_ENV=development` in production;
- do not re-enable `/api/v1/auth/local/token` in production/staging;
- do not implement Motive or Outlook;
- do not start QuickBooks OAuth automatically;
- do not close Issue #61 before live operator evidence.

### Phase 3A Follow-through — QuickBooks Live Operator Verification

Goal: connect Polaris safely to the live QuickBooks Online company for Mor Logistics through the merged tenant-bound, read-only adapter after production authentication works.

Required outcomes:

- production admin login works;
- QuickBooks OAuth is initiated by an authenticated owner with `connector.write`;
- company identity verifies against `MOR LOGISTICS MANITOBA LIMITED`;
- read-only resource/report verification completes;
- full and incremental sync evidence is recorded;
- no accounting writes occur;
- Issue #61 checklist is updated only with live operator evidence.

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

### v1.0 — Polaris Chief of Staff Platform

Exit criteria:

- stable engineering, operational, and executive workflows;
- documented security model;
- versioned database lifecycle with tested recovery procedures;
- persistent production database verified across deploy/restart;
- production authentication bootstrap complete and external IdP decision documented;
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
- no unreviewed critical or high security findings;
- no undocumented public API changes;
- no production secrets in source control;
- no tenant-owned persistence without migration and tenant-isolation review.