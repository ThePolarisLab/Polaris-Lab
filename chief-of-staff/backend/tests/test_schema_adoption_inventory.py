from __future__ import annotations

from app.connectors.outlook_credentials import OutlookOAuthCredential, OutlookOAuthState
from app.database.validate_schema import EXPECTED_COLUMNS, LEGACY_TABLE_OPTIONAL_COLUMNS, LEGACY_TENANT_OPTIONAL, TENANT_TABLES
from app.models.financial_snapshot import FinancialAccount, FinancialSnapshot, FinancialSyncHistory
from app.models.outlook import (
    OutlookAttachment,
    OutlookFolder,
    OutlookFolderCheckpoint,
    OutlookMessage,
    OutlookMessageClassification,
    OutlookSyncHistory,
)


def _model_columns(model) -> set[str]:
    return {column.name for column in model.__table__.columns}


def test_financial_cache_schema_adoption_inventory_matches_models():
    assert EXPECTED_COLUMNS["financial_accounts"] == _model_columns(FinancialAccount)
    assert EXPECTED_COLUMNS["financial_snapshots"] == _model_columns(FinancialSnapshot)
    assert EXPECTED_COLUMNS["financial_sync_history"] == _model_columns(FinancialSyncHistory)


def test_outlook_schema_adoption_inventory_matches_models():
    assert EXPECTED_COLUMNS["outlook_oauth_credentials"] == _model_columns(OutlookOAuthCredential)
    assert EXPECTED_COLUMNS["outlook_oauth_states"] == _model_columns(OutlookOAuthState)
    assert EXPECTED_COLUMNS["outlook_folders"] == _model_columns(OutlookFolder)
    assert EXPECTED_COLUMNS["outlook_folder_checkpoints"] == _model_columns(OutlookFolderCheckpoint)
    assert EXPECTED_COLUMNS["outlook_messages"] == _model_columns(OutlookMessage)
    assert EXPECTED_COLUMNS["outlook_attachments"] == _model_columns(OutlookAttachment)
    assert EXPECTED_COLUMNS["outlook_message_classifications"] == _model_columns(OutlookMessageClassification)
    assert EXPECTED_COLUMNS["outlook_sync_history"] == _model_columns(OutlookSyncHistory)


def test_outlook_tables_are_tenant_owned_in_inventory():
    assert {
        "outlook_oauth_credentials",
        "outlook_oauth_states",
        "outlook_folders",
        "outlook_folder_checkpoints",
        "outlook_messages",
        "outlook_attachments",
        "outlook_message_classifications",
        "outlook_sync_history",
    }.issubset(TENANT_TABLES)


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
