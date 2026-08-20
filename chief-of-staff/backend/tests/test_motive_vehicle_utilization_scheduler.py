import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./polaris-motive-scheduler-test.db")
os.environ.setdefault("POLARIS_ENV", "test")
os.environ.setdefault("POLARIS_LOCAL_AUTH_SECRET", "test-local-auth-secret-with-enough-length")
os.environ.setdefault("POLARIS_QBO_CLIENT_ID", "client-id")
os.environ.setdefault("POLARIS_QBO_CLIENT_SECRET", "client-secret")
os.environ.setdefault("POLARIS_QBO_REDIRECT_URI", "http://localhost:8000/api/v1/connectors/quickbooks/oauth/callback")
os.environ.setdefault("POLARIS_QBO_OAUTH_STATE_SECRET", "quickbooks-state-secret-with-enough-length")
os.environ.setdefault("POLARIS_QBO_TOKEN_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

from fastapi.testclient import TestClient

from app.database.database import Base, SessionLocal, engine
from app.main import app
from app.models.motive import MotiveSyncCheckpoint
from app.motive.vehicle_utilization_production_ingestion import MotiveVehicleUtilizationProductionIngestionError
from app.motive.vehicle_utilization_scheduler import (
    SCHEDULER_DISPATCH_RESOURCE,
    MotiveVehicleUtilizationSchedulerError,
    inside_schedule_window,
    resolve_scheduled_organization,
    run_scheduled_vehicle_utilization,
    scheduler_local_now,
)
from app.organizations.models import Organization
from app.security.job_auth import sign_job_request


@pytest.fixture(autouse=True)
def reset_database(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal.begin() as session:
        session.add(Organization(id="org-1", slug="mor", display_name="MOR"))
        session.add(Organization(id="org-2", slug="other", display_name="Other"))
    for name in (
        "MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED",
        "MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED",
        "MOTIVE_VEHICLE_UTILIZATION_SCHEDULER_CONTROLLED_VALIDATION_WINDOW_ENABLED",
        "POLARIS_MOTIVE_UTILIZATION_SCHEDULED_ORGANIZATION_SLUG",
        "POLARIS_MOTIVE_UTILIZATION_CRON_TRIGGER_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def _scheduled_time():
    return datetime(2026, 8, 19, 11, 17, tzinfo=timezone.utc)


def _headers(secret="scheduled-secret", *, body=b""):
    timestamp = str(int(_scheduled_time().timestamp()))
    path = "/api/v1/internal/motive/vehicle-utilization/run"
    return {
        "X-Polaris-Job-Timestamp": timestamp,
        "X-Polaris-Job-Signature": sign_job_request(
            method="POST", path=path, body=body, timestamp=timestamp, secret=secret
        ),
    }


def test_scheduler_and_ingestion_gates_fail_closed_before_orchestrator(monkeypatch):
    import app.motive.vehicle_utilization_scheduler as scheduler

    calls = []
    monkeypatch.setattr(scheduler, "run_vehicle_utilization_production_ingestion", lambda *a, **k: calls.append(1))

    with SessionLocal() as session:
        result = run_scheduled_vehicle_utilization(session, now=_scheduled_time())
    assert result.status == "disabled"
    assert result.error_code == "scheduler_disabled"
    assert calls == []

    monkeypatch.setenv("MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED", "true")
    with SessionLocal() as session:
        result = run_scheduled_vehicle_utilization(session, now=_scheduled_time())
    assert result.status == "disabled"
    assert result.error_code == "production_ingestion_disabled"
    assert calls == []


def test_local_time_gate_uses_iana_dst_rules():
    summer = datetime(2026, 7, 15, 11, 17, tzinfo=timezone.utc)
    winter = datetime(2026, 1, 15, 12, 17, tzinfo=timezone.utc)
    wrong_summer_trigger = datetime(2026, 7, 15, 12, 17, tzinfo=timezone.utc)
    wrong_winter_trigger = datetime(2026, 1, 15, 11, 17, tzinfo=timezone.utc)

    assert scheduler_local_now(now=summer).hour == 6
    assert scheduler_local_now(now=winter).hour == 6
    assert inside_schedule_window(now=summer) is True
    assert inside_schedule_window(now=winter) is True
    assert inside_schedule_window(now=wrong_summer_trigger) is False
    assert inside_schedule_window(now=wrong_winter_trigger) is False


def test_controlled_validation_window_is_11am_through_11pm_local(monkeypatch):
    monkeypatch.setenv(
        "MOTIVE_VEHICLE_UTILIZATION_SCHEDULER_CONTROLLED_VALIDATION_WINDOW_ENABLED", "true"
    )

    before_window = datetime(2026, 8, 19, 15, 59, tzinfo=timezone.utc)
    start_window = datetime(2026, 8, 19, 16, 0, tzinfo=timezone.utc)
    end_window = datetime(2026, 8, 20, 4, 59, tzinfo=timezone.utc)
    after_window = datetime(2026, 8, 20, 5, 0, tzinfo=timezone.utc)

    assert scheduler_local_now(now=start_window).hour == 11
    assert scheduler_local_now(now=end_window).hour == 23
    assert inside_schedule_window(now=before_window) is False
    assert inside_schedule_window(now=start_window) is True
    assert inside_schedule_window(now=end_window) is True
    assert inside_schedule_window(now=after_window) is False


def test_configured_organization_must_be_active_and_exact(monkeypatch):
    with SessionLocal() as session:
        with pytest.raises(MotiveVehicleUtilizationSchedulerError, match="not configured"):
            resolve_scheduled_organization(session)
        monkeypatch.setenv("POLARIS_MOTIVE_UTILIZATION_SCHEDULED_ORGANIZATION_SLUG", "missing")
        with pytest.raises(MotiveVehicleUtilizationSchedulerError, match="not found"):
            resolve_scheduled_organization(session)
        monkeypatch.setenv("POLARIS_MOTIVE_UTILIZATION_SCHEDULED_ORGANIZATION_SLUG", "mor")
        assert resolve_scheduled_organization(session).id == "org-1"


def test_outside_window_is_zero_provider_call(monkeypatch):
    import app.motive.vehicle_utilization_scheduler as scheduler

    monkeypatch.setenv("MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED", "true")
    calls = []
    monkeypatch.setattr(scheduler, "run_vehicle_utilization_production_ingestion", lambda *a, **k: calls.append(1))

    with SessionLocal() as session:
        result = run_scheduled_vehicle_utilization(
            session, now=datetime(2026, 8, 19, 12, 17, tzinfo=timezone.utc)
        )
    assert result.status == "outside_window"
    assert result.dispatch_claimed is False
    assert calls == []


def test_first_local_day_claim_executes_once_and_second_is_noop(monkeypatch):
    import app.motive.vehicle_utilization_scheduler as scheduler

    monkeypatch.setenv("MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED", "true")
    monkeypatch.setenv("POLARIS_MOTIVE_UTILIZATION_SCHEDULED_ORGANIZATION_SLUG", "mor")
    calls = []

    class FakeProductionResult:
        def as_dict(self):
            return {
                "status": "success",
                "provider_calls_attempted": 7,
                "provider_calls_completed": 7,
                "checkpoint_advanced": True,
                "sync_history_written": True,
                "secrets_exposed": False,
            }

    def fake_run(*args, **kwargs):
        calls.append(1)
        return FakeProductionResult()

    monkeypatch.setattr(scheduler, "run_vehicle_utilization_production_ingestion", fake_run)

    with SessionLocal() as session:
        first = run_scheduled_vehicle_utilization(session, now=_scheduled_time())
    with SessionLocal() as session:
        second = run_scheduled_vehicle_utilization(session, now=_scheduled_time())

    assert first.status == "executed"
    assert first.dispatch_claimed is True
    assert second.status == "already_claimed"
    assert second.dispatch_claimed is False
    assert calls == [1]
    with SessionLocal() as session:
        marker = session.query(MotiveSyncCheckpoint).filter_by(provider_resource=SCHEDULER_DISPATCH_RESOURCE).one()
        assert marker.last_successful_position["claimed_local_date"] == "2026-08-19"
        assert session.query(MotiveSyncCheckpoint).filter_by(provider_resource="vehicle_utilization").count() == 0


def test_claim_remains_consumed_after_production_failure(monkeypatch):
    import app.motive.vehicle_utilization_scheduler as scheduler

    monkeypatch.setenv("MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED", "true")
    monkeypatch.setenv("POLARIS_MOTIVE_UTILIZATION_SCHEDULED_ORGANIZATION_SLUG", "mor")
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise MotiveVehicleUtilizationProductionIngestionError("provider_failed", "sanitized failure")

    monkeypatch.setattr(scheduler, "run_vehicle_utilization_production_ingestion", fail)
    with SessionLocal() as session:
        first = run_scheduled_vehicle_utilization(session, now=_scheduled_time())
    with SessionLocal() as session:
        second = run_scheduled_vehicle_utilization(session, now=_scheduled_time())

    assert first.status == "failed"
    assert first.dispatch_claimed is True
    assert first.error_code == "provider_failed"
    assert second.status == "already_claimed"
    assert calls == [1]


def test_machine_endpoint_uses_motive_specific_hmac_and_rejects_body(client, monkeypatch):
    monkeypatch.setenv("POLARIS_MOTIVE_UTILIZATION_CRON_TRIGGER_SECRET", "scheduled-secret")

    assert client.post("/api/v1/internal/motive/vehicle-utilization/run").status_code == 401

    import time

    timestamp = str(int(time.time()))
    path = "/api/v1/internal/motive/vehicle-utilization/run"
    headers = {
        "X-Polaris-Job-Timestamp": timestamp,
        "X-Polaris-Job-Signature": sign_job_request(
            method="POST", path=path, body=b"", timestamp=timestamp, secret="scheduled-secret"
        ),
    }
    response = client.post(path, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
    assert response.json()["secrets_exposed"] is False

    body = b'{"organization_id":"org-2","date":"2026-01-01","retry":true}'
    body_headers = {
        "X-Polaris-Job-Timestamp": timestamp,
        "X-Polaris-Job-Signature": sign_job_request(
            method="POST", path=path, body=body, timestamp=timestamp, secret="scheduled-secret"
        ),
    }
    rejected = client.post(path, headers=body_headers, content=body)
    assert rejected.status_code == 400
    assert "org-2" not in rejected.text
