from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import time

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./polaris-torqueai-scheduled-sync-test.db")
os.environ.setdefault("POLARIS_ENV", "test")
os.environ.setdefault("POLARIS_LOCAL_AUTH_SECRET", "test-local-auth-secret-with-enough-length")
os.environ.setdefault("POLARIS_QBO_CLIENT_ID", "client-id")
os.environ.setdefault("POLARIS_QBO_CLIENT_SECRET", "client-secret")
os.environ.setdefault("POLARIS_QBO_REDIRECT_URI", "http://localhost:8000/api/v1/connectors/quickbooks/oauth/callback")
os.environ.setdefault("POLARIS_QBO_OAUTH_STATE_SECRET", "quickbooks-state-secret-with-enough-length")
os.environ.setdefault("POLARIS_QBO_TOKEN_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

from fastapi.testclient import TestClient

from app.connectors import torqueai
from app.connectors.torqueai import TorqueAIConnector
from app.connectors.torqueai_scheduler import (
    SCHEDULED_ORGANIZATION_ENV_VAR,
    SCHEDULED_SYNC_ENABLED_ENV_VAR,
    TorqueAIScheduledSyncError,
    run_scheduled_torqueai_dispatch_sync,
)
from app.database.database import Base, SessionLocal, engine
from app.main import app
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchSyncRun, TorqueAIDispatchSyncState
from app.organizations.models import Organization
from app.security.job_auth import sign_job_request

TRIGGER_SECRET_ENV = "POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET"
TRIGGER_SECRET = "scheduled-torqueai-test-secret"
PATH = "/api/v1/internal/torqueai/dispatches/scheduled-sync"
BASE_URL = "https://morlogistics.kordovatek.com"


@pytest.fixture(autouse=True)
def reset_database(monkeypatch: pytest.MonkeyPatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal.begin() as session:
        session.add(Organization(id="org-1", slug="mor", display_name="MOR"))
        session.add(Organization(id="org-2", slug="other", display_name="Other"))

    for name in (
        SCHEDULED_SYNC_ENABLED_ENV_VAR,
        SCHEDULED_ORGANIZATION_ENV_VAR,
        TRIGGER_SECRET_ENV,
        torqueai.TORQUEAI_API_TOKEN_ENV,
        torqueai.TORQUEAI_BASE_URL_ENV,
        torqueai.TORQUEAI_ORGANIZATION_SLUG_ENV,
    ):
        monkeypatch.delenv(name, raising=False)

    yield

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def _fixed_timestamp() -> int:
    return int(datetime(2026, 8, 29, 5, 17, tzinfo=timezone.utc).timestamp())


def _configure_scheduled_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SCHEDULED_SYNC_ENABLED_ENV_VAR, "true")
    monkeypatch.setenv(SCHEDULED_ORGANIZATION_ENV_VAR, "mor")
    monkeypatch.setenv(torqueai.TORQUEAI_ORGANIZATION_SLUG_ENV, "mor")
    monkeypatch.setenv(torqueai.TORQUEAI_API_TOKEN_ENV, "tk_scheduled_test_secret")
    monkeypatch.setenv(torqueai.TORQUEAI_BASE_URL_ENV, BASE_URL)


def _payload(*, request_from: str = "2026-08-23", request_to: str = "2026-08-29") -> dict:
    return {
        "data": [
            {
                "loadNumber": 9001,
                "orderNumber": "ORD-9001",
                "status": "dispatched",
                "orderDate": "2026-08-28",
                "shipDate": "2026-08-30",
                "deliveryDate": "2026-09-01",
                "customerName": "Sensitive Customer",
                "dispatcherName": "Sensitive Dispatcher",
                "driverName": "Sensitive Driver",
                "carrierName": "Sensitive Carrier",
                "truckNumber": "T-9001",
                "trailerNumber": "R-9001",
                "loadedMiles": 450.0,
                "totalCharge": 12345.67,
                "stops": [{"address": "Sensitive Address"}],
            }
        ],
        "totalCount": 1,
        "page": 1,
        "itemsPerPage": 100,
        "dateRange": {"from": request_from, "to": request_to},
    }


def _install_mock_http(monkeypatch: pytest.MonkeyPatch, handler) -> httpx.Client:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(TorqueAIConnector, "_http", lambda _self: http_client)
    return http_client


def _signed_headers(*, body: bytes = b"") -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        "X-Polaris-Job-Timestamp": timestamp,
        "X-Polaris-Job-Signature": sign_job_request(
            method="POST",
            path=PATH,
            body=body,
            timestamp=timestamp,
            secret=TRIGGER_SECRET,
        ),
    }


