# Polaris Technical Debt Register

**Baseline date:** 2026-07-20

This register records verified or strongly evidenced improvement opportunities. It is not a promise that every item must be fixed immediately.

## TD-001 — Dual-runtime architecture needs explicit integration contracts

**Area:** Platform architecture  
**Priority:** High  
**Status:** Open  
**Observation:** The repository contains a legacy Python/FastAPI operational application and a newer TypeScript intelligence platform.  
**Risk:** Domain data, ownership, deployment, and integration assumptions may diverge.  
**Recommendation:** Define explicit cross-runtime contracts before sharing persistence or runtime state.

## TD-002 — Persistence strategy is intentionally incomplete

**Area:** Data architecture  
**Priority:** High before production persistence  
**Status:** Accepted  
**Observation:** New TypeScript domains use repository contracts and in-memory implementations.  
**Risk:** Durability, concurrency, migrations, recovery, and multi-instance behavior are not yet established.  
**Recommendation:** Select persistent adapters through domain-specific ADRs and preserve repository contracts.

## TD-003 — Authentication and authorization require a unified model

**Area:** Security  
**Priority:** High  
**Status:** Open  
**Observation:** Domain ownership safeguards exist in selected components, but a repository-wide identity and authorization model is not yet documented.  
**Risk:** Inconsistent access control across operational, memory, graph, decision, and engineering capabilities.  
**Recommendation:** Define principals, scopes, tenant boundaries, service identities, and audit requirements before broad deployment.

## TD-004 — Legacy application configuration and migrations need hardening

**Area:** Legacy application  
**Priority:** Medium  
**Status:** Open  
**Observation:** Earlier architecture inspection identified embedded local configuration and startup-time schema creation.  
**Risk:** Environment portability and controlled schema evolution remain limited.  
**Recommendation:** Confirm current state, externalize configuration, and introduce versioned migrations before production use.

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

## Review policy

Each item must retain a status: `open`, `accepted`, `in progress`, `resolved`, or `deferred`. Priorities should be reassessed when the affected area changes. Resolved items should remain in history or move to a dated archive rather than disappearing without explanation.