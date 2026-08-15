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
    assert status["request_window"]["summary_scope"] == "CONFIRMED"
    assert status["request_window"]["end_date_inclusivity"] == "DEFERRED"
    assert status["request_window"]["provider_returned_reporting_period_fields"] is False
    assert status["persistence"]["schema_ready_for_future_writer_shape"] is True
    assert status["persistence"]["persistence_enabled"] is False
    assert status["persistence"]["writer_enabled"] is False
    assert status["persistence"]["checkpoint_advancement_enabled"] is False
    assert status["persistence"]["scheduled_sync_enabled"] is False
    assert status["persistence"]["broad_sync_enabled"] is False
    assert status["persistence"]["durable_identity_certified"] is False
    assert status["persistence"]["nullable_period_unique_constraint_certified_for_future_writes"] is False


def test_vehicle_utilization_semantics_field_matrix_matches_official_and_observed_contract(utilization_semantics_db) -> None:
    with utilization_semantics_db() as session:
        status = motive_vehicle_utilization_semantics_status(session, "org-a")

    fields = {field["field"]: field for field in status["field_definitions"]}
    assert fields["provider_vehicle_id"]["classification"] == "CONFIRMED"
    assert fields["utilization_percent"]["classification"] == "CONFIRMED"
    assert fields["utilization_percent"]["semantic_unit"] == "percent"
    assert fields["idle_time"]["semantic_unit"] == "seconds"
    assert fields["driving_time"]["semantic_unit"] == "seconds"
    assert fields["idle_fuel"]["semantic_unit"] == "fuel volume in provider-selected unit system"
    assert fields["driving_fuel"]["semantic_unit"] == "fuel volume in provider-selected unit system"
    assert fields["metric_units"]["documented_type"] == "Boolean"
    assert fields["metric_units"]["classification"] == "CONFIRMED"
    assert fields["request_window_start"]["classification"] == "CONFIRMED_REQUEST_CONTEXT"
    assert fields["request_window_end"]["classification"] == "CONFIRMED_REQUEST_CONTEXT"
    assert fields["reporting_period_start"]["classification"] == "DEFERRED"
    assert fields["reporting_period_end"]["classification"] == "DEFERRED"
    assert fields["distance"]["classification"] == "DEFERRED"
    assert fields["engine_hours"]["classification"] == "DEFERRED"
    assert "numeric JSON number or finite numeric string" in fields["utilization_percent"]["parser_acceptance"]
    assert status["parser"]["accepts_documented_string_or_integer_metric_forms"] is True
    assert status["parser"]["accepts_observed_numeric_metric_forms"] is True
    assert status["parser"]["zero_values_preserved_distinct_from_null"] is True


def test_vehicle_utilization_semantics_counts_are_tenant_scoped_and_preserve_zero_vs_null(utilization_semantics_db) -> None:
    with utilization_semantics_db.begin() as session:
        session.add(MotiveVehicleRecord(id=1, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-secret"))
        session.add(_utilization_record())
        session.add(
            MotiveVehicleUtilizationRecord(
                organization_id="org-b",
                organization_slug="org-b",
                provider_vehicle_id="other-provider-secret",
                request_window_start=date(2026, 8, 8),
                request_window_end=date(2026, 8, 9),
                utilization_percent=None,
                idle_time=Decimal("50"),
                driving_time=Decimal("0"),
                idle_fuel=None,
                driving_fuel=Decimal("10"),
                metric_units=True,
            )
        )

    with utilization_semantics_db() as session:
        org_a = motive_vehicle_utilization_semantics_status(session, "org-a")
        org_b = motive_vehicle_utilization_semantics_status(session, "org-b")

    assert org_a["persistence"]["utilization_records_stored"] == 1
    assert org_b["persistence"]["utilization_records_stored"] == 1
    assert org_a["completeness"]["utilization_percent"] == {"total": 1, "present": 1, "percent": 100.0}
    assert org_a["completeness"]["idle_time"] == {"total": 1, "present": 1, "percent": 100.0}
    assert org_a["completeness"]["idle_fuel"] == {"total": 1, "present": 1, "percent": 100.0}
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
    assert "120" not in rendered
    assert "X-API-Key" not in rendered
    assert "MOTIVE_API_KEY" not in rendered


def test_vehicle_utilization_semantics_does_not_create_checkpoint_or_dashboard_noise(utilization_semantics_db) -> None:
    with utilization_semantics_db.begin() as session:
        session.add(MotiveVehicleRecord(id=1, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-secret"))
        session.add(_utilization_record())

    with utilization_semantics_db() as session:
        _ = motive_vehicle_utilization_semantics_status(session, "org-a")
        dashboard = build_executive_dashboard(session, organization_id="org-a")

        assert session.query(MotiveSyncCheckpoint).filter(MotiveSyncCheckpoint.provider_resource == "vehicle_utilization").count() == 0
        assert not [item for item in dashboard.needs_attention if item.source.startswith("Motive")]
        assert not [item for item in dashboard.daily_brief.needs_attention if item.source.startswith("Motive")]


def test_vehicle_utilization_semantics_route_exists_without_sync_route() -> None:
    from app.api import motive as motive_api

    route_paths = {route.path for route in motive_api.router.routes}
    assert "/api/v1/motive/fleet/vehicle-utilization-semantics" in route_paths
    assert "/api/v1/motive/sync/vehicle-utilization" not in route_paths
    source = inspect.getsource(motive_api)
    assert "sync/vehicle-utilization" not in source
