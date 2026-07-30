# Phase 2 Database Gate Audit

Starting main SHA: `8a61a110ce39da5c5015d781b28b3cc372a46788`

Branch: `phase2/database-gate`

This audit was completed before schema/runtime code changes for Phase 2. The local Windows shell was unavailable in the Codex sandbox (`CreateProcessAsUserW failed: 5`), so repository inspection used the GitHub connector, GitHub code search, and direct file reads from the branch created from latest `main`.

## Current SQLAlchemy configuration

- Database configuration lives in `chief-of-staff/backend/app/database/database.py`.
- `DATABASE_URL` defaults to `sqlite:///./polaris.db`.
- `postgres://` and `postgresql://` URLs are normalized to `postgresql+psycopg://`.
- SQLite uses `check_same_thread=False`.
- `pool_pre_ping=True` is enabled.
- `SessionLocal` and declarative `Base` are module-level globals.
- There is no Alembic configuration or migration table on `main`.

## Metadata registration

`chief-of-staff/backend/app/main.py` imports all model modules to register metadata and then calls `Base.metadata.create_all(bind=engine)` at import/startup time. The registered model modules are:

- `app.organizations.models`
- `app.identity.models`
- `app.models.company`
- `app.models.truck`
- `app.models.memory`
- `app.models.relationship`
- `app.missions.models`
- `app.models.team_note`
- `app.models.financial_snapshot`
- `app.connectors.quickbooks_credentials`

## Direct schema creation and mutation inventory

GitHub code search found these relevant occurrences:

- `Base.metadata.create_all`
  - `chief-of-staff/backend/app/main.py`: production application startup currently creates missing tables.
  - `chief-of-staff/backend/tests/test_security_gate.py`: test reset/bootstrap.
  - `chief-of-staff/backend/tests/test_tenant_isolation.py`: test reset/bootstrap.
  - documentation references in `docs/security/route-security-matrix.md` and `docs/security/technical-debt.md`.
- `Base.metadata.drop_all`
  - `chief-of-staff/backend/tests/test_security_gate.py`: test reset.
  - `chief-of-staff/backend/tests/test_tenant_isolation.py`: test reset.
- `create_engine`
  - `chief-of-staff/backend/app/database/database.py` only.
- Manual `ALTER TABLE`
  - No backend schema migration code was found. Search results for `ALTER TABLE` were documentation and TypeScript audit references, not SQLAlchemy migration code.

## SQLite and PostgreSQL assumptions

- SQLite is the local/test default and current tests rely on direct metadata creation against the default database URL.
- PostgreSQL support is implied by `psycopg[binary]` and URL normalization, but there is no migration CI yet.
- JSON fields are modeled with SQLAlchemy `JSON`; this is compatible for SQLite local storage and PostgreSQL JSON-compatible columns.
- Date/time fields mix timezone-aware (`DateTime(timezone=True)`) and timezone-naive `DateTime`; migration code must preserve existing values without conversion.
- SQLite cannot add or validate foreign keys, unique constraints, or non-null constraints in all cases with simple `ALTER TABLE`; staged migration must use Alembic batch mode or defer enforcement where unsafe.

## Table inventory

