"""Backfill and require tenant ownership.

Revision ID: 202607290003
Revises: 202607290002
Create Date: 2026-07-29 00:03:00
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa

revision = "202607290003"
down_revision = "202607290002"
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


def _scalar(sql: str, **params: object) -> object:
    return op.get_bind().execute(sa.text(sql), params).scalar()


def _execute(sql: str, **params: object) -> None:
    op.get_bind().execute(sa.text(sql), params)


def _organization_ids() -> list[str]:
    if "organizations" not in _tables():
        return []
    rows = op.get_bind().execute(sa.text("SELECT id FROM organizations ORDER BY id")).fetchall()
    return [str(row[0]) for row in rows]


def _tenant_rows_needing_backfill(table_name: str) -> int:
    if table_name not in _tables() or "organization_id" not in _columns(table_name):
        return 0
    return int(_scalar(f"SELECT COUNT(*) FROM {table_name} WHERE organization_id IS NULL") or 0)


def _tenant_row_count(table_name: str) -> int:
    if table_name not in _tables() or "organization_id" not in _columns(table_name):
        return 0
    return int(_scalar(f"SELECT COUNT(*) FROM {table_name}") or 0)


def _backfill_organization_id() -> str | None:
    organization_ids = _organization_ids()
    explicit = os.getenv("POLARIS_TENANT_BACKFILL_ORGANIZATION_ID", "").strip()
    if explicit:
        if explicit not in organization_ids:
            raise RuntimeError(
                "POLARIS_TENANT_BACKFILL_ORGANIZATION_ID does not match an existing organization"
            )
        return explicit
    if len(organization_ids) == 1:
        return organization_ids[0]
    if len(organization_ids) == 0:
        return None
    raise RuntimeError(
        "Legacy tenant backfill is ambiguous because multiple organizations exist. "
        "Set POLARIS_TENANT_BACKFILL_ORGANIZATION_ID after taking a verified backup, "
        "or perform an operator-supplied data mapping before retrying."
    )


def _backfill_children_from_parents() -> None:
    if "mission_workflows" in _tables() and {"organization_id", "mission_id"}.issubset(_columns("mission_workflows")):
        _execute(
            """
            UPDATE mission_workflows
            SET organization_id = (
                SELECT missions.organization_id
                FROM missions
                WHERE missions.id = mission_workflows.mission_id
            )
            WHERE organization_id IS NULL
              AND mission_id IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM missions WHERE missions.id = mission_workflows.mission_id
              )
            """
        )
    if "mission_tasks" in _tables() and {"organization_id", "workflow_id"}.issubset(_columns("mission_tasks")):
        _execute(
            """
            UPDATE mission_tasks
            SET organization_id = (
                SELECT mission_workflows.organization_id
                FROM mission_workflows
                WHERE mission_workflows.id = mission_tasks.workflow_id
            )
            WHERE organization_id IS NULL
              AND workflow_id IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM mission_workflows WHERE mission_workflows.id = mission_tasks.workflow_id
              )
            """
        )


def _make_org_not_nullable(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column("organization_id", existing_type=sa.String(), nullable=False)


def _validate_child_ownership() -> None:
    if {"missions", "mission_workflows"}.issubset(_tables()):
        mismatched = int(
            _scalar(
                """
                SELECT COUNT(*)
                FROM mission_workflows
                JOIN missions ON missions.id = mission_workflows.mission_id
                WHERE mission_workflows.organization_id != missions.organization_id
                """
            )
            or 0
        )
        if mismatched:
            raise RuntimeError("Mission workflow organization ownership does not match parent mission")
    if {"mission_workflows", "mission_tasks"}.issubset(_tables()):
        mismatched = int(
            _scalar(
                """
                SELECT COUNT(*)
                FROM mission_tasks
                JOIN mission_workflows ON mission_workflows.id = mission_tasks.workflow_id
                WHERE mission_tasks.organization_id != mission_workflows.organization_id
                """
            )
            or 0
        )
        if mismatched:
            raise RuntimeError("Mission task organization ownership does not match parent workflow")


def upgrade() -> None:
    _backfill_children_from_parents()

    tables_with_null_rows = [table for table in TENANT_TABLES if _tenant_rows_needing_backfill(table) > 0]
    if tables_with_null_rows:
        organization_id = _backfill_organization_id()
        if organization_id is None:
            raise RuntimeError(
                "Legacy tenant backfill found tenant-owned rows but no organizations. "
                "Create or map an organization after taking a verified backup, then retry."
            )
        for table_name in tables_with_null_rows:
            _execute(
                f"UPDATE {table_name} SET organization_id = :organization_id WHERE organization_id IS NULL",
                organization_id=organization_id,
            )

    for table_name in TENANT_TABLES:
        if _tenant_rows_needing_backfill(table_name):
            raise RuntimeError(f"Tenant backfill left NULL organization_id rows in {table_name}")

    _validate_child_ownership()

    for table_name in TENANT_TABLES:
        if table_name in _tables() and "organization_id" in _columns(table_name):
            if _tenant_row_count(table_name) == 0 or _tenant_rows_needing_backfill(table_name) == 0:
                _make_org_not_nullable(table_name)


def downgrade() -> None:
    raise RuntimeError(
        "Downgrading tenant ownership enforcement is unsafe because it would permit unowned rows."
    )
