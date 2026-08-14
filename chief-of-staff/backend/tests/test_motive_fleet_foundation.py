from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.dashboard.service import build_executive_dashboard
from app.database.database import Base
from app.models.motive import MotiveDriverRecord, MotiveSyncCheckpoint, MotiveSyncHistory, MotiveVehicleRecord
from app.motive.fleet_foundation import motive_fleet_foundation_status
from app.organizations.models import Organization
from app.security.models import AuthenticatedPrincipal, Permission


@pytest.fixture()
def motive_fleet_db(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'motive-fleet.db').as_posix()}"
    engine = create_engine(database_url)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestingSession.begin() as session:
        session.add(Organization(id="org-a", slug="org-a", display_name="Org A"))
        session.add(Organization(id="org-b", slug="org-b", display_name="Org B"))
    return TestingSession


def _history(
    *,
    organization_id: str = "org-a",
    organization_slug: str = "org-a",
    mode: str = "vehicle_sync",
    provider_resource: str = "vehicles",
    status: str = "success",
    records_read: int = 1,
    records_written: int = 1,
) -> MotiveSyncHistory:
    now = datetime.now(timezone.utc)
    return MotiveSyncHistory(
        organization_id=organization_id,
        organization_slug=organization_slug,
        provider="motive",
        provider_resource=provider_resource,
        mode=mode,
        status=status,
        run_id=f"{organization_id}-{mode}-{status}",
        started_at=now,
        completed_at=now,
        records_read=records_read,
        records_written=records_written,
        checkpoint_before={},
        checkpoint_after={"page_number": 1},
        resource_counts={provider_resource: records_read, "pages_read": 1},
    )


def _principal(organization_id: str = "org-a") -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        identity_id="identity-a",
        organization_id=organization_id,
        membership_id=f"membership-{organization_id}",
        role="admin",
        permissions=frozenset({Permission.CONNECTOR_READ}),
        provider="test",
        subject="test-subject",
    )


def test_motive_fleet_foundation_reports_confirmed_derived_and_deferred_contracts(motive_fleet_db):
    with motive_fleet_db.begin() as session:
        session.add(MotiveVehicleRecord(organization_id="org-a", organization_slug="org-a", provider_vehicle_id="vehicle-secret-a"))
        session.add(MotiveVehicleRecord(organization_id="org-a", organization_slug="org-a", provider_vehicle_id="vehicle-secret-b"))
        session.add(MotiveVehicleRecord(organization_id="org-b", organization_slug="org-b", provider_vehicle_id="vehicle-secret-a"))
        session.add(MotiveDriverRecord(organization_id="org-a", organization_slug="org-a", provider_driver_id="user-secret-a", source_endpoint="/v1/users"))
        session.add(_history())
        session.add(_history(mode="user_sync", provider_resource="users", records_read=1, records_written=1))
        session.add(MotiveSyncCheckpoint(organization_id="org-a", organization_slug="org-a", provider_resource="vehicles", checkpoint_status="success", page_number=1, last_successful_position={"page_number": 1}))
        session.add(MotiveSyncCheckpoint(organization_id="org-a", organization_slug="org-a", provider_resource="users", checkpoint_status="success", page_number=1, last_successful_position={"page_number": 1}))

    with motive_fleet_db() as session:
        status = motive_fleet_foundation_status(session, "org-a")

    assert status["status"] == "ready"
    assert {item["classification"] for item in status["confirmed_contracts"]} == {"CONFIRMED"}
    metrics = {item["name"]: item for item in status["derived_metrics"]}
    assert metrics["total_known_vehicles"]["classification"] == "DERIVED"
    assert metrics["total_known_vehicles"]["value"] == 2
    assert metrics["total_known_company_users"]["value"] == 1
    assert "vehicle_utilization_reporting_period" in status["deferred_semantics"]
    assert "driver_classification" in status["deferred_semantics"]
    assert status["persistence"]["vehicle_utilization"]["enabled"] is False
    assert status["checkpoint_safety"]["vehicles"] == "last_successful_position_recorded"
    assert status["dashboard_daily_brief_boundary"]["fleet_attention_enabled"] is False
    assert status["security"]["secrets_exposed"] is False
    rendered = str(status)
    assert "vehicle-secret" not in rendered
    assert "user-secret" not in rendered


def test_motive_fleet_foundation_route_returns_safe_contract(motive_fleet_db):
    from app.api import motive as motive_api

    with motive_fleet_db.begin() as session:
        session.add(MotiveVehicleRecord(organization_id="org-a", organization_slug="org-a", provider_vehicle_id="vehicle-secret-a"))

    with motive_fleet_db() as session:
        response = motive_api.motive_fleet_foundation(principal=_principal(), session=session)

    assert response["resource"] == "fleet_operations_v1_foundation"
    assert response["security"]["provider_ids_exposed"] is False
    assert "vehicle-secret-a" not in str(response)


def test_motive_fleet_foundation_is_tenant_scoped(motive_fleet_db):
    with motive_fleet_db.begin() as session:
        session.add(MotiveVehicleRecord(organization_id="org-a", organization_slug="org-a", provider_vehicle_id="same-provider-id"))
        session.add(MotiveVehicleRecord(organization_id="org-b", organization_slug="org-b", provider_vehicle_id="same-provider-id"))
        session.add(MotiveVehicleRecord(organization_id="org-b", organization_slug="org-b", provider_vehicle_id="other-provider-id"))
        session.add(_history(organization_id="org-b", organization_slug="org-b"))

    with motive_fleet_db() as session:
        org_a = motive_fleet_foundation_status(session, "org-a")
        org_b = motive_fleet_foundation_status(session, "org-b")

    org_a_metrics = {item["name"]: item["value"] for item in org_a["derived_metrics"]}
    org_b_metrics = {item["name"]: item["value"] for item in org_b["derived_metrics"]}
    assert org_a_metrics["total_known_vehicles"] == 1
    assert org_b_metrics["total_known_vehicles"] == 2
    assert org_a["status"] == "not_started"
    assert org_b["status"] == "ready"


def test_motive_fleet_foundation_reports_safe_failure_health(motive_fleet_db):
    with motive_fleet_db.begin() as session:
        session.add(_history(status="authorization_required", records_read=0, records_written=0))

    with motive_fleet_db() as session:
        status = motive_fleet_foundation_status(session, "org-a")

    assert status["status"] == "authorization_required"
    assert "authorization_required" in status["message"]
    assert status["persistence"]["vehicles"]["latest_status"] == "authorization_required"
    assert status["persistence"]["vehicles"]["records_written"] == 0


def test_motive_fleet_foundation_does_not_create_dashboard_or_daily_brief_noise(motive_fleet_db):
    with motive_fleet_db.begin() as session:
        session.add(MotiveVehicleRecord(organization_id="org-a", organization_slug="org-a", provider_vehicle_id="vehicle-secret-a"))
        session.add(_history())

    with motive_fleet_db() as session:
        dashboard = build_executive_dashboard(session, organization_id="org-a")

    assert not [item for item in dashboard.needs_attention if item.source.startswith("Motive")]
    assert not [item for item in dashboard.daily_brief.needs_attention if item.source.startswith("Motive")]
    assert not [item for item in dashboard.daily_brief.system_health if item.source.startswith("Motive")]
