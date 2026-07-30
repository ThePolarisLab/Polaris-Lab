# Rollback and Recovery

Status date: 2026-07-30

## Backup Requirement

Production migrations must not proceed without a verified backup.

Minimum pre-migration checklist:

- Confirm maintenance window and owner.
- Record current application commit and current Alembic revision.
- Create backup.
- Verify backup can be read.
- Run `python -m app.database.validate_schema`.
- Run `alembic current`.

Hosted production and staging must use persistent PostgreSQL. SQLite under `/tmp` is temporary container storage and is not an acceptable production recovery target.

## SQLite Backup

SQLite is supported for local development and isolated test workflows. Stop writers, then copy the database file and verify it opens:

```bash
cp polaris.db backups/polaris-$(date +%Y%m%d%H%M%S).db
sqlite3 backups/polaris-YYYYMMDDHHMMSS.db "PRAGMA integrity_check;"
```

Do not treat `/tmp/polaris.db` from a Render web instance as durable production data. If a temporary file contains test data that must be preserved, export it deliberately after operator review rather than silently promoting it to production.

## PostgreSQL Backup

Use `pg_dump` with credentials supplied by the deployment environment:

```bash
pg_dump "$DATABASE_URL" --format=custom --file=backups/polaris-$(date +%Y%m%d%H%M%S).dump
pg_restore --list backups/polaris-YYYYMMDDHHMMSS.dump >/tmp/polaris-restore-list.txt
```

For Render PostgreSQL, use the database's managed backup/snapshot capability where available and record the backup identifier before migration. Do not commit backups or credentials.

## Restore Validation

After restore to an isolated database:

```bash
python -m app.database.validate_schema
alembic current
alembic upgrade head
```

Then run application smoke tests against the restored database.

## Rollback Decision Criteria

Use restore-from-backup when:

- A migration fails after changing data.
- Tenant ownership validation fails unexpectedly.
- Application startup fails at schema head.
- Post-migration smoke checks detect data loss or tenant boundary issues.
- QuickBooks credential, sync, or financial evidence integrity is uncertain.

Phase 2 downgrade functions fail explicitly for destructive reversions. They are designed as guardrails, not production rollback automation. Do not reverse a destructive production migration in place; restore a verified backup to a known-good database and redeploy a compatible application revision.

## Post-Migration Verification

Run:

```bash
alembic current
python -m app.database.validate_schema
python -m pytest -v
```

For production, also verify `/health`, authenticated detailed system health, and tenant-scoped application smoke checks from a valid organization account.
