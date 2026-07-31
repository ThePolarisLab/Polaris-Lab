# Polaris Technical Debt Register

**Baseline date:** 2026-07-20  
**Last updated:** 2026-07-30

This register records verified or strongly evidenced improvement opportunities. It is not a promise that every item must be fixed immediately.

## TD-001 — Dual-runtime architecture needs explicit integration contracts

**Area:** Platform architecture  
**Priority:** High  
**Status:** Resolved for QuickBooks Phase 3A; still applies to future cross-runtime integrations  
**Observation:** The repository contains a Python/FastAPI operational application and a TypeScript intelligence platform.  
**Risk:** Domain data, ownership, deployment, and integration assumptions may diverge.  
**Resolution:** ADR-026 assigns production QuickBooks OAuth, credential persistence, token rotation, live HTTPS calls, and sync to Python. Hermes remains the connector/evidence/checkpoint contract and mocked/sandbox test harness for Phase 3A.  
**Recommendation:** Future connectors must define runtime ownership before sharing persistence or runtime state.

## TD-002 — Persistence strategy is intentionally incomplete

**Area:** Data architecture  
**Priority:** High before production persistence  
**Status:** Accepted  
**Observation:** New TypeScript domains use repository contracts and in-memory implementations.  
**Risk:** Durability, concurrency, migrations, recovery, and multi-instance behavior are not yet established.  
**Recommendation:** Select persistent adapters through domain-specific ADRs and preserve repository contracts.

## TD-003 — External identity provider remains future work

**Area:** Security  
**Priority:** High before broad external rollout  
**Status:** Accepted after Phase 3B  
**Observation:** Phase 3B replaces the production login blocker with one-time first-admin bootstrap and internal-launch email/password sessions, while keeping `/api/v1/auth/local/token` disabled in production/staging.  
**Risk:** Internal password sessions are suitable for controlled launch but do not provide enterprise SSO, MFA, delegated identity lifecycle, or centralized offboarding.  
**Recommendation:** Select and integrate the production identity provider before broad human-user rollout. Keep Phase 3B sessions as an internal bridge, not the final identity strategy.

## TD-004 — Legacy application configuration and migrations need hardening

**Area:** Legacy application  
**Priority:** Medium  
**Status:** Resolved by Phase 2 Database Gate and Phase 2.1 deployment hardening  
**Observation:** Earlier architecture inspection identified embedded local configuration, startup-time schema creation, and temporary SQLite production deployment risk.  
**Resolution:** Phase 2 introduced Alembic migrations, adoption validation, migration startup enforcement, and backup/rollback documentation. Phase 2.1 moved production deployment guidance to persistent PostgreSQL, migration-before-startup, and generic public health responses.

## TD-005 — Architecture and ADR indexing is fragmented

**Area:** Documentation  
**Priority:** Medium  
**Status:** Open  
**Observation:** Architecture and release work introduced multiple ADRs across milestones.  
**Risk:** Numbering, supersession, and discoverability may become inconsistent.  
**Recommendation:** Maintain a canonical ADR index with status, date, domain, and supersession links.

## TD-006 — CI quality gates remain uneven

**Area:** Engineering quality  
**Priority:** Medium  
**Status:** In progress  
**Observation:** Automated test workflows exist and TypeScript release verification has expanded, but linting, formatting, type checking, coverage expectations, and legacy application checks are not yet uniformly enforced.  
**Risk:** Quality may vary by runtime and domain.  
**Recommendation:** Establish repository-wide required checks with domain-specific test jobs.

## TD-007 — Operational observability is not yet standardized

**Area:** Operations  
**Priority:** Medium  
**Status:** Open  
**Observation:** Domain logic and telemetry contracts exist, but structured logs, metrics, traces, retention, and incident diagnostics are not defined repository-wide.  
**Risk:** Production failures may be difficult to diagnose.  
**Recommendation:** Define an observability standard before production deployment.

## TD-008 — Static-analysis false-positive governance needs expansion

**Area:** Engineering intelligence  
**Priority:** Medium for PGE-004.2 and later  
**Status:** Open  
**Observation:** Deterministic analysis foundations exist, including dependency and complexity analysis.  
**Risk:** Code-smell and recommendation features may overstate ambiguous findings.  
**Recommendation:** Add evidence levels, suppression mechanisms, confidence rules, and documented false-positive handling.

## TD-009 — Release and branch lifecycle should be automated further

**Area:** Repository operations  
**Priority:** Low  
**Status:** Open  
**Observation:** Feature branches are manually cleaned after merge and release evidence is maintained through disciplined workflow.  
**Risk:** Stale branches and inconsistent release housekeeping may recur.  
**Recommendation:** Enable safe automatic branch deletion and standard release checklists where repository settings permit.

## TD-010 — Knowledge-base summaries can drift from source documents

**Area:** Documentation governance  
**Priority:** Medium  
**Status:** Open  
**Observation:** Daily logs summarize repository state while roadmaps, ADRs, and release notes serve different source-of-truth purposes.  
**Risk:** Chronological summaries may become inconsistent with authoritative documents.  
**Recommendation:** Treat daily logs as historical records and update canonical roadmap or architecture documents separately when status changes.

## TD-011 — QuickBooks production smoke test requires live operator evidence

**Area:** Integrations  
**Priority:** High before closing Issue #61  
**Status:** Open until production verification is complete  
**Observation:** CI must use mocks/sandbox and cannot hold production Intuit credentials.  
**Risk:** Implementation can pass CI before the live company is authorized and verified.  
**Recommendation:** Keep Issue #61 open until the runbook checklist is completed against `MOR LOGISTICS MANITOBA LIMITED` with operator evidence.

## Review policy

Each item must retain a status: `open`, `accepted`, `in progress`, `resolved`, or `deferred`. Priorities should be reassessed when the affected area changes. Resolved items should remain in history or move to a dated archive rather than disappearing without explanation.