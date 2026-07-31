from __future__ import annotations

from app.database.validate_schema import EXPECTED_COLUMNS, LEGACY_TABLE_OPTIONAL_COLUMNS, LEGACY_TENANT_OPTIONAL
from app.models.financial_snapshot import FinancialAccount, FinancialSnapshot, FinancialSyncHistory


def _model_columns(model) -> set[str]:
    return {column.name for column in model.__table__.columns}


def test_financial_cache_schema_adoption_inventory_matches_models():
    assert EXPECTED_COLUMNS["financial_accounts"] == _model_columns(FinancialAccount)
    assert EXPECTED_COLUMNS["financial_snapshots"] == _model_columns(FinancialSnapshot)
    assert EXPECTED_COLUMNS["financial_sync_history"] == _model_columns(FinancialSyncHistory)


def test_financial_sync_history_inventory_requires_organization_slug():
    assert "organization_slug" in EXPECTED_COLUMNS["financial_sync_history"]


def test_legacy_financial_cache_inventory_allows_only_migration_added_columns():
    assert LEGACY_TENANT_OPTIONAL == {"organization_id"}
    assert LEGACY_TABLE_OPTIONAL_COLUMNS["financial_accounts"] == {"organization_slug"}
    assert LEGACY_TABLE_OPTIONAL_COLUMNS["financial_snapshots"] == {"organization_slug"}
    assert LEGACY_TABLE_OPTIONAL_COLUMNS["financial_sync_history"] == {
        "organization_slug",
        "sync_mode",
        "resource_counts",
        "report_availability",
        "checkpoint_before",
        "checkpoint_after",
        "verification_status",
    }