def test_machine_endpoint_is_hmac_only_disabled_by_default_and_rejects_body(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def provider_must_not_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not be called")

    monkeypatch.setattr(TorqueAIConnector, "fetch_dispatches", provider_must_not_run)
    monkeypatch.setenv(TRIGGER_SECRET_ENV, TRIGGER_SECRET)

    assert client.post(PATH).status_code == 401

    disabled = client.post(PATH, headers=_signed_headers())
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert disabled.json()["dispatch_claimed"] is False
    assert disabled.json()["secrets_exposed"] is False

    body = b'{"organization":"other","date":"2026-01-01","retry":true}'
    rejected = client.post(PATH, headers=_signed_headers(body=body), content=body)
    assert rejected.status_code == 400
    assert "other" not in rejected.text
    assert calls == 0

    with SessionLocal() as session:
        assert session.query(TorqueAIDispatchSyncRun).count() == 0


def test_scheduled_tenant_scope_mismatch_fails_before_claim_or_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_scheduled_sync(monkeypatch)
    monkeypatch.setenv(torqueai.TORQUEAI_ORGANIZATION_SLUG_ENV, "other")
    calls = 0

    def provider_must_not_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not be called")

    monkeypatch.setattr(TorqueAIConnector, "fetch_dispatches", provider_must_not_run)

    with SessionLocal() as session:
        with pytest.raises(TorqueAIScheduledSyncError) as exc_info:
            run_scheduled_torqueai_dispatch_sync(session, trigger_timestamp=_fixed_timestamp())

    assert exc_info.value.code == "organization_scope_mismatch"
    assert calls == 0
    with SessionLocal() as session:
        assert session.query(TorqueAIDispatchSyncRun).count() == 0


def test_first_hourly_claim_executes_once_and_duplicate_trigger_is_provider_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_scheduled_sync(monkeypatch)
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "GET"
        assert request.url.path == torqueai.TORQUEAI_DISPATCH_PATH
        assert request.url.params == httpx.QueryParams(
            {"from": "2026-08-23", "to": "2026-08-29", "page": "1", "limit": "100"}
        )
        return httpx.Response(200, json=_payload())

    http_client = _install_mock_http(monkeypatch, handler)
    try:
        with SessionLocal() as session:
            first = run_scheduled_torqueai_dispatch_sync(session, trigger_timestamp=_fixed_timestamp())
        with SessionLocal() as session:
            duplicate = run_scheduled_torqueai_dispatch_sync(session, trigger_timestamp=_fixed_timestamp())
    finally:
        http_client.close()

    assert first.status == "executed"
    assert first.dispatch_claimed is True
    assert first.rows_inserted == 1
    assert duplicate.status == "already_claimed"
    assert duplicate.dispatch_claimed is False
    assert len(calls) == 1

    with SessionLocal() as session:
        run = session.query(TorqueAIDispatchSyncRun).one()
        assert run.status == "success"
        assert run.trigger_mode == "scheduled"
        assert run.trigger_slot == "2026-08-29T05:00:00Z"
        assert run.requested_from.isoformat() == "2026-08-23"
        assert run.requested_to.isoformat() == "2026-08-29"
        assert run.rows_inserted == 1

        state = session.query(TorqueAIDispatchSyncState).one()
        assert state.last_successful_run_id == run.run_id
        assert session.query(TorqueAIDispatch).count() == 1


def test_failed_provider_attempt_consumes_slot_and_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_scheduled_sync(monkeypatch)
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, json={"message": "sensitive provider body"})

    http_client = _install_mock_http(monkeypatch, handler)
    try:
        with SessionLocal() as session:
            first = run_scheduled_torqueai_dispatch_sync(session, trigger_timestamp=_fixed_timestamp())
        with SessionLocal() as session:
            duplicate = run_scheduled_torqueai_dispatch_sync(session, trigger_timestamp=_fixed_timestamp())
    finally:
        http_client.close()

    assert first.status == "failed"
    assert first.dispatch_claimed is True
    assert first.error_code is not None
    assert duplicate.status == "already_claimed"
    assert calls == 1

    with SessionLocal() as session:
        run = session.query(TorqueAIDispatchSyncRun).one()
        assert run.status == "failed"
        assert run.error_code == first.error_code
        assert run.trigger_slot == "2026-08-29T05:00:00Z"
        assert session.query(TorqueAIDispatch).count() == 0
        assert session.query(TorqueAIDispatchSyncState).count() == 0


def test_stage_two_workflow_enables_hourly_schedule_and_has_no_provider_secrets() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workflow = (repo_root / ".github" / "workflows" / "torqueai-dispatch-sync.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "schedule:" in workflow
    assert '- cron: "17 * * * *"' in workflow
    assert workflow.count("cron:") == 1
    assert "torqueai-dispatch-sync-production" in workflow
    assert "POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET" in workflow
    assert "POLARIS_PRODUCTION_API_URL" in workflow
    assert PATH in workflow
    assert "POLARIS_TORQUEAI_API_TOKEN" not in workflow
    assert "POLARIS_TORQUEAI_BASE_URL" not in workflow
    assert "POLARIS_TORQUEAI_ORGANIZATION_SLUG" not in workflow
    assert "DATABASE_URL" not in workflow
