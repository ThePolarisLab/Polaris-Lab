# Motive Vehicle Utilization Database Identity

This gate adds **database-level enforcement** for the certified Polaris-owned
durable-writer replay identity on `motive_vehicle_utilization`. It is a
scoped database/schema-contract gate, not the writer-enablement PR.

It does **not** enable utilization persistence, create
`/sync/vehicle-utilization`, write utilization records from Motive, advance
`MotiveSyncCheckpoint`, enable the scheduler, enable broad Motive sync, make
live Motive provider calls, or change pagination, unit policy, Dashboard,
Daily Brief, alerts, ACE, Outlook, or QuickBooks behavior.

## Certified Logical Replay Identity

The certified Polaris-owned idempotency identity for a future durable
utilization writer, established by the writer-contract gate
(`MOTIVE_UTILIZATION_SEMANTICS_CERTIFICATION.md`), is:

```
organization_id + motive_vehicle_id + request_window_start + request_window_end
```

under the already-certified canonical metric policy (`X-Metric-Units: true`,
`metric_units == true`, canonical unit system = metric). `metric_units` is
deliberately **not** part of the key, because the canonical metric policy
already prevents parallel metric/imperial durable rows for the same
vehicle/window.

## Database Constraint

Alembic migration `202608150001` (`Revises: 202608140001`) adds:

```sql
UNIQUE (organization_id, motive_vehicle_id, request_window_start, request_window_end)
  -- name: uq_motive_vehicle_util_org_vehicle_request_window
```

on `motive_vehicle_utilization`. `app/models/motive.py` (`MotiveVehicleUtilizationRecord.__table_args__`)
declares the same constraint so the ORM model matches the migrated schema.

## Legacy Constraint Retained

The existing legacy uniqueness constraint on
`organization_id + provider_vehicle_id + reporting_period_start + reporting_period_end`
(`uq_motive_vehicle_util_org_period`) is **retained unchanged**. It is not
dropped, not modified, and not certified as the future writer's identity.
The new `uq_motive_vehicle_util_org_vehicle_request_window` constraint is the
only certified enforcement of the future writer's idempotency key.

## Nullable Legacy Compatibility

The four identity columns (`organization_id`, `motive_vehicle_id`,
`request_window_start`, `request_window_end`) remain **nullable**. This
migration does not make them `NOT NULL`, does not backfill unknown request
windows, does not copy `reporting_period_start`/`reporting_period_end` into
`request_window_start`/`request_window_end`, and does not infer
`motive_vehicle_id` from `provider_vehicle_id`.

Historical/pre-contract rows with an incomplete key (e.g.
`motive_vehicle_id IS NULL`) remain insertable — the database only rejects
duplicate **fully-populated** certified-identity rows. The future writer, not
this migration, will require a complete non-null identity before persisting
any row.

## Duplicate Preflight (Fail-Closed)

Before creating the unique constraint, the migration checks for existing
duplicate groups among **fully-populated** rows only (`organization_id`,
`motive_vehicle_id`, `request_window_start`, and `request_window_end` all
`IS NOT NULL`), grouped by those four columns with `COUNT(*) > 1`.

If any violating group exists, the migration raises:

```
Motive utilization certified request-window identity contains existing
duplicates; database uniqueness migration cannot proceed safely.
duplicate_group_count=<N>
```

and stops **before any schema mutation**. No row is deleted, merged, or
modified; no unit is silently deduplicated; the Alembic version does not
advance; and the target unique constraint is not partially created. This
migration is enforcement only, not cleanup — resolving any real duplicate
data is left to a separately reviewed operator/data process.

## Writer Contract Update

`app/motive/vehicle_utilization_writer_contract.py`'s `request_window_identity`
now reports:

```
database_enforced: true
database_constraint: "uq_motive_vehicle_util_org_vehicle_request_window"
database_identity_columns: ["organization_id", "motive_vehicle_id", "request_window_start", "request_window_end"]
legacy_reporting_period_constraint_retained: true
legacy_reporting_period_constraint_certified_for_future_writer: false
```

`writer_enabled`, `persistence_enabled`, `checkpoint_advancement_enabled`,
`scheduled_ingestion_enabled`, and `broad_sync_enabled` all remain `false`.
`observed_persistence_state` adds
`certified_request_window_unique_constraint_enforced: true` alongside the
existing read-only row count.

## Tenant Association Boundary

This uniqueness constraint certifies **database uniqueness of the Polaris
durable replay identity only**. It does **not** claim composite database-level
tenant ownership of `motive_vehicle_id`. Current association semantics still
require the application to map a provider vehicle to exactly one
`MotiveVehicleRecord` owned by the authenticated organization; no composite
foreign key was added, and none was required for this migration.

## Remaining Blockers

After this gate, `remaining_blockers` on the writer contract was:

1. utilization writer transaction implementation remains disabled
2. checkpoint advancement implementation remains disabled
3. exact company-configured Motive rollup timezone must be confirmed before
   scheduled daily ingestion

Database uniqueness enforcement is no longer listed as a blocker.

> **Superseded by the writer transaction gate.** The internal, all-or-nothing
> writer transaction primitive (`app.motive.vehicle_utilization_writer.write_vehicle_utilization_transaction`,
> database-enforced by the constraint added here) is now implemented. Blocker
> 1 above was replaced with "controlled/manual provider-to-database write
> validation remains disabled and requires separate authorization" — see
> `MOTIVE_UTILIZATION_WRITER_TRANSACTION.md`. This is still not runtime
> provider-to-database sync: there is no public write route, no checkpoint
> advancement, and no scheduler.

## Tests

- `tests/test_motive_vehicle_utilization_database_identity.py` — clean
  upgrade creates both constraints with the exact certified column order;
  upgrade to head twice is an idempotent no-op; database-level uniqueness
  enforcement (duplicate rejected; different window start/end, vehicle, or
  organization succeeds); nullable legacy rows remain insertable; the
  duplicate preflight fails closed (sanitized error, no row change, no
  version advance, no partial constraint) when built from a database seeded
  at the previous revision (`202608140001`).
- `tests/test_database_gate.py` — the clean-upgrade Database Gate test now
  also asserts both `motive_vehicle_utilization` unique constraints and
  their exact column order.
- `tests/test_motive_vehicle_utilization_writer_contract.py` — updated to
  assert the new `database_enforced`, constraint-name, and
  `observed_persistence_state` fields, and that "database uniqueness
  enforcement" no longer appears in `remaining_blockers`.

## No Live Provider Calls

This gate makes zero Motive provider calls. It is a database/schema-contract
gate only.

> **Now exercised by the controlled write validation gate.** The
> `uq_motive_vehicle_util_org_vehicle_request_window` constraint added here
> is the durable identity the feature-flagged (default disabled)
> `POST /api/v1/motive/verify/vehicle-utilization-write` route relies on when
> it calls the writer transaction for the fixed historical day `2026-08-13`.
> No schema change was required for that gate — see
> `MOTIVE_UTILIZATION_CONTROLLED_WRITE_VALIDATION.md`.
