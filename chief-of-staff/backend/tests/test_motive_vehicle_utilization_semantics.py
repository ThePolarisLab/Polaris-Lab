from __future__ import annotations

from datetime import date
from decimal import Decimal
import inspect
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.dashboard.service import build_executive_dashboard
from app.database.database import Base
from app.database.models import register_models
from app.models.motive import MotiveSyncCheckpoint, MotiveVehicleRecord, MotiveVehicleUtilizationRecord
from app.motive.vehicle_utilization_semantics import motive_vehicle_utilization_semantics_status
from app.organizations.models import Organization
from app.security.models import AuthenticatedPrincipal, Permission

register_models()


@pytest.fixture()
def utilization_semantics_db(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'motive-utilization-semantics.db').as_posix()}"
    engine = create_engine(database_url)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestingSession.begin() as session:
        session.add(Organization(id="org-a", slug="org-a", display_name="Org A"))
        session.add(Organization(id="org-b", slug="org-b", display_name="Org B"))
    return TestingSession


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


def _utilization_record(*, organization_id: str = "org-a", organization_slug: str = "org-a") -> MotiveVehicleUtilizationRecord:
    return MotiveVehicleUtilizationRecord(
        organization_id=organization_id,
        organization_slug=organization_slug,
        provider_vehicle_id="provider-vehicle-secret",
        motive_vehicle_id=1 if organization_id == "org-a" else None,
        request_window_start=date(2026, 8, 8),
        request_window_end=date(2026, 8, 9),
        reporting_period_start=None,
        reporting_period_end=None,
        utilization_percent=Decimal("0"),
        idle_time=Decimal("0"),
        driving_time=Decimal("120"),
        idle_fuel=Decimal("0"),
        driving_fuel=None,
        metric_units=False,
        parser_version="motive_vehicle_idle_rollup_v1",
        provider_payload_metadata={"source": "synthetic-test"},
    )


