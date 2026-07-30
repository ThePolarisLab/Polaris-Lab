"""Initial Database Gate schema for clean installs.

Revision ID: 202607290001
Revises:
Create Date: 2026-07-29 00:01:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202607290001"
down_revision = None
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _create_index_if_missing(name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if name not in _indexes(table_name):
        op.create_index(name, table_name, columns, unique=unique)


def upgrade() -> None:
    existing = _tables()

    if "organizations" not in existing:
        op.create_table(
            "organizations",
            sa.Column("id", sa.String(), primary_key=True, nullable=False),
            sa.Column("slug", sa.String(length=120), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column("legal_name", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        _create_index_if_missing("ix_organizations_id", "organizations", ["id"])
        _create_index_if_missing("ix_organizations_slug", "organizations", ["slug"], unique=True)

    if "identities" not in existing:
        op.create_table(
            "identities",
            sa.Column("id", sa.String(), primary_key=True, nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        _create_index_if_missing("ix_identities_id", "identities", ["id"])
        _create_index_if_missing("ix_identities_email", "identities", ["email"], unique=True)

    existing = _tables()

    if "organization_memberships" not in existing:
        op.create_table(
            "organization_memberships",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("identity_id", sa.String(), nullable=False),
            sa.Column("role", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["identity_id"], ["identities.id"]),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.UniqueConstraint("organization_id", "identity_id", name="uq_organization_membership_identity"),
        )
        _create_index_if_missing("ix_organization_memberships_id", "organization_memberships", ["id"])
        _create_index_if_missing("ix_organization_memberships_organization_id", "organization_memberships", ["organization_id"])
        _create_index_if_missing("ix_organization_memberships_identity_id", "organization_memberships", ["identity_id"])

    if "companies" not in existing:
        op.create_table(
            "companies",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("website", sa.String(), nullable=True),
            sa.Column("industry", sa.String(), nullable=True),
            sa.Column("location", sa.String(), nullable=True),
            sa.Column("mission", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        )
        _create_index_if_missing("ix_companies_id", "companies", ["id"])
        _create_index_if_missing("ix_companies_organization_id", "companies", ["organization_id"], unique=True)

    if "trucks" not in existing:
        op.create_table(
            "trucks",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("unit_number", sa.String(), nullable=False),
            sa.Column("make", sa.String(), nullable=True),
            sa.Column("model", sa.String(), nullable=True),
            sa.Column("year", sa.Integer(), nullable=True),
            sa.Column("vin", sa.String(), nullable=True),
            sa.Column("license_plate", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="active"),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.UniqueConstraint("organization_id", "unit_number", name="uq_truck_organization_unit_number"),
        )
        _create_index_if_missing("ix_trucks_id", "trucks", ["id"])
        _create_index_if_missing("ix_trucks_organization_id", "trucks", ["organization_id"])

    if "memory_entries" not in existing:
        op.create_table(
            "memory_entries",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("category", sa.String(length=100), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("details", sa.Text(), nullable=False),
            sa.Column("importance", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("source", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        )
        _create_index_if_missing("ix_memory_entries_id", "memory_entries", ["id"])
        _create_index_if_missing("ix_memory_entries_organization_id", "memory_entries", ["organization_id"])
        _create_index_if_missing("ix_memory_entries_category", "memory_entries", ["category"])

    if "knowledge_relationships" not in existing:
        op.create_table(
            "knowledge_relationships",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("source", sa.String(length=255), nullable=False),
            sa.Column("target", sa.String(length=255), nullable=False),
            sa.Column("relation", sa.String(length=100), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.UniqueConstraint("organization_id", "source", "target", "relation", name="uq_knowledge_relationship_org"),
        )
        _create_index_if_missing("ix_knowledge_relationships_id", "knowledge_relationships", ["id"])
        _create_index_if_missing("ix_knowledge_relationships_organization_id", "knowledge_relationships", ["organization_id"])
        _create_index_if_missing("ix_knowledge_relationships_source", "knowledge_relationships", ["source"])
        _create_index_if_missing("ix_knowledge_relationships_target", "knowledge_relationships", ["target"])
        _create_index_if_missing("ix_knowledge_relationships_relation", "knowledge_relationships", ["relation"])

    if "missions" not in existing:
        op.create_table(
            "missions",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("code", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(), nullable=False, server_default="Not Started"),
            sa.Column("priority", sa.String(), nullable=False, server_default="Medium"),
            sa.Column("owner", sa.String(), nullable=False, server_default="Founder"),
            sa.Column("company", sa.String(), nullable=False, server_default="MOR Logistics Manitoba Limited"),
            sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("due_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.UniqueConstraint("organization_id", "code", name="uq_mission_organization_code"),
        )
        _create_index_if_missing("ix_missions_id", "missions", ["id"])
        _create_index_if_missing("ix_missions_code", "missions", ["code"])
        _create_index_if_missing("ix_missions_organization_id", "missions", ["organization_id"])

    if "mission_workflows" not in existing:
        op.create_table(
            "mission_workflows",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("mission_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="Not Started"),
            sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["mission_id"], ["missions.id"]),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        )
        _create_index_if_missing("ix_mission_workflows_id", "mission_workflows", ["id"])
        _create_index_if_missing("ix_mission_workflows_mission_id", "mission_workflows", ["mission_id"])
        _create_index_if_missing("ix_mission_workflows_organization_id", "mission_workflows", ["organization_id"])

    if "mission_tasks" not in existing:
        op.create_table(
            "mission_tasks",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("workflow_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="Not Started"),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("system", sa.String(), nullable=True),
            sa.Column("capability", sa.String(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["workflow_id"], ["mission_workflows.id"]),
        )
        _create_index_if_missing("ix_mission_tasks_id", "mission_tasks", ["id"])
        _create_index_if_missing("ix_mission_tasks_workflow_id", "mission_tasks", ["workflow_id"])
        _create_index_if_missing("ix_mission_tasks_organization_id", "mission_tasks", ["organization_id"])

    if "team_notes" not in existing:
        op.create_table(
            "team_notes",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("author", sa.String(length=255), nullable=False),
            sa.Column("note_type", sa.String(length=100), nullable=False),
            sa.Column("status", sa.String(length=100), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("details", sa.Text(), nullable=False),
            sa.Column("target_entity", sa.String(length=255), nullable=True),
            sa.Column("assigned_to", sa.String(length=255), nullable=True),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        )
        _create_index_if_missing("ix_team_notes_id", "team_notes", ["id"])
        _create_index_if_missing("ix_team_notes_organization_id", "team_notes", ["organization_id"])
        _create_index_if_missing("ix_team_notes_author", "team_notes", ["author"])
        _create_index_if_missing("ix_team_notes_note_type", "team_notes", ["note_type"])
        _create_index_if_missing("ix_team_notes_status", "team_notes", ["status"])

    if "financial_accounts" not in existing:
        op.create_table(
            "financial_accounts",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("qbo_id", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("fully_qualified_name", sa.String(length=500), nullable=True),
            sa.Column("account_type", sa.String(length=120), nullable=True),
            sa.Column("account_subtype", sa.String(length=120), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("current_balance", sa.Float(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.UniqueConstraint("organization_id", "qbo_id", name="uq_financial_account_org_qbo"),
        )
        _create_index_if_missing("ix_financial_accounts_organization_id", "financial_accounts", ["organization_id"])
        _create_index_if_missing("ix_financial_accounts_qbo_id", "financial_accounts", ["qbo_id"])
        _create_index_if_missing("ix_financial_accounts_synced_at", "financial_accounts", ["synced_at"])

    if "financial_snapshots" not in existing:
        op.create_table(
            "financial_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("snapshot_type", sa.String(length=50), nullable=False),
            sa.Column("period_start", sa.String(length=10), nullable=True),
            sa.Column("period_end", sa.String(length=10), nullable=True),
            sa.Column("accounting_method", sa.String(length=20), nullable=False, server_default="Accrual"),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        )
        _create_index_if_missing("ix_financial_snapshots_organization_id", "financial_snapshots", ["organization_id"])
        _create_index_if_missing("ix_financial_snapshots_snapshot_type", "financial_snapshots", ["snapshot_type"])
        _create_index_if_missing("ix_financial_snapshots_captured_at", "financial_snapshots", ["captured_at"])

    if "financial_sync_history" not in existing:
        op.create_table(
            "financial_sync_history",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("accounts_imported", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("company_name", sa.String(length=255), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        )
        _create_index_if_missing("ix_financial_sync_history_organization_id", "financial_sync_history", ["organization_id"])
        _create_index_if_missing("ix_financial_sync_history_status", "financial_sync_history", ["status"])
        _create_index_if_missing("ix_financial_sync_history_started_at", "financial_sync_history", ["started_at"])

    if "quickbooks_oauth_credentials" not in existing:
        op.create_table(
            "quickbooks_oauth_credentials",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("realm_id", sa.String(length=80), nullable=False),
            sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
            sa.Column("scopes", sa.Text(), nullable=False, server_default="com.intuit.quickbooks.accounting"),
            sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        )
        _create_index_if_missing("ix_quickbooks_oauth_credentials_organization_id", "quickbooks_oauth_credentials", ["organization_id"], unique=True)

    if "quickbooks_oauth_states" not in existing:
        op.create_table(
            "quickbooks_oauth_states",
            sa.Column("state", sa.String(length=255), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("identity_id", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["identity_id"], ["identities.id"]),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        )
        _create_index_if_missing("ix_quickbooks_oauth_states_organization_id", "quickbooks_oauth_states", ["organization_id"])
        _create_index_if_missing("ix_quickbooks_oauth_states_identity_id", "quickbooks_oauth_states", ["identity_id"])
        _create_index_if_missing("ix_quickbooks_oauth_states_created_at", "quickbooks_oauth_states", ["created_at"])
        _create_index_if_missing("ix_quickbooks_oauth_states_expires_at", "quickbooks_oauth_states", ["expires_at"])
        _create_index_if_missing("ix_quickbooks_oauth_states_consumed_at", "quickbooks_oauth_states", ["consumed_at"])


def downgrade() -> None:
    raise RuntimeError(
        "Downgrading the initial Polaris database schema would drop production data. "
        "Restore from a verified backup instead."
    )
