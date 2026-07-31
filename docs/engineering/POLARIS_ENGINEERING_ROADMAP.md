# Polaris Engineering Roadmap

Status: Active
Owner: Polaris Lab
Last updated: 2026-07-31

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
- Phase 3B Production Authentication Bootstrap core implementation

### In progress

- Phase 3A follow-through — QuickBooks live operator verification after the QBO sync-history hotfix is merged and deployed.
- Phase 3B.1 Production Hardening Cleanup — schema drift audit, adoption inventory guardrail, dead-code cleanup, and v1.0 scope re-baseline.

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
- run backend, frontend, TypeScript, security, runtime, QuickBooks, and database lifecycle checks in GitHub Actions;
- enforce Alembic schema lifecycle for staging and production startup;
- operate hosted staging/production on persistent PostgreSQL with generic public health responses;
- authenticate the first Mor Logistics production owner through the hosted frontend;
- provide a tenant-bound QuickBooks production adapter implementation awaiting final read-only sync evidence.

## Product Direction

Polaris will evolve through five engineering stages:

1. Repository awareness
2. Code understanding
3. Cross-file architectural reasoning
4. Refactoring and impact analysis
5. Controlled engineering automation

The platform must remain explainable, reviewable, testable, and safe at every stage.

## Near-Term Priorities

### Phase 3B.1 — Production Hardening Cleanup

Goal: remove small but meaningful production-readiness risks before declaring the QuickBooks path complete.

Planned outcomes:

- schema adoption inventory aligned with current financial cache SQLAlchemy models;
- regression test that catches future financial-cache model/adoption-inventory drift;
- documented production schema drift audit procedure;
- dead frontend backup file removed from `src`;
- v1.0 punch list updated with the current 86-89% readiness band and an explicit narrow-vs-broad v1.0 decision.

Scope boundaries:

- do not change auth, OAuth, refresh, frontend retry, or QuickBooks permissions;
- do not implement Motive or Outlook;
- do not change deployment infrastructure;
- do not merge the QBO sync-history hotfix without human review.

### Phase 3A Follow-through — QuickBooks Live Operator Verification

Goal: connect Polaris safely to the live QuickBooks Online company for Mor Logistics through the merged tenant-bound, read-only adapter after production authentication works and the sync-history hotfix is deployed.

Required outcomes:

- production admin login works;
- QuickBooks OAuth is initiated by an authenticated owner with `connector.write`;
- company identity verifies against `MOR LOGISTICS MANITOBA LIMITED`;
- read-only resource/report verification completes;
- full and incremental sync evidence is recorded;
- no accounting writes occur;
- Issue #61 checklist is updated only with live operator evidence.

### External Identity Decision

Goal: decide whether the internal production auth bootstrap is sufficient for internal v1.0 or whether external IdP integration is required before the release label.

Decision options:

- internal v1.0: ship with production bootstrap/password sessions for controlled Mor Logistics use, defer external IdP to v1.1;
- broader v1.0: require external IdP before production-ready approval.

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
- production-readiness review approved;
- repository visibility reviewed and set to private unless stakeholders explicitly approve public visibility.

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
- no tenant-owned persistence without migration and tenant-isolation review;
- no model/adoption-inventory drift for tables touched by the change.
