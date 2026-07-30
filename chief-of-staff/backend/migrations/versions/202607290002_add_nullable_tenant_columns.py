"""Add nullable tenant ownership columns for legacy databases.

Revision ID: 202607290002
Revises: 202607290001
Create Date: 2026-07-29 00:02:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202607290002"
down_revision = "202607290001"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "companies",
    "trucks",
    "memory_entries",
    "knowledge_relationships",
    "missions",
    "mission_workflows",
    "mission_tasks",
    "team_notes",
    "financial_accounts",
    "financial_snapshots",
    "financial_sync_history",
    "quickbooks_oauth_credentials",
    "quickbooks_oauth_states",
)


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _create_index_if_missing(table_name: str, column_name: str) -> None:
    index_name = f"ix_{table_name}_organization_id"
    if index_name not in _indexes(table_name):
        op.create_index(index_name, table_name, [column_name])


def upgrade() -> None:
    existing_tables = _tables()
    for table_name in TENANT_TABLES:
        if table_name not in existing_tables:
            continue
        if "organization_id" not in _columns(table_name):
            op.add_column(table_name, sa.Column("organization_id", sa.String(), nullable=True))
        _create_index_if_missing(table_name, "organization_id")

    if "organization_memberships" in existing_tables:
        columns = _columns("organization_memberships")
        if "organization_id" in columns:
            _create_index_if_missing("organization_memberships", "organization_id")
        if "identity_id" in columns and "ix_organization_memberships_identity_id" not in _indexes("organization_memberships"):
            op.create_index("ix_organization_memberships_identity_id", "organization_memberships", ["identity_id"])


def downgrade() -> None:
    raise RuntimeError(
        "Removing tenant ownership columns is unsafe because it would erase tenant isolation metadata."
    )
