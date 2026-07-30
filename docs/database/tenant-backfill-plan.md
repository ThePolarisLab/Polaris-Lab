# Tenant Backfill Plan

Status date: 2026-07-29

## Goal

Backfill `organization_id` for tenant-owned records introduced before Alembic without deleting data or assigning ambiguous ownership silently.

## Tenant-Owned Tables

- `companies`
- `trucks`
- `memory_entries`
- `knowledge_relationships`
- `missions`
- `mission_workflows`
- `mission_tasks`
- `team_notes`
- `financial_accounts`
- `financial_snapshots`
- `financial_sync_history`
- `quickbooks_oauth_credentials`
- `quickbooks_oauth_states`

## Backfill Rules

1. Add `organization_id` as nullable for compatible legacy tables.
2. Backfill child mission rows from their parents where possible:
   - `mission_workflows.organization_id` from `missions.organization_id`.
   - `mission_tasks.organization_id` from `mission_workflows.organization_id`.
3. If remaining unowned tenant rows exist and exactly one organization exists, assign that organization deterministically.
4. If multiple organizations exist, fail unless `POLARIS_TENANT_BACKFILL_ORGANIZATION_ID` names an existing organization.
5. If no organizations exist and tenant rows exist, fail.
6. Validate no tenant-owned rows remain with `organization_id IS NULL`.
7. Validate mission child ownership matches parent ownership.
8. Make `organization_id` non-null.

## Operator-Supplied Mapping

`POLARIS_TENANT_BACKFILL_ORGANIZATION_ID` is a coarse adoption control for legacy databases where every unowned row has been externally verified to belong to one organization. It is not a substitute for row-level mapping in genuinely mixed-tenant legacy databases.

If legacy data is mixed across tenants, stop and perform a manual data-mapping migration before running Phase 2 migrations.

## Data Safety

The migration never decrypts, re-encrypts, logs, or rewrites encrypted QuickBooks refresh tokens. Financial payloads, OAuth state strings, note text, memory details, timestamps, and primary keys are preserved.
