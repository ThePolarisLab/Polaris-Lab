from __future__ import annotations

from datetime import date
from decimal import Decimal
import inspect
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import motive as motive_api
from app.dashboard.service import build_executive_dashboard
from app.database.database import Base
from app.database.models import register_models
from app.models.motive import MotiveSyncCheckpoint, MotiveVehicleUtilizationRecord
from app.motive.vehicle_utilization_writer_contract import motive_vehicle_utilization_writer_contract_status
from app.organizations.models import Organization
from app.security.models import AuthenticatedPrincipal, Permission

register_models()


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


def _session_factory(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'motive-utilization-writer-contract.db').as_posix()}"
    engine = create_engine(database_url)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestingSession.begin() as session:
        session.add(Organization(id="org-a", slug="org-a", display_name="Org A"))
        session.add(Organization(id="org-b", slug="org-b", display_name="Org B"))
    return TestingSession


def _utilization_record(organization_id: str = "org-a") -> MotiveVehicleUtilizationRecord:
    return MotiveVehicleUtilizationRecord(
        organization_id=organization_id,
        organization_slug=organization_id,
        provider_vehicle_id="provider-vehicle-secret",
        motive_vehicle_id=1,
        request_window_start=date(2026, 8, 12),
        request_window_end=date(2026, 8, 13),
        reporting_period_start=None,
        reporting_period_end=None,
        utilization_percent=Decimal("99.9999"),
        idle_time=Decimal("111.0000"),
        driving_time=Decimal("222.0000"),
        idle_fuel=Decimal("333.0000"),
        driving_fuel=Decimal("444.0000"),
        metric_units=True,
        parser_version="motive_vehicle_idle_rollup_v1",
        provider_payload_metadata={"unsafe": "vin-and-provider-values-stay-out-of-contract"},
    )


def test_vehicle_utilization_writer_contract_route_requires_connector_read() -> None:
    route_paths = {getattr(route, "path", "") for route in motive_api.router.routes}
    source = inspect.getsource(motive_api.motive_fleet_vehicle_utilization_writer_contract)

    assert "/api/v1/motive/fleet/vehicle-utilization-writer-contract" in route_paths
    assert "require_permission(Permission.CONNECTOR_READ)" in source


def test_vehicle_utilization_writer_contract_metadata_is_advertised_without_provider_calls(tmp_path, monkeypatch) -> None:
    def fail_provider_call(*_args, **_kwargs):
        raise AssertionError("writer contract gate must not call Motive")

    monkeypatch.setattr(motive_api, "run_vehicle_utilization_contract_verification", fail_provider_call)
    monkeypatch.setattr(motive_api, "run_vehicle_utilization_bounded_evidence", fail_provider_call)
    TestingSession = _session_factory(tmp_path)

    with TestingSession() as session:
        response = motive_api.motive_fleet_vehicle_utilization_writer_contract(principal=_principal(), session=session)
        contract = motive_api.motive_verification_contract(principal=_principal())

    metadata = contract["fleet_vehicle_utilization_writer_contract"]
    assert metadata["method"] == "GET"
    assert metadata["manual_route"] == "/api/v1/motive/fleet/vehicle-utilization-writer-contract"
    assert metadata["provider_calls"] == 0
    assert response["resource"] == "vehicle_utilization_writer_contract"
    assert response["writer_enabled"] is False
    assert response["persistence_enabled"] is False
    assert response["checkpoint_advancement_enabled"] is False


