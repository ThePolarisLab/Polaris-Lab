# Database Lifecycle

Status date: 2026-07-29  
Scope: Phase 2 Database Gate.

## Supported Database Targets

- Local and test: SQLite via `sqlite:///...`.
- Production/staging: PostgreSQL-compatible URLs via `DATABASE_URL`. The application normalizes `postgres://` and `postgresql://` to SQLAlchemy's `postgresql+psycopg://` driver form.

## Required Environment Variables

- `DATABASE_URL`: database connection URL. Defaults to `sqlite:///./polaris.db` only for local development.
- `POLARIS_ENV`: `development`, `test`, `staging`, or `production`.
- `POLARIS_AUTO_CREATE_SCHEMA`: optional. In `development` and `test`, defaults to enabled for isolated local bootstrap. In `staging` and `production`, automatic schema creation is never allowed.
- `POLARIS_TENANT_BACKFILL_ORGANIZATION_ID`: optional operator-supplied organization ID for legacy multi-organization tenant backfill. Use only after a verified backup and ownership review.

## Clean Installation

From `chief-of-staff/backend`:

```bash
pip install -r requirements.txt
alembic history
alembic upgrade head
alembic current
```

Then start the API. In staging and production the app refuses to start unless the database has an `alembic_version` row at the migration head.

## Existing Database Adoption

Never run `alembic stamp head` blindly.

1. Take and verify a backup.
2. Run:

```bash
python -m app.database.validate_schema
```

3. Interpret the result:

- `empty`: run `alembic upgrade head`.
- `current-compatible`: if `alembic_version` is absent, `python -m app.database.validate_schema --stamp-if-safe` may stamp `head`.
- `legacy-pre-tenant-compatible`: stamp the baseline revision with `--stamp-if-safe`, then run `alembic upgrade head`.
- `partial` or `unknown`: do not stamp. Investigate manually.

## Tenant Backfill

Legacy tenant-owned rows can be backfilled automatically only when exactly one organization exists. If multiple organizations exist, set `POLARIS_TENANT_BACKFILL_ORGANIZATION_ID` only after the operator confirms all legacy unowned rows belong to that organization. If no organizations exist and tenant-owned rows exist, migration fails safely.

## Deployment Order

```text
backup
-> validate schema/adoption status
-> alembic upgrade head
-> alembic current
-> start API
-> run health and smoke checks
```

Production and staging requests must never trigger schema creation or mutation.

## Common Commands

```bash
alembic current
alembic history
alembic upgrade head
alembic downgrade -1
alembic revision --autogenerate -m "describe change"
```

Downgrades that would remove tenant ownership or drop production data fail explicitly. Use restore-from-backup for destructive reversions.

## Test Workflow

Backend tests may still create isolated schemas directly when `POLARIS_ENV=test` or `POLARIS_AUTO_CREATE_SCHEMA=true`. This behavior is for test/dev only and is blocked in managed environments.
