# Rollback and Recovery

Status date: 2026-07-30

Current readiness and execution gates: [2026-10-12 recovery assessment and isolated restore plan](RECOVERY_READINESS_2026-10-12.md). The dated procedures below do not establish recovery certification; validate the original recovered state before considering migrations, and account for application encryption-key/configuration recovery.

## Governing recovery authority

[Confirmed MOR rule 23: Backup, Restore, and Recovery Governance](../operations/POLARIS_MOR_GOVERNED_BUSINESS_RULES.md#23-backup-restore-and-recovery-governance) governs this runbook. RPO <= 1 hour / RTO <= 4 hours are required certification targets; recovery remains **NOT CERTIFIED**. Historical writes and broader autonomy stay blocked until certification, and historical execution still requires separate explicit approval afterward.

The commands below are technical procedure examples, not execution approval. Verify actual production mapping, Neon backup/PITR/snapshot/export capabilities, independent backup availability, encryption-key/configuration recovery and assigned recovery ownership before a drill. Any cloud resource creation/deletion, production-setting change, cost, key rotation or backup-policy change requires explicit human approval before execution. A readable backup is a pre-migration check, not tested-restore certification.

Restore testing must use an isolated non-production target without modifying production data, with external integrations and side effects disabled. Preserve tenant isolation, audit history, TorqueAI backfill evidence and both quarantined identity conflicts. Record timezone-qualified timestamps, elapsed recovery time, RPO/RTO pass/fail, evidence and unresolved gaps using the [certificate template](RECOVERY_READINESS_2026-10-12.md#5-passfail-and-certificate).

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

After an approved restore to an isolated non-production database, first validate the original recovered state using the compatible application revision, without migrations or upgrades:

```bash
python -m app.database.validate_schema
alembic current
```

Then validate tenant boundaries, audit history, TorqueAI backfill evidence, both quarantined conflicts and matching-key/configuration recovery; run tenant-scoped read-only application smoke tests with external integrations and side effects disabled. Review startup behavior first: the current Blueprint automatically upgrades schema. Use a reviewed isolated startup procedure that preserves the recovered state.

Only after original-state validation may a separately reviewed upgrade rehearsal run on a disposable isolated copy; `alembic upgrade head` is not part of initial restore validation. No production cutover or migration is authorized by this runbook.

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