| Table | Model | Ownership | Current enforcement | Migration/backfill risk |
| --- | --- | --- | --- | --- |
| `organizations` | `Organization` | Tenant root and platform-visible entity | Primary key `id`, unique indexed `slug` | Existing databases with zero organizations cannot safely backfill tenant rows. Multiple organizations require explicit ownership mapping. |
| `identities` | `Identity` | Global identity directory, tenant exposure through membership | Unique indexed `email` | Do not tenant-scope identity rows directly; access must stay membership-gated. |
| `organization_memberships` | `OrganizationMembership` | Tenant membership join | `organization_id` FK, `identity_id` FK, unique pair | Backfill depends on existing identity and organization rows. |
| `companies` | `Company` | Tenant-owned singleton/company profile | `organization_id` FK, unique indexed | Legacy rows without ownership can be backfilled only when exactly one organization exists. |
| `trucks` | `Truck` | Tenant-owned operational data | `organization_id` FK/index, unique `(organization_id, unit_number)` | Legacy unit-number uniqueness must be checked before adding tenant uniqueness. |
| `memory_entries` | `MemoryEntry` | Tenant-owned knowledge/memory | `organization_id` FK/index | Existing memory rows are sensitive and must not be silently assigned in ambiguous cases. |
| `knowledge_relationships` | `KnowledgeRelationship` | Tenant-owned knowledge graph edges | `organization_id` FK/index, unique `(organization_id, source, target, relation)` | Legacy duplicate edges can conflict after backfill. |
| `missions` | `Mission` | Tenant-owned mission data | `organization_id` FK/index, unique `(organization_id, code)` | Legacy mission-code uniqueness must be checked per organization. |
| `mission_workflows` | `Workflow` | Tenant-owned child of mission | `organization_id` FK/index plus `mission_id` FK | Workflow org must match parent mission org after migration. |
| `mission_tasks` | `MissionTask` | Tenant-owned child of workflow | `organization_id` FK/index plus `workflow_id` FK | Task org must match parent workflow org after migration. |
| `team_notes` | `TeamNote` | Tenant-owned team note data | `organization_id` FK/index | Notes can contain sensitive operational details; no silent ambiguous assignment. |
| `financial_accounts` | `FinancialAccount` | Tenant-owned QuickBooks financial cache | `organization_id` FK/index, unique `(organization_id, qbo_id)` | Cache rows are sensitive financial data; duplicate QBO IDs must be tenant-scoped. |
| `financial_snapshots` | `FinancialSnapshot` | Tenant-owned financial snapshots | `organization_id` FK/index | Snapshot payloads must be preserved exactly. |
| `financial_sync_history` | `FinancialSyncHistory` | Tenant-owned sync audit/history | `organization_id` FK/index | Preserve timestamps, statuses, and error strings. |
| `quickbooks_oauth_credentials` | `QuickBooksOAuthCredential` | Tenant-owned encrypted OAuth credential | `organization_id` FK, unique/index | Refresh tokens are encrypted; migrations must never decrypt or re-encrypt. |
| `quickbooks_oauth_states` | `QuickBooksOAuthState` | Tenant/principal-bound OAuth state | `organization_id` FK/index, `identity_id` FK/index, `consumed_at` index | OAuth state rows are short-lived and replay-sensitive; migration must preserve state fields and not expose secrets. |
| in-memory event bus | `app.events.bus` | Runtime-only events | No database table | No schema migration required. |
| future connector storage | connector framework | Tenant-owned by design | Current persistent connector state is QuickBooks-specific | Future connectors must use `organization_id` and Alembic migrations before production use. |

## Newly added organization ownership fields

Phase 1.1 already introduced `organization_id` onto the tenant-owned models listed above. Existing pre-Phase 1.1 databases may therefore lack the columns and require staged addition/backfill before the application can start against the Phase 1.1 model set.

## Destructive-change risks

- Dropping and recreating tables would destroy QuickBooks encrypted credentials, financial history, notes, memory, trucks, missions, workflows, tasks, memberships, and tenant boundaries.
- Automatically assigning tenant-owned rows to an arbitrary organization is unsafe when more than one organization exists.
- Backfilling child rows must preserve hierarchy: mission -> workflow -> task.
- SQLite table rebuilds can rewrite data; every batch operation must preserve primary keys and timestamps.
- OAuth credential and state migrations must treat encrypted tokens and opaque state strings as opaque data.

## Required changes

1. Add Alembic and point it at the existing `Base.metadata` after importing all model modules.
2. Add a migration chain that supports clean installs and safe adoption of legacy pre-Alembic databases.
3. Add an adoption/schema validation command that refuses unknown, partially migrated, and ambiguous schemas.
4. Remove production/staging reliance on `Base.metadata.create_all`; production startup must require an Alembic-managed schema at head.
5. Preserve explicit dev/test bootstrap behavior without allowing production schema mutation.
6. Add migration tests for clean SQLite, legacy single-organization SQLite, ambiguous multi-organization SQLite, no-organization failure, idempotency, downgrade behavior, startup schema enforcement, and tenant-isolation regression.
7. Add Database Gate CI so migration lifecycle checks run on the Phase 2 PR and future database changes.
