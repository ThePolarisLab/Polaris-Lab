# Security Technical Debt

Status date: 2026-07-30

## Closed By Completed Gates

| Item | Status |
|---|---|
| Alembic migrations for newly tenant-owned columns | Closed by merged Phase 2 Database Gate |
| Backfill existing persistent tenant-owned rows with organization IDs | Closed by merged Phase 2 Database Gate and Phase 2.1 no-organization bootstrap recovery |
| Replace production `Base.metadata.create_all` startup behavior | Closed by merged Phase 2 Database Gate |
| Public root and health metadata exposure | Closed by merged Phase 2.1 Persistent Deployment Hardening |
| Hosted `/tmp` SQLite production blocker | Closed by merged Phase 2.1 Persistent Deployment Hardening and Render PostgreSQL cutover guidance |
| QuickBooks production runtime ownership ambiguity | Addressed in Phase 3A ADR-026 |
| QuickBooks frontend OAuth authorization link without bearer/org headers | Addressed in Phase 3A with authenticated `authorize-url` endpoint |

## Accepted Later-Phase Debt

| Item | Status | Later Gate |
|---|---|---|
| Production identity provider replacing local token bootstrap | Not started | Authentication rollout after Security Gate |
| Motive connector tenant-owned persistence | Not started | Motive Gate / Issue #62 |
| Outlook connector tenant-owned persistence | Not started | Outlook Gate |
| API response/versioning standardization | Not started | API Versioning Gate |
| Broad deployment/runbook hardening beyond migration and QuickBooks operator commands | Not started | Deployment Gate |
| Row-level tenant mapping utility for genuinely mixed-tenant legacy databases | Not started | Operational data migration tooling |

## Tenant Persistence Rules

- Do not add connector persistence without an `organization_id` boundary.
- Do not query tenant-owned data without a principal-derived organization filter.
- Do not use `settings.organization_slug` or `POLARIS_ORGANIZATION_SLUG` as an authorization, credential, cache, or migration backfill key.
- Do not expose unscoped retained event payloads through authenticated tenant APIs.
- Do not add tenant-owned schema changes without an Alembic revision and downgrade safety decision.
- Do not add production connector token ownership in a second runtime without an ADR and rotation-race analysis.

## Verification Debt

Local verification in the Codex desktop sandbox is blocked by Windows `CreateProcessAsUserW failed: 5 (Access is denied.)`. Phase 3A verification relies on GitHub Actions until local execution is restored. Production QuickBooks smoke testing remains a manual protected operator procedure and must not run in broad CI.
