"""Add organization_slug to financial_snapshots.

Follow-up to 202607300003, which covered financial_accounts and
financial_sync_history but missed financial_snapshots -- a third table that
carries the same legacy organization_slug NOT NULL drift from before Alembic
migrations existed. Discovered when a live QuickBooks sync progressed past
account import and failed inserting into financial_snapshots.

Revision ID: 202607300004
Revises: 202607300003
Create Date: 2026-07-31 12:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202607300004"
down_revision = "202607300003"
branch_labels = None
depends_on = None

TARGET_TABLES = ("financial_snapshots",)


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _create_index_if_missing(name: str, table_name: str, columns: list[str]) -> None:
    if name not in _indexes(table_name):
        op.create_index(name, table_name, columns)


def _is_nullable(table_name: str, column_name: str) -> bool:
    for column in sa.inspect(op.get_bind()).get_columns(table_name):
        if column["name"] == column_name:
            return bool(column.get("nullable", True))
    return False


def _backfill_slug(table_name: str) -> None:
    op.get_bind().execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET organization_slug = organizations.slug
            FROM organizations
            WHERE {table_name}.organization_id = organizations.id
              AND ({table_name}.organization_slug IS NULL OR {table_name}.organization_slug = '')
            """
        )
    )


def _rows_missing_slug(table_name: str) -> int:
    return int(
        op.get_bind()
        .execute(
            sa.text(
                f"SELECT COUNT(*) FROM {table_name} "
                f"WHERE organization_slug IS NULL OR organization_slug = ''"
            )
        )
        .scalar()
        or 0
    )


def upgrade() -> None:
    if "organizations" not in _tables():
        return

    for table_name in TARGET_TABLES:
        if table_name not in _tables():
            continue

        if "organization_slug" not in _columns(table_name):
            op.add_column(table_name, sa.Column("organization_slug", sa.String(), nullable=True))

        _backfill_slug(table_name)

        remaining = _rows_missing_slug(table_name)
        if remaining:
            raise RuntimeError(
                f"{remaining} row(s) in {table_name} could not be backfilled with organization_slug "
                "(orphaned organization_id or organization missing a slug). Resolve data before retrying."
            )

        if _is_nullable(table_name, "organization_slug"):
            with op.batch_alter_table(table_name) as batch_op:
                batch_op.alter_column("organization_slug", existing_type=sa.String(), nullable=False)

        _create_index_if_missing(f"ix_{table_name}_organization_slug", table_name, ["organization_slug"])


def downgrade() -> None:
    raise RuntimeError(
        "Downgrading organization_slug enforcement is unsafe because model code and production "
        "already depend on it being present and non-null."
    )
