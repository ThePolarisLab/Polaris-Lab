from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api.connector_freshness as freshness_api
from app.database.database import SessionLocal
from app.main import app
from app.models.motive import MotiveSyncCheckpoint, MotiveSyncHistory
from app.models.torqueai import TorqueAIDispatchSyncRun
from tests.auth_helpers import seed_principal


def _enable_motive_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED", "true")
    monkeypatch.setenv("MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED", "true")


def _torque_run(
    organization_id: str,
    *,
    run_id: str,
    status: str,
    started_at: datetime,
    completed_at: datetime | None,
    trigger_slot: str,
    error_code: str | None = None,
) -> TorqueAIDispatchSyncRun:
    return TorqueAIDispatchSyncRun(
        run_id=run_id,
        organization_id=organization_id,
        requested_from=date(2026, 8, 25),
        requested_to=date(2026, 8, 31),
        page_size=100,
        status=status,
        trigger_mode="scheduled",
        trigger_slot=trigger_slot,
        pages_fetched=1 if status == "success" else 0,
        provider_total_count=20 if status == "success" else None,
        rows_validated=20 if status == "success" else 0,
        rows_inserted=0,
        rows_updated=0,
        rows_unchanged=20 if status == "success" else 0,
        error_code=error_code,
        started_at=started_at,
        completed_at=completed_at,
    )


def _motive_history(
    organization: dict,
    *,
    run_id: str,
    status: str,
    started_at: datetime,
    completed_at: datetime,
    error_code: str | None = None,
) -> MotiveSyncHistory:
    return MotiveSyncHistory(
        organization_id=organization["id"],
        organization_slug=organization["slug"],
        provider="motive",
        provider_resource="vehicle_utilization",
        mode="production_recent_window_ingestion",
        status=status,
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at,
        records_read=10 if status == "success" else 0,
        records_written=0,
        error_code=error_code,
        error_message_sanitized=None if status == "success" else "Sanitized production failure.",
        checkpoint_before={},
        checkpoint_after={},
        resource_counts={},
    )


def _motive_checkpoint(
    organization: dict,
    *,
    completed_through: str,
    synced_at: datetime,
) -> MotiveSyncCheckpoint:
    return MotiveSyncCheckpoint(
        organization_id=organization["id"],
        organization_slug=organization["slug"],
        provider="motive",
        provider_resource="vehicle_utilization",
        checkpoint_status="success",
        last_successful_position={
            "completed_through": completed_through,
            "request_timezone": "America/Chicago",
            "unit_request_mode": "imperial",
        },
        last_successful_sync_at=synced_at,
    )


def _scheduler_claim(organization: dict, *, local_date: str, claimed_at: datetime) -> MotiveSyncCheckpoint:
    return MotiveSyncCheckpoint(
        organization_id=organization["id"],
        organization_slug=organization["slug"],
        provider="motive",
        provider_resource="vehicle_utilization_scheduler_dispatch",
        checkpoint_status="claimed",
        last_successful_position={
            "claimed_local_date": local_date,
            "request_timezone": "America/Chicago",
            "scheduler_mode": "scheduled_production_ingestion",
        },
        last_successful_sync_at=claimed_at,
    )


def _get(headers: dict[str, str]):
    return TestClient(app).get("/api/v1/system/connector-freshness", headers=headers)


