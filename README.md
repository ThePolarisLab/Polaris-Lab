# Polaris Lab

Helping Builders Build Better.

## Backend Database Setup

From `chief-of-staff/backend`:

```bash
pip install -r requirements.txt
alembic upgrade head
alembic current
```

Local development defaults to SQLite at `sqlite:///./polaris.db`. Staging and production must provide a persistent PostgreSQL `DATABASE_URL` and run `alembic upgrade head` before starting the API; the application refuses to start against an unversioned or stale managed database.

Do not use `sqlite:////tmp/polaris.db` for production or staging. Render `/tmp` storage can disappear on redeploy, restart, free-tier spin-down, or container replacement.

Before adopting an existing database, run:

```bash
python -m app.database.validate_schema
```

Render backend services should use:

```bash
pip install -r requirements.txt
python -m alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Set `POLARIS_FRONTEND_URL` to the deployed frontend origin, not `localhost`, for hosted environments.

See `docs/database/database-lifecycle.md`, `docs/database/tenant-backfill-plan.md`, `docs/database/rollback-and-recovery.md`, and `docs/deployment/render-persistent-deployment.md` for the full Phase 2/2.1 database lifecycle process.

## QuickBooks Production Setup

Phase 3A keeps QuickBooks Online read-only and tenant-bound. Configure Intuit credentials in Render or another secret manager, never in GitHub or source control. Use `chief-of-staff/backend/.env.quickbooks.example` as the variable inventory.

Production prerequisites:

- hosted `DATABASE_URL` points to persistent PostgreSQL, not temporary SQLite;
- `python -m alembic upgrade head` succeeds before API startup;
- public `/` and `/health` expose only generic status;
- `POLARIS_FRONTEND_URL` points to the deployed frontend origin.

Operator setup and smoke-test steps are documented in `docs/integrations/quickbooks-production-runbook.md`. Runtime ownership and the Python/Hermes boundary are documented in `docs/architecture/ADR-026-quickbooks-runtime-ownership.md`.