def test_vehicle_utilization_writer_contract_is_read_only_and_tenant_scoped(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    with TestingSession.begin() as session:
        session.add(_utilization_record("org-a"))
        session.add(_utilization_record("org-b"))

    with TestingSession() as session:
        before_utilization = session.query(MotiveVehicleUtilizationRecord).count()
        before_checkpoints = session.query(MotiveSyncCheckpoint).count()
        status = motive_vehicle_utilization_writer_contract_status(session, "org-a")

        assert status["observed_persistence_state"]["organization_scoped_utilization_rows"] == 1
        assert status["observed_persistence_state"]["certified_request_window_unique_constraint_enforced"] is True
        assert status["observed_persistence_state"]["legacy_nullable_reporting_period_unique_constraint_certified_for_future_writes"] is False
        assert session.query(MotiveVehicleUtilizationRecord).count() == before_utilization
        assert session.query(MotiveSyncCheckpoint).count() == before_checkpoints


def test_vehicle_utilization_writer_contract_missing_rollup_is_not_zero_or_no_activity(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    with TestingSession() as session:
        status = motive_vehicle_utilization_writer_contract_status(session, "org-a")

    missing = status["missing_row_policy"]
    assert missing["classification"] == "provider_rollup_absent"
    assert missing["creates_durable_row"] is False
    assert missing["creates_synthetic_zero_metrics"] is False
    assert missing["classifies_vehicle_inactive"] is False
    assert missing["classifies_no_activity"] is False
    assert missing["missing_rollup_means_no_activity"] == "DEFERRED"
    assert status["live_bounded_evidence"]["no_activity_evidence"]["zero_activity_shaped_rollup_observed"] is False
    assert status["live_bounded_evidence"]["no_activity_evidence"]["missing_single_day_rollup_observed"] is True
    assert status["live_bounded_evidence"]["no_activity_evidence"]["missing_combined_window_rollup_observed"] is True


def test_vehicle_utilization_writer_contract_fails_closed_for_unknown_and_duplicate_rollups(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    with TestingSession() as session:
        status = motive_vehicle_utilization_writer_contract_status(session, "org-a")

    assert status["unknown_vehicle_policy"]["classification"] == "fail_closed"
    assert status["unknown_vehicle_policy"]["auto_create_vehicle"] is False
    assert status["duplicate_policy"]["classification"] == "fail_closed"
    assert status["duplicate_policy"]["duplicate_returned_rollup_for_vehicle_window_allowed"] is False
    assert "no duplicate returned rollup exists" in " ".join(status["returned_row_policy"]["required_conditions"])
    assert "no unexpected provider vehicle appears" in status["returned_row_policy"]["required_conditions"]


def test_vehicle_utilization_writer_contract_keeps_request_window_distinct_from_reporting_period(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    with TestingSession() as session:
        status = motive_vehicle_utilization_writer_contract_status(session, "org-a")

    identity = status["request_window_identity"]
    reporting = status["reporting_period_status"]
    assert identity["classification"] == "CERTIFIED_POLARIS_IDEMPOTENCY_KEY"
    assert identity["candidate_key"] == ["organization_id", "motive_vehicle_id", "request_window_start", "request_window_end"]
    assert "metric_units" not in identity["candidate_key"]
    assert identity["provider_natural_key_returned"] is False
    assert identity["prefers_internal_vehicle_fk"] is True
    assert identity["migration_required_now"] is False
    assert identity["database_enforced"] is True
    assert identity["database_constraint"] == "uq_motive_vehicle_util_org_vehicle_request_window"
    assert identity["database_identity_columns"] == [
        "organization_id",
        "motive_vehicle_id",
        "request_window_start",
        "request_window_end",
    ]
    assert identity["legacy_reporting_period_constraint_retained"] is True
    assert identity["legacy_reporting_period_constraint_certified_for_future_writer"] is False
    assert identity["writer_enabled"] is False
    assert identity["persistence_enabled"] is False
    assert identity["metric_units_in_key"] is False
    assert reporting["request_window_start_end_are_context"] is True
    assert reporting["copy_request_window_to_reporting_period"] is False
    assert reporting["provider_reporting_period_fields_available"] is False
    assert reporting["reporting_period_start"] == "DEFERRED"
    assert reporting["reporting_period_end"] == "DEFERRED"


def test_vehicle_utilization_writer_contract_certifies_canonical_metric_unit_policy(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    with TestingSession() as session:
        status = motive_vehicle_utilization_writer_contract_status(session, "org-a")

    identity = status["request_window_identity"]
    unit_policy = status["unit_policy"]
    assert identity["classification"] == "CERTIFIED_POLARIS_IDEMPOTENCY_KEY"
    assert identity["database_enforced"] is True
    assert status["writer_enabled"] is False
    assert status["persistence_enabled"] is False
    assert unit_policy["writer_unit_mode_certified"] is True
    assert unit_policy["canonical_metric_units_policy"] is True
    assert unit_policy["canonical_unit_system"] == "metric"
    assert unit_policy["canonical_request_header"] == "X-Metric-Units"
    assert unit_policy["canonical_request_header_value"] == "true"
    assert unit_policy["canonical_metric_units_policy_required_before_writer_enablement"] is False
    assert unit_policy["replay_unit_mode_must_not_change_for_existing_window"] is True
    assert unit_policy["returned_metric_units_must_match_certified_request_policy"] is True
    assert unit_policy["unknown_or_missing_unit_context_fails_persistence_readiness"] is True
    assert unit_policy["unit_conversion_enabled"] is False
    assert unit_policy["combine_fuel_across_different_or_unknown_unit_contexts"] is False
    assert "canonical metric-units request policy must be fixed before writer enablement" not in status["remaining_blockers"]
    assert "never create a second imperial row" in unit_policy["replay_rule"]


def test_vehicle_utilization_writer_contract_blocks_scheduler_checkpoint_and_pagination(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    with TestingSession() as session:
        status = motive_vehicle_utilization_writer_contract_status(session, "org-a")

    assert status["scheduled_ingestion_enabled"] is False
    assert status["checkpoint_contract"]["enabled"] is False
    assert status["checkpoint_advancement_enabled"] is False
    assert status["timezone_blocker"]["exact_company_rollup_timezone_required_before_scheduled_daily_ingestion"] is True
    assert status["timezone_blocker"]["scheduled_daily_ingestion_enabled"] is False
    assert status["pagination_blocker"]["status"] == "pagination_reader_certified_writer_still_disabled"
    assert status["pagination_blocker"]["pagination_contract_certified"] is True
    assert status["pagination_blocker"]["pagination_reader_implemented"] is True
    assert status["pagination_blocker"]["canonical_page_size"] == 100
    assert status["pagination_blocker"]["one_based_page_progression"] is True
    assert status["pagination_blocker"]["pagination_total_required"] is True
    assert status["pagination_blocker"]["pagination_total_stability_required"] is True
    assert status["pagination_blocker"]["duplicate_across_pages_fails_closed"] is True
    assert status["pagination_blocker"]["unexpected_vehicle_fails_closed"] is True
    assert status["pagination_blocker"]["pagination_persistence_enabled"] is False
    assert status["pagination_blocker"]["checkpoint_advancement_enabled"] is False
    assert status["pagination_blocker"]["broad_writer_requires_explicit_pagination_contract"] is False
    assert status["pagination_blocker"]["page_2_fetch_enabled"] is False
    assert "broad pagination behavior must be certified before ingestion beyond bounded page 1" not in status["remaining_blockers"]
    assert "database uniqueness enforcement for the durable writer identity key is not yet implemented" not in status["remaining_blockers"]
    assert "utilization writer transaction implementation remains disabled" in status["remaining_blockers"]
    assert "checkpoint advancement implementation remains disabled" in status["remaining_blockers"]


def test_vehicle_utilization_writer_contract_redacts_values_and_creates_no_dashboard_noise(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    with TestingSession.begin() as session:
        session.add(_utilization_record())

    with TestingSession() as session:
        status = motive_vehicle_utilization_writer_contract_status(session, "org-a")
        dashboard = build_executive_dashboard(session, organization_id="org-a")

    rendered = json.dumps(status, sort_keys=True, default=str)
    for unsafe in (
        "provider-vehicle-secret",
        "vin-and-provider-values-stay-out-of-contract",
        "99.9999",
        "111.0000",
        "222.0000",
        "333.0000",
        "444.0000",
        "X-API-Key",
        "MOTIVE_API_KEY",
        "fake-motive-secret",
    ):
        assert unsafe not in rendered
    assert status["security"]["provider_ids_exposed"] is False
    assert status["security"]["vin_values_exposed"] is False
    assert status["security"]["metric_values_exposed"] is False
    assert status["security"]["secrets_exposed"] is False
    assert status["dashboard_daily_brief_attention_enabled"] is False
    assert not [item for item in dashboard.needs_attention if item.source.startswith("Motive")]
    assert not [item for item in dashboard.daily_brief.needs_attention if item.source.startswith("Motive")]