def test_vehicle_utilization_semantics_classifies_provider_contract_and_persistence_boundary(utilization_semantics_db) -> None:
    with utilization_semantics_db.begin() as session:
        session.add(MotiveVehicleRecord(id=1, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-secret"))
        session.add(_utilization_record())

    with utilization_semantics_db() as session:
        status = motive_vehicle_utilization_semantics_status(session, "org-a")

    assert status["resource"] == "vehicle_utilization_semantics_certification"
    assert status["source_endpoint"] == "/v1/vehicle_utilization"
    assert status["provider_contract"]["endpoint_version"] == "v1"
    assert status["provider_contract"]["endpoint_kind"] == "rollup_summary"
    assert status["provider_contract"]["schema_certified"] is True
    assert status["provider_contract"]["provider_schema_compatibility"] == "compatible"
    assert status["request_window"]["start_date_parameter"] == "CONFIRMED"
    assert status["request_window"]["end_date_parameter"] == "CONFIRMED"
    assert status["request_window"]["end_date_inclusivity"] == "DEFERRED"
    assert status["request_window"]["provider_returned_reporting_period_fields"] is False
    assert status["request_window"]["summary_scope"] == "CONFIRMED"
    assert status["timezone"]["behavior"] == "company_configured_rollup_timezone"
    assert status["timezone"]["rollup_timezone_behavior"] == "CONFIRMED"
    assert status["timezone"]["controlled_by_x_time_zone"] is False
    assert status["timezone"]["exact_company_rollup_timezone"] == "DEFERRED"
    assert status["timezone"]["polaris_request_window_calendar_timezone"] == "America/Winnipeg"
    assert status["timezone"]["polaris_timezone_is_provider_rollup_timezone"] is False
    assert status["unit_system"]["x_metric_units_controls_unit_system"] == "CONFIRMED"
    assert status["unit_system"]["metric_units_type"] == "boolean"
    assert status["unit_system"]["normalization_to_one_internal_unit_system"] == "DEFERRED"
    assert status["persistence"]["schema_ready_for_future_writer_shape"] is True
    assert status["persistence"]["migration_required"] is False
    assert status["persistence"]["persistence_enabled"] is False
    assert status["persistence"]["writer_enabled"] is False
    assert status["persistence"]["scheduled_sync_enabled"] is False
    assert status["persistence"]["checkpoint_advancement_enabled"] is False
    assert status["persistence"]["durable_identity_certified"] is False
    assert status["persistence"]["nullable_period_unique_constraint_certified_for_future_writes"] is False
    assert status["persistence"]["broad_sync_enabled"] is False
    assert status["persistence"]["utilization_records_stored"] == 1
    assert status["persistence"]["structural_identity_columns"] == [
        "organization_id",
        "provider_vehicle_id",
        "motive_vehicle_id",
        "request_window_start",
        "request_window_end",
    ]
    assert status["security"] == {
        "organization_scoped": True,
        "provider_ids_exposed": False,
        "vin_values_exposed": False,
        "vehicle_number_values_exposed": False,
        "metric_values_exposed": False,
        "raw_provider_payload_exposed": False,
        "headers_exposed": False,
        "secrets_exposed": False,
    }


def test_vehicle_utilization_semantics_classifies_field_completeness_per_org(utilization_semantics_db) -> None:
    with utilization_semantics_db.begin() as session:
        session.add(MotiveVehicleRecord(id=1, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-secret"))
        session.add(_utilization_record())
        other = _utilization_record(organization_id="org-b", organization_slug="org-b")
        other.utilization_percent = None
        other.driving_time = Decimal("0")
        session.add(other)

    with utilization_semantics_db() as session:
        org_a = motive_vehicle_utilization_semantics_status(session, "org-a")
        org_b = motive_vehicle_utilization_semantics_status(session, "org-b")

    assert org_a["completeness"]["utilization_percent"] == {"total": 1, "present": 1, "percent": 100.0}
    assert org_a["completeness"]["driving_time"] == {"total": 1, "present": 1, "percent": 100.0}
    assert org_a["completeness"]["driving_fuel"] == {"total": 1, "present": 0, "percent": 0.0}
    assert org_b["completeness"]["utilization_percent"] == {"total": 1, "present": 0, "percent": 0.0}
    assert org_b["completeness"]["driving_time"] == {"total": 1, "present": 1, "percent": 100.0}


def test_vehicle_utilization_semantics_route_is_read_only_redacted_and_does_not_call_provider(
    utilization_semantics_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import motive as motive_api

    def fail_provider_call(*_args, **_kwargs):
        raise AssertionError("semantics certification must not call Motive")

    monkeypatch.setattr(motive_api, "run_vehicle_utilization_contract_verification", fail_provider_call)
    with utilization_semantics_db.begin() as session:
        session.add(MotiveVehicleRecord(id=1, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-secret"))
        session.add(_utilization_record())

    with utilization_semantics_db() as session:
        response = motive_api.motive_fleet_vehicle_utilization_semantics(principal=_principal(), session=session)

    rendered = json.dumps(response, sort_keys=True, default=str)
    assert response["security"]["provider_ids_exposed"] is False
    assert response["security"]["vin_values_exposed"] is False
    assert response["security"]["vehicle_number_values_exposed"] is False
    assert response["security"]["metric_values_exposed"] is False
    assert response["security"]["raw_provider_payload_exposed"] is False
    assert response["security"]["headers_exposed"] is False
    assert response["security"]["secrets_exposed"] is False
    assert "provider-vehicle-secret" not in rendered
    assert "0.0000" not in rendered
    assert '"120"' not in rendered
    assert "X-API-Key" not in rendered
    assert "MOTIVE_API_KEY" not in rendered


def test_vehicle_utilization_semantics_does_not_create_checkpoint_or_dashboard_noise(utilization_semantics_db) -> None:
    with utilization_semantics_db.begin() as session:
        session.add(MotiveVehicleRecord(id=1, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-secret"))
        session.add(_utilization_record())

    with utilization_semantics_db() as session:
        before = session.query(MotiveSyncCheckpoint).count()
        _ = motive_vehicle_utilization_semantics_status(session, "org-a")
        after = session.query(MotiveSyncCheckpoint).count()
        dashboard = build_executive_dashboard(session, organization_id="org-a")

    assert before == 0
    assert after == 0
    assert all("utilization semantics" not in item.title.lower() for item in dashboard.needs_attention)


def test_vehicle_utilization_semantics_source_has_no_provider_call_or_write_path() -> None:
    from app.motive import vehicle_utilization_semantics as semantics_module

    source = inspect.getsource(semantics_module)
    assert "_request_json" not in source
    assert "run_vehicle_utilization_contract_verification" not in source
    assert "session.add" not in source
    assert "session.commit" not in source
    assert "session.flush" not in source


def test_vehicle_utilization_semantics_source_has_no_dashboard_or_checkpoint_import() -> None:
    from app.motive import vehicle_utilization_semantics as semantics_module

    source = inspect.getsource(semantics_module)
    assert "from app.dashboard" not in source
    assert "import app.dashboard" not in source
    assert "MotiveSyncCheckpoint" not in source
