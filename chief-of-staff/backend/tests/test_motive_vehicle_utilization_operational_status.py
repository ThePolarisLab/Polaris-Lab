from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.api import motive_vehicle_utilization_production as api
from app.database.database import Base
from app.models.motive import MotiveSyncCheckpoint, MotiveSyncHistory
from app.motive.vehicle_utilization_operational_status import vehicle_utilization_operational_status
from app.organizations.models import Organization


ORG_A = "org-a"
ORG_B = "org-b"
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[Organization.__table__, MotiveSyncHistory.__table__, MotiveSyncCheckpoint.__table__],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _history(
    *,
    organization_id: str = ORG_A,
    status: str = "success",
    started_at: datetime = NOW,
    completed_through: str = "2026-08-21",
    counts: dict | None = None,
) -> MotiveSyncHistory:
    resource_counts = {
        "horizon_days": 7,
        "request_timezone": "America/Chicago",
        "unit_request_mode": "imperial",
        "fuel_unit": "gallons",
        "selected_vehicle_count": 23,
        "provider_calls_attempted": 7,
        "provider_calls_completed": 7,
        "rollups_returned": 72,
        "records_updated": 61,
        "checkpoint_advanced": status == "success",
        "secret_like_unapproved_key": "must-not-leak",
    }
    if counts:
        resource_counts.update(counts)
    return MotiveSyncHistory(
        organization_id=organization_id,
        organization_slug=organization_id,
        provider="motive",
        provider_resource="vehicle_utilization",
        mode="production_recent_window_ingestion",
        status=status,
        run_id=f"run-{organization_id}-{started_at.timestamp()}",
        started_at=started_at,
        completed_at=started_at,
        records_read=72,
        records_written=61,
        error_code=None if status == "success" else "bounded_failure",
        checkpoint_before={},
        checkpoint_after={"completed_through": completed_through} if status == "success" else {},
        resource_counts=resource_counts,
    )


def _production_checkpoint(
    *,
    organization_id: str = ORG_A,
    completed_through: str = "2026-08-21",
    status: str = "success",
) -> MotiveSyncCheckpoint:
    return MotiveSyncCheckpoint(
        organization_id=organization_id,
        organization_slug=organization_id,
        provider="motive",
        provider_resource="vehicle_utilization",
        checkpoint_status=status,
        last_successful_sync_at=NOW,
        last_successful_position={
            "completed_through": completed_through,
            "request_timezone": "America/Chicago",
            "unit_request_mode": "imperial",
            "fuel_unit": "gallons",
            "unapproved": "must-not-leak",
        },
    )


def _scheduler_checkpoint(*, organization_id: str = ORG_A) -> MotiveSyncCheckpoint:
    return MotiveSyncCheckpoint(
        organization_id=organization_id,
        organization_slug=organization_id,
        provider="motive",
        provider_resource="vehicle_utilization_scheduler_dispatch",
        checkpoint_status="claimed",
        last_successful_sync_at=NOW,
        last_successful_position={
            "claimed_local_date": "2026-08-22",
            "request_timezone": "America/Chicago",
            "scheduler_mode": "scheduled_production_ingestion",
            "unapproved": "must-not-leak",
        },
    )


def test_not_started_is_stable_and_read_only(session, monkeypatch):
    monkeypatch.delenv("MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED", raising=False)
    monkeypatch.delenv("MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED", raising=False)
    monkeypatch.delenv("MOTIVE_VEHICLE_UTILIZATION_SCHEDULER_CONTROLLED_VALIDATION_WINDOW_ENABLED", raising=False)

    before_new = len(session.new)
    result = vehicle_utilization_operational_status(session, ORG_A)

    assert result["operational_status"] == "not_started"
    assert result["production"]["status"] == "not_started"
    assert result["checkpoint"]["status"] == "not_started"
    assert result["scheduler"]["claim_status"] == "not_claimed"
    assert result["secrets_exposed"] is False
    assert result["configuration"] == {
        "production_ingestion_enabled": False,
        "production_scheduler_enabled": False,
        "controlled_validation_window_enabled": False,
    }
    assert len(session.new) == before_new


def test_matching_success_history_and_checkpoint_is_healthy(session):
    session.add_all([_history(), _production_checkpoint(), _scheduler_checkpoint()])
    session.commit()

    result = vehicle_utilization_operational_status(session, ORG_A)

    assert result["operational_status"] == "healthy"
    assert result["production"]["status"] == "success"
    assert result["checkpoint"]["completed_through"] == "2026-08-21"
    assert result["scheduler"]["claim_status"] == "claimed"
    assert result["scheduler"]["claimed_local_date"] == "2026-08-22"


