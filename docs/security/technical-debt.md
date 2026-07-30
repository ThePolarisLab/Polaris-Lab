# Security Technical Debt

Status date: 2026-07-29

## Accepted Later-Phase Debt

The following items are intentionally not solved in Phase 1.1 because they belong to later gates or would broaden the security-only milestone.

| Item | Status | Later Gate |
|---|---|---|
| Alembic migrations for newly tenant-owned columns | Not started | Database Gate |
| Backfill existing persistent tenant-owned rows with organization IDs | Not started | Database Gate |
| Replace `Base.metadata.create_all` startup behavior | Not started | Database Gate |
| Production identity provider replacing local token bootstrap | Not started | Authentication rollout after Security Gate |
| Motive connector tenant-owned persistence | Not started | Motive Gate |
| Outlook connector tenant-owned persistence | Not started | Outlook Gate |
| API response/versioning standardization | Not started | API Versioning Gate |
| Deployment/runbook hardening | Not started | Deployment Gate |

## Phase 1.1 Rules

- Do not add connector persistence without an `organization_id` boundary.
- Do not query tenant-owned data without a principal-derived organization filter.
- Do not use `settings.organization_slug` or `POLARIS_ORGANIZATION_SLUG` as an authorization, credential, or cache key.
- Do not expose unscoped retained event payloads through authenticated tenant APIs.

## Verification Debt

Local verification in the Codex desktop sandbox is blocked by Windows `CreateProcessAsUserW failed: 5 (Access is denied.)`. Phase 1.1 verification must therefore rely on GitHub Actions until local execution is restored.
