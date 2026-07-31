from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

from app.database.database import SessionLocal
from app.models.financial_snapshot import FinancialSyncHistory
from app.organizations.models import Organization
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
        return {
            "verified_company_name": "MOR LOGISTICS MANITOBA LIMITED",
            "identity_verification_status": "healthy",
        }

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


def _seed_organization(*, slug: str = "mor-logistics") -> str:
    organization_id = f"org-test-{uuid4().hex}"
    with SessionLocal.begin() as session:
        session.add(
            Organization(
                id=organization_id,
                slug=slug,
                display_name="MOR Logistics",
                legal_name="MOR LOGISTICS MANITOBA LIMITED",
            )
        )
    return organization_id


def _latest_history(organization_id: str) -> FinancialSyncHistory:
    with SessionLocal() as session:
        history = (
            session.query(FinancialSyncHistory)
            .filter_by(organization_id=organization_id)
            .order_by(FinancialSyncHistory.started_at.desc())
            .first()
        )
        assert history is not None
        session.expunge(history)
        return history


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


def test_start_history_populates_organization_slug_from_matching_organization_row():
    organization_id = _seed_organization(slug="mor-logistics")
    service = QuickBooksFinancialSyncService(organization_id, connector=FakeConnector())

    history_id = service._start_history(datetime.now(timezone.utc), "incremental", None)

    with SessionLocal() as session:
        history = session.get(FinancialSyncHistory, history_id)
        assert history is not None
        assert history.organization_id == organization_id
        assert history.organization_slug == "mor-logistics"
        assert history.status == "running"
        assert history.sync_mode == "incremental"


def test_start_history_rejects_missing_or_blank_organization_slug():
    missing_service = QuickBooksFinancialSyncService("org-missing", connector=FakeConnector())
    blank_slug_organization_id = _seed_organization(slug="")
    blank_slug_service = QuickBooksFinancialSyncService(blank_slug_organization_id, connector=FakeConnector())

    with pytest.raises(RuntimeError, match="was not found"):
        missing_service._start_history(datetime.now(timezone.utc), "incremental", None)
    with pytest.raises(RuntimeError, match="has no slug"):
        blank_slug_service._start_history(datetime.now(timezone.utc), "incremental", None)


def test_failed_sync_history_preserves_organization_slug(monkeypatch):
    organization_id = _seed_organization(slug="mor-logistics")
    service = QuickBooksFinancialSyncService(organization_id, connector=FakeConnector("fetch_company_info"))
    service.store = FakeStore()
    monkeypatch.setattr(service, "_last_checkpoint", lambda: None)

    with pytest.raises(QuickBooksSyncStageError):
        service.sync(mode="incremental")

    history = _latest_history(organization_id)
    assert history.organization_slug == "mor-logistics"
    assert history.status == "failed"
    assert history.completed_at is not None
    assert "fetch_company_info" in str(history.error_message)


def test_successful_sync_history_preserves_slug_and_updates_last_sync(monkeypatch):
    organization_id = _seed_organization(slug="mor-logistics")
    service = QuickBooksFinancialSyncService(organization_id, connector=FakeConnector())
    service.store = FakeStore()
    monkeypatch.setattr(service, "_write_sync_payload", lambda *args, **kwargs: None)

    result = service.sync(mode="incremental")

    history = _latest_history(organization_id)
    assert history.organization_slug == "mor-logistics"
    assert history.status == "success"
    assert history.completed_at is not None
    assert result["last_sync"] == history.completed_at.isoformat()
    assert result["sync_mode"] == "incremental"


def test_sync_history_slug_cannot_be_borrowed_from_another_tenant():
    first_org = _seed_organization(slug="mor-logistics")
    second_org = _seed_organization(slug="other-tenant")

    first_history_id = QuickBooksFinancialSyncService(first_org, connector=FakeConnector())._start_history(
        datetime.now(timezone.utc),
        "incremental",
        None,
    )
    second_history_id = QuickBooksFinancialSyncService(second_org, connector=FakeConnector())._start_history(
        datetime.now(timezone.utc),
        "incremental",
        None,
    )

    with SessionLocal() as session:
        first_history = session.get(FinancialSyncHistory, first_history_id)
        second_history = session.get(FinancialSyncHistory, second_history_id)
        assert first_history is not None
        assert second_history is not None
        assert first_history.organization_id == first_org
        assert first_history.organization_slug == "mor-logistics"
        assert second_history.organization_id == second_org
        assert second_history.organization_slug == "other-tenant"
