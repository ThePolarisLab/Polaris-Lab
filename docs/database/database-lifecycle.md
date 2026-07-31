# Database Lifecycle

Status date: 2026-07-31  
Scope: Phase 2 Database Gate plus Phase 2.1 persistent deployment hardening.

## Supported Database Targets

- Local and test: SQLite via `sqlite:///...`.
- Production/staging: PostgreSQL-compatible URLs via `DATABASE_URL`. The application normalizes `postgres://` and `postgresql://` to SQLAlchemy's `postgresql+psycopg://` driver form.

Hosted production and staging services must not use SQLite under `/tmp`. Temporary container storage is not durable and can lose Alembic revision state, tenant data, connector credentials, financial snapshots, and sync history on redeploy, restart, spin-down, or instance replacement.

## Required Environment Variables

- `DATABASE_URL`: database connection URL. Defaults to `sqlite:///./polaris.db` only for local development. Hosted staging and production must use persistent PostgreSQL.
- `POLARIS_ENV`: `development`, `test`, `staging`, or `production`.
- `POLARIS_AUTO_CREATE_SCHEMA`: optional. In `development` and `test`, defaults to enabled for isolated local bootstrap. In `staging` and `production`, automatic schema creation is never allowed.
- `POLARIS_TENANT_BACKFILL_ORGANIZATION_ID`: optional operator-supplied organization ID for legacy multi-organization tenant backfill. Use only after a verified backup and ownership review.
- `POLARIS_FRONTEND_URL`: deployed frontend origin for hosted environments. Do not use `localhost` in staging or production.

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

## Schema Drift Audit

Run the production schema drift audit before merging model or migration changes, after any manual production database repair, and before adopting a database that predates Alembic. The audit compares Alembic head, SQLAlchemy models, the adoption inventory in `app.database.validate_schema`, and read-only PostgreSQL introspection.

Required reference: `docs/database/schema-drift-audit.md`.

## Deployment Order

```text
backup
-> validate schema/adoption status
-> alembic upgrade head
-> alembic current
-> start API
-> run health and smoke checks
```

Production and staging requests must never trigger schema creation or mutation. The current Render web service starts with:

```bash
python -m alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Use a Render pre-deploy command or one-off migration job before increasing web concurrency beyond one instance, so only one migration process runs against the production database.

See `docs/deployment/render-persistent-deployment.md` for the hosted cutover checklist.

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
