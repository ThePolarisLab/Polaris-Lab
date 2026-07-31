# Production Schema Drift Audit

Status date: 2026-07-31  
Scope: production hardening cleanup after the QuickBooks sync-history `organization_slug` mismatch.

## Why This Exists

Polaris now uses Alembic as the source of truth for schema lifecycle, but production databases can still drift when:

- a database predates Alembic adoption;
- a live database was repaired manually during an incident;
- SQLAlchemy models advance without matching adoption inventory updates;
- migration tests cover fresh databases but not an adopted production-shaped database;
- code reads or writes a column that exists in one environment but is missing from another.

The production QuickBooks sync failure in July 2026 was caused by this class of issue: `financial_sync_history.organization_slug` was non-null in the live PostgreSQL schema, but the ORM/adoption inventory path did not consistently account for it.

## Source Of Truth Order

Use this order when resolving disagreement:

1. Alembic revision chain at head.
2. SQLAlchemy models registered in `Base.metadata`.
3. `app.database.validate_schema.EXPECTED_COLUMNS` adoption inventory.
4. Production PostgreSQL introspection from a read-only/schema-only query.
5. Documentation.

If any lower layer disagrees with Alembic head and the current models, treat it as drift until proven otherwise.

## Required Audit Triggers

Run this audit before merging or deploying any change that touches:

- SQLAlchemy models;
- Alembic migrations;
- database adoption or bootstrap scripts;
- tenant-owned persistence;
- connector credentials or OAuth state;
- financial cache tables;
- production incident repairs involving database rows or columns.

Also run it after any emergency production data repair.

## Local Audit Checklist

From `chief-of-staff/backend`:

```bash
python -m alembic heads
python -m alembic current
python -m alembic upgrade head
python -m app.database.validate_schema
python -m pytest tests/test_schema_adoption_inventory.py
```

Expected results:

- exactly one Alembic head;
- `alembic current` reports the head revision;
- `validate_schema` returns `empty`, `current-compatible`, or another documented safe state for the target database;
- schema adoption inventory tests pass.

## Production-Safe Introspection

Use Render PostgreSQL or another production database only after confirming the command is read-only. Do not paste credentials into GitHub, issues, PRs, logs, screenshots, or chat.

Recommended PostgreSQL checks:

```sql
select version_num from alembic_version;

select table_name, column_name, is_nullable, data_type
from information_schema.columns
where table_schema = 'public'
order by table_name, ordinal_position;
```

For the QuickBooks financial cache, verify at minimum:

```sql
select column_name, is_nullable, data_type
from information_schema.columns
where table_schema = 'public'
  and table_name in ('financial_accounts', 'financial_snapshots', 'financial_sync_history')
order by table_name, ordinal_position;
```

Expected current financial ownership fields:

- `financial_accounts.organization_id`
- `financial_accounts.organization_slug`
- `financial_snapshots.organization_id`
- `financial_snapshots.organization_slug`
- `financial_sync_history.organization_id`
- `financial_sync_history.organization_slug`

`organization_id` and `organization_slug` must be populated from the same `organizations` row. Do not repair missing slugs by guessing tenant ownership.

## Drift Response

If drift is found:

1. Stop the affected production workflow.
2. Take and verify a backup.
3. Identify whether the database, model, migration, or adoption inventory is wrong.
4. Prefer a forward Alembic migration or narrow code fix over manual mutation.
5. Add or update a regression test that would have caught the drift.
6. Document the incident in the PR body and relevant runbook.
7. Deploy only after Database Gate, Security Gate, and relevant connector workflows pass.

## Explicitly Unsafe Actions

Do not:

- run `alembic stamp head` without `python -m app.database.validate_schema`;
- make tenant ownership columns nullable to bypass a production error;
- assign `organization_slug` independently from `organization_id`;
- use `/tmp` SQLite in hosted staging or production;
- run write SQL against production without backup, review, and a rollback plan.
