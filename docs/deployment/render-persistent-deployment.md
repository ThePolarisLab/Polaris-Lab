# Render Persistent Deployment Hardening

Status date: 2026-07-30  
Scope: Phase 2.1 prerequisite before live QuickBooks production verification.

## Production Blocker

Production and staging Render services must not use SQLite files under `/tmp`, including:

```text
DATABASE_URL=sqlite:////tmp/polaris.db
```

That storage is temporary container filesystem. It can be lost on redeploy, restart, free-tier spin-down, or instance replacement. Losing that file can remove Alembic revision state, organizations, memberships, QuickBooks OAuth credentials, encrypted refresh tokens, sync history, financial snapshots, and connector health evidence.

Live QuickBooks OAuth and read-only financial synchronization must not be completed until the service uses persistent PostgreSQL.

## Required Render Resources

- Web service: `polaris-executive-api`.
- Persistent database: Render PostgreSQL, same region as the web service when possible.
- `DATABASE_URL`: the Render PostgreSQL Internal Database URL.
- `POLARIS_FRONTEND_URL`: the deployed Polaris frontend origin, not `localhost`.
- QuickBooks secrets: set only in Render environment variables or a secret manager; never commit them.

## Blueprint Expectations

The repository blueprint defines the backend root directory as `chief-of-staff/backend`. Commands entered in Render are evaluated from that directory.

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
python -m alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

This keeps deployment order aligned with the application startup guard:

```text
backup
-> validate schema
-> alembic upgrade head
-> verify revision
-> start application
-> post-migration checks
```

Longer term, prefer a Render pre-deploy migration command or one-off migration job before scaling beyond one web instance so concurrent web processes cannot attempt migrations at the same time.

## Cutover Procedure

1. Create a Render PostgreSQL database.
2. Copy the database Internal Database URL.
3. In the web service Environment page, replace any SQLite `DATABASE_URL` with the PostgreSQL URL.
4. Set `POLARIS_FRONTEND_URL` to the deployed frontend URL.
5. Confirm `POLARIS_ENV` is `production` or `staging` as appropriate.
6. Confirm production authentication, OAuth state, and token encryption secrets are set and are not defaults.
7. Deploy the service.
8. Confirm the deploy log includes:

```bash
python -m alembic upgrade head
alembic current
```

The current blueprint start command runs `alembic upgrade head`; if an operator also needs explicit revision evidence, run `alembic current` as a Render one-off job or add it temporarily to an operator-controlled deploy command.

9. Confirm `GET /health` returns `200` with only:

```json
{"status":"ok"}
```

10. Confirm authenticated detailed system health succeeds only with a valid bearer token and organization context.
11. Redeploy once and confirm data remains available.
12. Let the free instance spin down, wake it, and confirm `/health` still returns `200` and tenant data persists.

## Handling Existing Temporary SQLite Data

Data in `/tmp/polaris.db` is not durable production data. Before switching to PostgreSQL, decide explicitly whether it is disposable test data or must be manually exported.

Do not silently copy `/tmp` data into production PostgreSQL. If it must be preserved, take a backup, inspect ownership, validate the schema, and perform an operator-reviewed import into PostgreSQL.

## QuickBooks Gate

Do not complete Issue #61 live verification until all of these are true:

- Render `DATABASE_URL` points to PostgreSQL.
- `alembic upgrade head` succeeds on the PostgreSQL database.
- The app starts after the migration guard.
- `/health` returns `200` after redeploy and after free-tier wake-up.
- QuickBooks credentials, once authorized, survive a restart/redeploy.

## Public Endpoint Policy

Public readiness endpoints expose only generic status. Detailed runtime, database, version, environment, organization, and capability metadata must remain behind authenticated tenant-bound routes.
