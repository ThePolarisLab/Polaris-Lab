from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

import pytest

from app.services.quickbooks_financial_sync import QuickBooksFinancialSyncService, QuickBooksSyncStageError


ORGANIZATION_ID = "org-mor-logistics"
REALM_ID = "realm-production-test"


@dataclass
class FakeCredential:
    realm_id: str = REALM_ID


class FakeStore:
    def __init__(self, fail_stage: str | None = None) -> None:
        self.fail_stage = fail_stage
        self.failures: list[str] = []
        self.successes = 0

    def load_credential(self) -> FakeCredential:
        if self.fail_stage == "load_stored_oauth_tokens":
            raise RuntimeError("credential load failed")
        return FakeCredential()

    def record_sync_failure(self, message: str, status: str | None = None) -> None:
        self.failures.append(message)

    def record_sync_success(self) -> None:
        self.successes += 1

    def metadata(self) -> dict[str, Any]:
        return {}


class FakeConnector:
    def __init__(self, fail_stage: str | None = None) -> None:
        self.fail_stage = fail_stage
        self._realm_id = REALM_ID

    def organization_sync_lock(self):
        return nullcontext()

    def authenticate(self) -> None:
        if self.fail_stage == "refresh_intuit_token_if_needed":
            raise RuntimeError("token refresh failed")

    def _http(self) -> object:
        if self.fail_stage == "build_quickbooks_client":
            raise RuntimeError("client build failed")
        return object()

    def company_info(self) -> dict[str, Any]:
        if self.fail_stage == "fetch_company_info":
            raise RuntimeError("company info failed")
        return {"CompanyName": "MOR LOGISTICS MANITOBA LIMITED"}

    def verify_company_identity(self) -> dict[str, Any]:
        if self.fail_stage == "verify_company_identity":
            raise RuntimeError("company verification failed")
        return {"verified_company_name": "MOR LOGISTICS MANITOBA LIMITED"}

    def list_all_resource(self, resource: str, *, changed_since: str | None = None) -> list[dict[str, Any]]:
        if self.fail_stage == f"fetch_{resource}":
            raise RuntimeError(f"{resource} failed")
        return [{"Id": f"{resource}-1", "MetaData": {"LastUpdatedTime": "2026-07-30T10:00:00Z"}}]

    def report(self, report_key: str, *, start_date=None, end_date=None) -> dict[str, Any]:
        if self.fail_stage == f"fetch_report_{report_key}":
            raise RuntimeError(f"{report_key} report failed")
        return {"Header": {"ReportName": report_key}, "Rows": {"Row": []}}


class FakeSession:
    def __init__(self, *, fail_commit: bool = False) -> None:
        self.fail_commit = fail_commit
        self.rollback_called = False
        self.close_called = False
        self.commit_called = False

    def commit(self) -> None:
        self.commit_called = True
        if self.fail_commit:
            raise RuntimeError("commit failed")

    def rollback(self) -> None:
        self.rollback_called = True

    def close(self) -> None:
        self.close_called = True


@pytest.fixture
def service_factory(monkeypatch):
    def build(fail_stage: str | None = None, *, db_session: FakeSession | None = None) -> QuickBooksFinancialSyncService:
        service = QuickBooksFinancialSyncService(ORGANIZATION_ID, connector=FakeConnector(fail_stage))
        service.store = FakeStore(fail_stage)
        monkeypatch.setattr(service, "_last_checkpoint", lambda: None)
        monkeypatch.setattr(service, "_start_history", lambda started_at, mode, checkpoint_before: 123)
        monkeypatch.setattr(service, "_record_failure", lambda history_id, timer, safe_message, sync_error: None)
        if db_session is not None:
            monkeypatch.setattr("app.services.quickbooks_financial_sync.SessionLocal", lambda: db_session)
        return service

    return build


@pytest.mark.parametrize(
    "stage",
    [
        "load_stored_oauth_tokens",
        "refresh_intuit_token_if_needed",
        "build_quickbooks_client",
        "fetch_company_info",
        "verify_company_identity",
        "fetch_accounts",
        "fetch_customers",
        "fetch_vendors",
        "fetch_items",
        "fetch_invoices",
        "fetch_payments",
        "fetch_bills",
        "fetch_purchases",
        "fetch_journal_entries",
        "fetch_report_profit_loss",
        "fetch_report_balance_sheet",
        "fetch_report_cash_flow",
        "fetch_report_aged_receivables",
        "fetch_report_aged_payables",
    ],
)
def test_sync_reports_stage_context_for_provider_failures(service_factory, stage):
    service = service_factory(stage)

    with pytest.raises(QuickBooksSyncStageError) as exc_info:
        service.sync(mode="incremental")

    error = exc_info.value
    assert error.stage == stage
    assert error.organization_id == ORGANIZATION_ID
    assert error.mode == "incremental"
    assert error.company_id == REALM_ID
    assert error.payload()["stage"] == stage
    assert "exception" in error.payload()


def test_sync_reports_write_to_database_stage(service_factory, monkeypatch):
    db_session = FakeSession()
    service = service_factory(db_session=db_session)
    monkeypatch.setattr(service, "_write_sync_payload", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("write failed")))

    with pytest.raises(QuickBooksSyncStageError) as exc_info:
        service.sync(mode="incremental")

    assert exc_info.value.stage == "write_to_database"
    assert exc_info.value.company_id == REALM_ID
    assert db_session.rollback_called is True
    assert db_session.close_called is True


def test_sync_reports_update_last_sync_stage(service_factory, monkeypatch):
    db_session = FakeSession()
    service = service_factory(db_session=db_session)
    monkeypatch.setattr(service, "_write_sync_payload", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_mark_history_success", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("history update failed")))

    with pytest.raises(QuickBooksSyncStageError) as exc_info:
        service.sync(mode="incremental")

    assert exc_info.value.stage == "update_last_sync"
    assert exc_info.value.company_id == REALM_ID
    assert db_session.rollback_called is True
    assert db_session.close_called is True


def test_sync_reports_commit_transaction_stage(service_factory, monkeypatch):
    db_session = FakeSession(fail_commit=True)
    service = service_factory(db_session=db_session)
    monkeypatch.setattr(service, "_write_sync_payload", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_mark_history_success", lambda *args, **kwargs: None)

    with pytest.raises(QuickBooksSyncStageError) as exc_info:
        service.sync(mode="incremental")

    assert exc_info.value.stage == "commit_transaction"
    assert exc_info.value.company_id == REALM_ID
    assert db_session.commit_called is True
    assert db_session.rollback_called is True
    assert db_session.close_called is True