def test_current_scheduled_freshness_is_tenant_scoped_and_passive(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, headers = seed_principal("owner")
    other_organization, _other_identity, _other_headers = seed_principal("owner")
    fixed_now = datetime(2026, 8, 31, 17, 30, tzinfo=timezone.utc)  # 12:30 America/Chicago
    monkeypatch.setattr(freshness_api, "_now_utc", lambda: fixed_now)
    _enable_motive_scheduler(monkeypatch)

    session = SessionLocal()
    try:
        session.add_all(
            [
                _torque_run(
                    organization["id"],
                    run_id="torque-current",
                    status="success",
                    started_at=datetime(2026, 8, 31, 16, 40, tzinfo=timezone.utc),
                    completed_at=datetime(2026, 8, 31, 16, 45, tzinfo=timezone.utc),
                    trigger_slot="2026-08-31T16:00:00Z",
                ),
                _motive_history(
                    organization,
                    run_id="motive-current",
                    status="success",
                    started_at=datetime(2026, 8, 31, 16, 0, tzinfo=timezone.utc),
                    completed_at=datetime(2026, 8, 31, 16, 20, tzinfo=timezone.utc),
                ),
                _motive_checkpoint(
                    organization,
                    completed_through="2026-08-30",
                    synced_at=datetime(2026, 8, 31, 16, 20, tzinfo=timezone.utc),
                ),
                _scheduler_claim(
                    organization,
                    local_date="2026-08-31",
                    claimed_at=datetime(2026, 8, 31, 16, 0, tzinfo=timezone.utc),
                ),
                _torque_run(
                    other_organization["id"],
                    run_id="torque-other-failed",
                    status="failed",
                    started_at=datetime(2026, 8, 31, 17, 0, tzinfo=timezone.utc),
                    completed_at=datetime(2026, 8, 31, 17, 1, tzinfo=timezone.utc),
                    trigger_slot="2026-08-31T17:00:00Z",
                    error_code="other_tenant_error",
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    response = _get(headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_called"] is False
    assert payload["tenant_scope_validated"] is True
    assert payload["secrets_exposed"] is False
    assert payload["manual_connectors"]["quickbooks"]["stale_threshold_minutes"] is None
    assert payload["torqueai"]["freshness_status"] == "current"
    assert payload["torqueai"]["freshness_age_minutes"] == 45
    assert payload["torqueai"]["latest_run_error_code"] is None
    assert payload["motive_vehicle_utilization"]["freshness_status"] == "current"
    assert payload["motive_vehicle_utilization"]["completed_through"] == "2026-08-30"
    assert payload["motive_vehicle_utilization"]["expected_completed_through"] == "2026-08-30"
    assert "other_tenant_error" not in response.text
    assert other_organization["id"] not in response.text


def test_scheduled_freshness_marks_missed_windows_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, headers = seed_principal("owner")
    fixed_now = datetime(2026, 8, 31, 20, 30, tzinfo=timezone.utc)  # 15:30 America/Chicago
    monkeypatch.setattr(freshness_api, "_now_utc", lambda: fixed_now)
    _enable_motive_scheduler(monkeypatch)

    session = SessionLocal()
    try:
        session.add_all(
            [
                _torque_run(
                    organization["id"],
                    run_id="torque-stale",
                    status="success",
                    started_at=datetime(2026, 8, 31, 16, 55, tzinfo=timezone.utc),
                    completed_at=datetime(2026, 8, 31, 17, 0, tzinfo=timezone.utc),
                    trigger_slot="2026-08-31T16:00:00Z",
                ),
                _motive_history(
                    organization,
                    run_id="motive-old-success",
                    status="success",
                    started_at=datetime(2026, 8, 30, 17, 0, tzinfo=timezone.utc),
                    completed_at=datetime(2026, 8, 30, 17, 20, tzinfo=timezone.utc),
                ),
                _motive_checkpoint(
                    organization,
                    completed_through="2026-08-29",
                    synced_at=datetime(2026, 8, 30, 17, 20, tzinfo=timezone.utc),
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    response = _get(headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["torqueai"]["freshness_status"] == "stale"
    assert payload["torqueai"]["freshness_age_minutes"] == 210
    assert payload["torqueai"]["stale_after_minutes"] == 120
    assert payload["motive_vehicle_utilization"]["freshness_status"] == "stale"
    assert payload["motive_vehicle_utilization"]["freshness_lag_days"] == 1
    assert "acceptance window has ended" in payload["motive_vehicle_utilization"]["recovery"]


def test_latest_scheduled_failures_surface_sanitized_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, headers = seed_principal("owner")
    fixed_now = datetime(2026, 8, 31, 17, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(freshness_api, "_now_utc", lambda: fixed_now)
    _enable_motive_scheduler(monkeypatch)

    session = SessionLocal()
    try:
        session.add_all(
            [
                _torque_run(
                    organization["id"],
                    run_id="torque-prior-success",
                    status="success",
                    started_at=datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc),
                    completed_at=datetime(2026, 8, 31, 15, 5, tzinfo=timezone.utc),
                    trigger_slot="2026-08-31T15:00:00Z",
                ),
                _torque_run(
                    organization["id"],
                    run_id="torque-latest-failure",
                    status="failed",
                    started_at=datetime(2026, 8, 31, 17, 0, tzinfo=timezone.utc),
                    completed_at=datetime(2026, 8, 31, 17, 2, tzinfo=timezone.utc),
                    trigger_slot="2026-08-31T17:00:00Z",
                    error_code="provider_rate_limited",
                ),
                _motive_checkpoint(
                    organization,
                    completed_through="2026-08-29",
                    synced_at=datetime(2026, 8, 30, 17, 20, tzinfo=timezone.utc),
                ),
                _scheduler_claim(
                    organization,
                    local_date="2026-08-31",
                    claimed_at=datetime(2026, 8, 31, 16, 0, tzinfo=timezone.utc),
                ),
                _motive_history(
                    organization,
                    run_id="motive-latest-failure",
                    status="partial",
                    started_at=datetime(2026, 8, 31, 16, 5, tzinfo=timezone.utc),
                    completed_at=datetime(2026, 8, 31, 16, 30, tzinfo=timezone.utc),
                    error_code="provider_contract_error",
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    response = _get(headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["torqueai"]["freshness_status"] == "failed"
    assert payload["torqueai"]["latest_run_error_code"] == "provider_rate_limited"
    assert "next hourly slot" in payload["torqueai"]["recovery"]
    assert payload["motive_vehicle_utilization"]["freshness_status"] == "failed"
    assert payload["motive_vehicle_utilization"]["latest_attempt_error_code"] == "provider_contract_error"
    assert "same local-day dispatch claim" in payload["motive_vehicle_utilization"]["recovery"]
    assert "token" not in response.text.lower()
    assert "secret" not in response.text.lower().replace('"secrets_exposed":false', "")


def test_freshness_module_has_no_provider_call_or_mutation_path() -> None:
    source = Path("app/api/connector_freshness.py").read_text(encoding="utf-8")
    assert "httpx" not in source
    assert "fetch_dispatches" not in source
    assert "request_vehicle_utilization_page" not in source
    assert "run_vehicle_utilization_production_ingestion" not in source
    assert ".commit(" not in source
    assert ".add(" not in source
    assert "session.delete" not in source
