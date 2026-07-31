from __future__ import annotations

from app.database.validate_schema import EXPECTED_COLUMNS
from app.models.financial_snapshot import FinancialAccount, FinancialSnapshot, FinancialSyncHistory


def _model_columns(model) -> set[str]:
    return {column.name for column in model.__table__.columns}


def test_financial_cache_schema_adoption_inventory_matches_models():
    assert EXPECTED_COLUMNS["financial_accounts"] == _model_columns(FinancialAccount)
    assert EXPECTED_COLUMNS["financial_snapshots"] == _model_columns(FinancialSnapshot)
    assert EXPECTED_COLUMNS["financial_sync_history"] == _model_columns(FinancialSyncHistory)


def test_financial_sync_history_inventory_requires_organization_slug():
    assert "organization_slug" in EXPECTED_COLUMNS["financial_sync_history"]
