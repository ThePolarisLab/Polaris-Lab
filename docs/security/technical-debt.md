# Security Technical Debt

Status date: 2026-07-29

## Closed By Phase 2 Database Gate

The following Phase 1.1 database lifecycle debts are addressed by the Phase 2 branch:

| Item | Status |
|---|---|
| Alembic migrations for newly tenant-owned columns | Draft implementation in `phase2/database-gate` |
| Backfill existing persistent tenant-owned rows with organization IDs | Draft implementation in `phase2/database-gate` |
| Replace production `Base.metadata.create_all` startup behavior | Draft implementation in `phase2/database-gate` |

## Accepted Later-Phase Debt

| Item | Status | Later Gate |
|---|---|---|
| Production identity provider replacing local token bootstrap | Not started | Authentication rollout after Security Gate |
| Motive connector tenant-owned persistence | Not started | Motive Gate |
| Outlook connector tenant-owned persistence | Not started | Outlook Gate |
| API response/versioning standardization | Not started | API Versioning Gate |
| Deployment/runbook hardening beyond migration commands | Not started | Deployment Gate |
| Row-level tenant mapping utility for genuinely mixed-tenant legacy databases | Not started | Operational data migration tooling |

## Tenant Persistence Rules

- Do not add connector persistence without an `organization_id` boundary.
- Do not query tenant-owned data without a principal-derived organization filter.
- Do not use `settings.organization_slug` or `POLARIS_ORGANIZATION_SLUG` as an authorization, credential, cache, or migration backfill key.
- Do not expose unscoped retained event payloads through authenticated tenant APIs.
- Do not add tenant-owned schema changes without an Alembic revision and downgrade safety decision.

## Verification Debt

Local verification in the Codex desktop sandbox is blocked by Windows `CreateProcessAsUserW failed: 5 (Access is denied.)`. Phase 2 verification must rely on GitHub Actions until local execution is restored.
