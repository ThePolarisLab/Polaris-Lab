"""Enforce Motive vehicle utilization database identity.

Adds a database uniqueness constraint for the certified Polaris-owned
durable-writer replay identity on ``motive_vehicle_utilization``:

    organization_id + motive_vehicle_id + request_window_start + request_window_end

This is enforcement only, not writer enablement. The four identity columns
remain nullable for backward compatibility with historical/pre-contract
rows; the future writer will require a complete non-null identity before
persistence. The legacy reporting-period uniqueness constraint
(``uq_motive_vehicle_util_org_period``) is retained unchanged.

Revision ID: 202608150001
Revises: 202608140001
Create Date: 2026-08-15 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202608150001"
down_revision = "202608140001"
branch_labels = None
depends_on = None

TABLE_NAME = "motive_vehicle_utilization"
CONSTRAINT_NAME = "uq_motive_vehicle_util_org_vehicle_request_window"
IDENTITY_COLUMNS = (
    "organization_id",
    "motive_vehicle_id",
    "request_window_start",
    "request_window_end",
)


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _duplicate_group_count() -> int:
    """Count groups of fully-populated certified-identity duplicates.

    Only rows where every identity column is non-null are considered --
    historical/legacy rows with an incomplete key are intentionally out of
    scope for this uniqueness enforcement.
    """
    columns_sql = ", ".join(IDENTITY_COLUMNS)
    not_null_sql = " AND ".join(f"{column} IS NOT NULL" for column in IDENTITY_COLUMNS)
    sql = sa.text(
        f"""
        SELECT COUNT(*) FROM (
            SELECT {columns_sql}
            FROM {TABLE_NAME}
            WHERE {not_null_sql}
            GROUP BY {columns_sql}
            HAVING COUNT(*) > 1
        ) AS duplicate_certified_identity_groups
        """
    )
    return int(op.get_bind().execute(sql).scalar() or 0)


def upgrade() -> None:
    inspector = _inspector()
    columns = {column["name"] for column in inspector.get_columns(TABLE_NAME)}
    missing_columns = [name for name in IDENTITY_COLUMNS if name not in columns]
    if missing_columns:
        raise RuntimeError(
            "Motive utilization database identity migration requires columns "
            f"{missing_columns} on {TABLE_NAME}, but they were not found. "
            "Run the schema-hardening migration (202608140001) first."
        )

    existing_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints(TABLE_NAME)}
    if CONSTRAINT_NAME in existing_constraints:
        # Already enforced; nothing to do (idempotent re-run / already-current DB).
        return

    duplicate_group_count = _duplicate_group_count()
    if duplicate_group_count:
        raise RuntimeError(
            "Motive utilization certified request-window identity contains existing "
            "duplicates; database uniqueness migration cannot proceed safely. "
            f"duplicate_group_count={duplicate_group_count}"
        )

    with op.batch_alter_table(TABLE_NAME) as batch_op:
        batch_op.create_unique_constraint(CONSTRAINT_NAME, list(IDENTITY_COLUMNS))


def downgrade() -> None:
    raise RuntimeError(
        "unsafe destructive downgrade is intentionally disabled for Motive utilization database identity"
    )
