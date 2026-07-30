# Polaris Lab

Helping Builders Build Better.

## Backend Database Setup

From `chief-of-staff/backend`:

```bash
pip install -r requirements.txt
alembic upgrade head
alembic current
```

Local development defaults to SQLite at `sqlite:///./polaris.db`. Staging and production must provide `DATABASE_URL` and run `alembic upgrade head` before starting the API; the application refuses to start against an unversioned or stale managed database.

Before adopting an existing database, run:

```bash
python -m app.database.validate_schema
```

See `docs/database/database-lifecycle.md`, `docs/database/tenant-backfill-plan.md`, and `docs/database/rollback-and-recovery.md` for the full Phase 2 Database Gate process.