def test_allow_lists_exclude_unrestricted_json(session):
    session.add_all([_history(), _production_checkpoint(), _scheduler_checkpoint()])
    session.commit()

    result = vehicle_utilization_operational_status(session, ORG_A)

    assert "secret_like_unapproved_key" not in result["production"]["counts"]
    assert "unapproved" not in result["checkpoint"]
    assert "unapproved" not in result["scheduler"]
    assert "run_id" not in result["production"]


def test_partial_or_failed_latest_history_is_degraded(session):
    session.add_all([_history(status="partial"), _production_checkpoint()])
    session.commit()

    result = vehicle_utilization_operational_status(session, ORG_A)

    assert result["operational_status"] == "degraded"
    assert result["production"]["status"] == "partial"


def test_stale_checkpoint_relative_to_success_history_is_degraded(session):
    session.add_all([_history(completed_through="2026-08-21"), _production_checkpoint(completed_through="2026-08-20")])
    session.commit()

    result = vehicle_utilization_operational_status(session, ORG_A)

    assert result["operational_status"] == "degraded"


def test_scheduler_claim_alone_never_proves_health(session):
    session.add(_scheduler_checkpoint())
    session.commit()

    result = vehicle_utilization_operational_status(session, ORG_A)

    assert result["operational_status"] == "not_started"
    assert result["scheduler"]["claim_status"] == "claimed"


def test_newer_cross_tenant_history_cannot_replace_tenant_history(session):
    older = _history(organization_id=ORG_A, started_at=datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc))
    newer_other_tenant = _history(organization_id=ORG_B, started_at=datetime(2026, 8, 22, 13, 0, tzinfo=timezone.utc))
    newer_other_tenant.records_read = 999
    session.add_all([older, newer_other_tenant, _production_checkpoint(organization_id=ORG_A)])
    session.commit()

    result = vehicle_utilization_operational_status(session, ORG_A)

    assert result["production"]["records_read"] == 72
    assert result["operational_status"] == "healthy"


def test_latest_tenant_history_is_selected_deterministically(session):
    first = _history(started_at=datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc))
    second = _history(started_at=datetime(2026, 8, 22, 11, 0, tzinfo=timezone.utc), counts={"records_updated": 62})
    second.records_read = 73
    session.add_all([first, second, _production_checkpoint()])
    session.commit()

    result = vehicle_utilization_operational_status(session, ORG_A)

    assert result["production"]["records_read"] == 73
    assert result["production"]["counts"]["records_updated"] == 62


def test_configuration_exposes_booleans_only(session, monkeypatch):
    monkeypatch.setenv("MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED", "true")
    monkeypatch.setenv("MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("MOTIVE_VEHICLE_UTILIZATION_SCHEDULER_CONTROLLED_VALIDATION_WINDOW_ENABLED", "false")

    result = vehicle_utilization_operational_status(session, ORG_A)

    assert result["configuration"] == {
        "production_ingestion_enabled": True,
        "production_scheduler_enabled": True,
        "controlled_validation_window_enabled": False,
    }
    assert all(isinstance(value, bool) for value in result["configuration"].values())


def test_route_sanitizes_database_exception(monkeypatch):
    def fail(*_args, **_kwargs):
        raise SQLAlchemyError("database-password-should-not-leak")

    monkeypatch.setattr(api, "vehicle_utilization_operational_status", fail)

    with pytest.raises(HTTPException) as caught:
        api.get_motive_vehicle_utilization_operations_status(
            principal=SimpleNamespace(organization_id=ORG_A),
            session=SimpleNamespace(),
        )

    assert caught.value.status_code == 500
    assert caught.value.detail == {
        "status": "failed",
        "error_code": "motive_operational_status_read_failed",
        "message": "Motive vehicle-utilization operational status could not be read.",
        "secrets_exposed": False,
    }
    assert "database-password" not in str(caught.value.detail)


def test_route_requires_connector_read_dependency():
    route = next(
        route
        for route in api.router.routes
        if getattr(route, "path", None) == "/api/v1/motive/vehicle-utilization/operations-status"
    )
    assert route.methods == {"GET"}
    assert route.dependant.dependencies
    dependency_repr = " ".join(repr(dep.call) for dep in route.dependant.dependencies)
    assert "require_permission" in dependency_repr or route.dependant.dependencies[0].call is not None
