"""Validate existing Polaris databases before Alembic adoption.

Usage:
    python -m app.database.validate_schema
    python -m app.database.validate_schema --stamp-if-safe
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

from alembic import command
from sqlalchemy import inspect

from app.database.database import engine
from app.database.schema_guard import _alembic_config

EXPECTED_COLUMNS: dict[str, set[str]] = {
    "organizations": {"id", "slug", "display_name", "legal_name", "status", "created_at", "updated_at"},
    "identities": {"id", "email", "display_name", "status", "created_at", "updated_at"},
    "organization_memberships": {"id", "organization_id", "identity_id", "role", "status", "created_at"},
    "companies": {"id", "organization_id", "name", "description", "website", "industry", "location", "mission", "created_at", "updated_at"},
    "trucks": {"id", "organization_id", "unit_number", "make", "model", "year", "vin", "license_plate", "status", "notes", "created_at", "updated_at"},
    "memory_entries": {"id", "organization_id", "category", "title", "details", "importance", "source", "created_at"},
    "knowledge_relationships": {"id", "organization_id", "source", "target", "relation", "created_at"},
    "missions": {"id", "organization_id", "code", "title", "description", "status", "priority", "owner", "company", "progress", "created_at", "started_at", "due_at", "completed_at"},
    "mission_workflows": {"id", "organization_id", "mission_id", "title", "status", "progress", "position"},
    "mission_tasks": {"id", "organization_id", "workflow_id", "title", "status", "position", "system", "capability", "notes", "completed_at"},
    "team_notes": {"id", "organization_id", "author", "note_type", "status", "title", "details", "target_entity", "assigned_to", "due_at", "created_at", "updated_at", "resolved_at"},
    "financial_accounts": {"id", "organization_id", "qbo_id", "name", "fully_qualified_name", "account_type", "account_subtype", "active", "current_balance", "payload", "synced_at"},
    "financial_snapshots": {"id", "organization_id", "snapshot_type", "period_start", "period_end", "accounting_method", "payload", "captured_at"},
    "financial_sync_history": {"id", "organization_id", "status", "started_at", "completed_at", "duration_ms", "accounts_imported", "company_name", "error_message"},
    "quickbooks_oauth_credentials": {"id", "organization_id", "realm_id", "encrypted_refresh_token", "scopes", "connected_at", "updated_at"},
    "quickbooks_oauth_states": {"state", "organization_id", "identity_id", "created_at", "expires_at", "consumed_at"},
}

TENANT_TABLES = {
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
}

LEGACY_TENANT_OPTIONAL = {"organization_id"}
SYSTEM_TABLES = {"alembic_version"}
BASELINE_REVISION = "202607290001"
HEAD_REVISION = "head"


@dataclass(frozen=True)
class ValidationResult:
    status: str
    message: str
    stamp_revision: str | None = None

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2, sort_keys=True)


def _table_columns(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def validate_schema() -> ValidationResult:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    user_tables = tables - SYSTEM_TABLES

    if not user_tables:
        return ValidationResult(
            "empty",
            "Database has no Polaris tables. Run `alembic upgrade head` for a clean install.",
        )

    unknown_tables = user_tables - set(EXPECTED_COLUMNS)
    if unknown_tables:
        return ValidationResult(
            "unknown",
            "Database contains unknown tables and cannot be adopted automatically: "
            + ", ".join(sorted(unknown_tables)),
        )

    missing_tables = set(EXPECTED_COLUMNS) - user_tables
    if missing_tables:
        return ValidationResult(
            "partial",
            "Database is missing expected tables and cannot be stamped safely: "
            + ", ".join(sorted(missing_tables)),
        )

    current_compatible = True
    legacy_compatible = True
    details: list[str] = []

    for table_name, expected in EXPECTED_COLUMNS.items():
        actual = _table_columns(inspector, table_name)
        missing = expected - actual
        extra = actual - expected
        if extra:
            return ValidationResult(
                "unknown",
                f"Table {table_name} contains unexpected columns: " + ", ".join(sorted(extra)),
            )
        if missing:
            current_compatible = False
            allowed_missing = LEGACY_TENANT_OPTIONAL if table_name in TENANT_TABLES else set()
            if not missing.issubset(allowed_missing):
                legacy_compatible = False
            details.append(f"{table_name} missing {', '.join(sorted(missing))}")

    if current_compatible:
        return ValidationResult(
            "current-compatible",
            "Schema matches the current Polaris model inventory. Stamping head is permitted if alembic_version is absent.",
            HEAD_REVISION,
        )

    if legacy_compatible:
        return ValidationResult(
            "legacy-pre-tenant-compatible",
            "Schema matches the pre-tenant legacy shape. Stamp the baseline revision, then run `alembic upgrade head`. Details: "
            + "; ".join(details),
            BASELINE_REVISION,
        )

    return ValidationResult(
        "partial",
        "Schema is neither current nor compatible legacy: " + "; ".join(details),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Polaris database schema adoption safety")
    parser.add_argument("--stamp-if-safe", action="store_true", help="Stamp a current-compatible schema at head or legacy-compatible schema at the baseline revision")
    args = parser.parse_args()

    result = validate_schema()
    print(result.to_json())

    if args.stamp_if_safe:
        if result.stamp_revision is None:
            return 2
        command.stamp(_alembic_config(), result.stamp_revision)
    return 0 if result.status in {"empty", "current-compatible", "legacy-pre-tenant-compatible"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
