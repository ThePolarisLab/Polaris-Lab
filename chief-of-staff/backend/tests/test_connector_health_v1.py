from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.connectors.quickbooks import QuickBooksConnector
from app.database.database import SessionLocal
from app.main import app
from app.models.torqueai import TorqueAIDispatchSyncRun, TorqueAIDispatchSyncState
from tests.auth_helpers import seed_principal


def test_quickbooks_generic_status_is_passive_and_does_not_call_provider_health(monkeypatch: pytest.MonkeyPatch) -> None:
    _organization, _identity, headers = seed_principal("owner")
    provider_health_calls = 0

    def forbidden_health(self):
        nonlocal provider_health_calls
        provider_health_calls += 1
        raise AssertionError("QuickBooks status read must not call provider health")

    def safe_status(self, *, include_resources: bool = False):
        return {
            "expected_company_name": "MOR LOGISTICS MANITOBA LIMITED",
            "verified_company_name": "MOR LOGISTICS MANITOBA LIMITED",
            "identity_verification_status": "healthy",
            "authorization_status": "authorized",
            "last_successful_sync_time": "2026-08-30T20:00:00+00:00",
            "reauthorization_required": False,
            "read_only": True,
            "secrets_exposed": False,
            "resources": ["company"] if include_resources else None,
        }

    monkeypatch.setattr(QuickBooksConnector, "health", forbidden_health)
    monkeypatch.setattr(QuickBooksConnector, "safe_status", safe_status)

    response = TestClient(app).get("/api/v1/connectors/quickbooks", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["details"]["authorization_status"] == "authorized"
    assert payload["details"]["identity_verification_status"] == "healthy"
    assert payload["details"]["secrets_exposed"] is False
    assert provider_health_calls == 0


def test_torqueai_status_reads_durable_sync_state_only_and_is_tenant_scoped() -> None:
    organization, _identity, headers = seed_principal("owner")
    other_organization, _other_identity, _other_headers = seed_principal("owner")
    completed_at = datetime(2026, 8, 30, 23, 24, tzinfo=timezone.utc)

    session = SessionLocal()
    try:
        session.add_all(
            [
                TorqueAIDispatchSyncRun(
                    run_id="torque-health-success",
                    organization_id=organization["id"],
                    requested_from=date(2026, 8, 30),
                    requested_to=date(2026, 8, 30),
                    page_size=100,
                    status="success",
                    trigger_mode="scheduled",
                    trigger_slot="2026-08-30T23:00:00Z",
                    pages_fetched=1,
                    provider_total_count=31,
                    rows_validated=31,
                    rows_inserted=0,
                    rows_updated=1,
                    rows_unchanged=30,
                    error_code=None,
                    started_at=completed_at,
                    completed_at=completed_at,
                ),
                TorqueAIDispatchSyncState(
                    organization_id=organization["id"],
                    last_successful_window_start=date(2026, 8, 30),
                    last_successful_window_end=date(2026, 8, 30),
                    last_successful_run_id="torque-health-success",
                    last_successful_completed_at=completed_at,
                ),
                TorqueAIDispatchSyncRun(
                    run_id="torque-other-failure",
                    organization_id=other_organization["id"],
                    requested_from=date(2026, 8, 30),
                    requested_to=date(2026, 8, 30),
                    page_size=100,
                    status="failed",
                    trigger_mode="scheduled",
                    trigger_slot="2026-08-30T23:00:00Z",
                    pages_fetched=0,
                    provider_total_count=None,
                    rows_validated=0,
                    rows_inserted=0,
                    rows_updated=0,
                    rows_unchanged=0,
                    error_code="token_missing",
                    started_at=completed_at,
                    completed_at=completed_at,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    response = TestClient(app).get("/api/v1/torqueai/status", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["health"]["status"] == "healthy"
    assert payload["status"]["latest_run_status"] == "success"
    assert payload["status"]["latest_run_trigger_mode"] == "scheduled"
    assert payload["status"]["last_successful_run_id"] == "torque-health-success"
    assert payload["status"]["provider_called"] is False
    assert payload["status"]["tenant_scope_validated"] is True
    assert payload["status"]["secrets_exposed"] is False
    assert "torque-other-failure" not in response.text
    assert "token_missing" not in response.text
    assert other_organization["id"] not in response.text


def test_torqueai_status_reports_degraded_latest_run_without_erasing_prior_success() -> None:
    organization, _identity, headers = seed_principal("viewer")
    prior_success = datetime(2026, 8, 30, 22, 24, tzinfo=timezone.utc)
    failed_at = datetime(2026, 8, 30, 23, 24, tzinfo=timezone.utc)

    session = SessionLocal()
    try:
        session.add_all(
            [
                TorqueAIDispatchSyncState(
                    organization_id=organization["id"],
                    last_successful_window_start=date(2026, 8, 30),
                    last_successful_window_end=date(2026, 8, 30),
                    last_successful_run_id="torque-prior-success",
                    last_successful_completed_at=prior_success,
                ),
                TorqueAIDispatchSyncRun(
                    run_id="torque-latest-failed",
                    organization_id=organization["id"],
                    requested_from=date(2026, 8, 30),
                    requested_to=date(2026, 8, 30),
                    page_size=100,
                    status="failed",
                    trigger_mode="scheduled",
                    trigger_slot="2026-08-30T23:00:00Z",
                    pages_fetched=0,
                    provider_total_count=None,
                    rows_validated=0,
                    rows_inserted=0,
                    rows_updated=0,
                    rows_unchanged=0,
                    error_code="provider_unavailable",
                    started_at=failed_at,
                    completed_at=failed_at,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    response = TestClient(app).get("/api/v1/torqueai/status", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["health"]["status"] == "degraded"
    assert "prior successful durable data remains available" in payload["health"]["message"]
    assert payload["status"]["latest_run_error_code"] == "provider_unavailable"
    assert payload["status"]["last_successful_run_id"] == "torque-prior-success"
