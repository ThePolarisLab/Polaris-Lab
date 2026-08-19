"""Tests for the controlled, feature-flagged ONE-DAY live-staging validation
mechanism for the Motive vehicle-utilization RECENT-WINDOW RECONCILIATION
runner:

- ``app/motive/vehicle_utilization_recent_reconciliation_validation.py``
  (orchestration: both feature gates, the <=100-eligible-vehicle pre-flight
  bound, the post-hoc one-call invariant assertion, and the sanitized
  response shape)
- ``app/api/motive.py::verify_motive_vehicle_utilization_recent_reconciliation``
  (the route: permission, confirmation, and HTTP status mapping)

This gate builds the MECHANISM only. No live Motive provider call is made
anywhere in this module -- every test either exercises a disabled/rejected
path (zero provider calls by construction) or injects an
``httpx.MockTransport`` client via monkeypatching, exactly like the sibling
controlled-write and runner test suites.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import inspect
from typing import Any

from fastapi import HTTPException
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import motive as motive_api
from app.database.database import Base
from app.database.models import register_models
from app.models.motive import (
    MotiveSyncCheckpoint,
    MotiveSyncHistory,
    MotiveVehicleRecord,
    MotiveVehicleUtilizationRecord,
)
from app.motive import vehicle_utilization_recent_reconciliation as runner_module
from app.motive.vehicle_utilization_recent_reconciliation import RECENT_RECONCILIATION_ENABLED_ENV_VAR
from app.motive.vehicle_utilization_recent_reconciliation_validation import (
    RECENT_RECONCILIATION_VALIDATION_ENABLED_ENV_VAR,
    RECENT_RECONCILIATION_VALIDATION_HORIZON_DAYS,
    RECENT_RECONCILIATION_VALIDATION_MAX_BATCHES,
    RECENT_RECONCILIATION_VALIDATION_MAX_PAGES,
    RECENT_RECONCILIATION_VALIDATION_MAX_PROVIDER_CALLS,
    RECENT_RECONCILIATION_VALIDATION_MAX_SELECTED_VEHICLES,
    RECENT_RECONCILIATION_VALIDATION_MAX_WINDOWS,
    MotiveVehicleUtilizationRecentReconciliationValidationError,
    recent_reconciliation_validation_enabled,
    run_recent_vehicle_utilization_reconciliation_live_validation,
)
from app.organizations.models import Organization
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

register_models()

FAKE_API_KEY = "fake-motive-secret"
UNSAFE_VIN = "VINSHOULDNOTLEAK99"
UNSAFE_UNIT_NUMBER = "unit-should-not-leak-221"
UNSAFE_DRIVER_EMAIL = "driver-should-not-leak@example.com"
FIXED_END_DATE = date(2026, 8, 17)  # frozen "yesterday" for deterministic tests


@pytest.fixture(autouse=True)
def _fixed_window_and_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(runner_module, "_completed_recent_reconciliation_window", lambda: FIXED_END_DATE)
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    yield


# ---------------------------------------------------------------------------
# Shared fixtures / helpers.
# ---------------------------------------------------------------------------
def _principal(organization_id: str = "org-a", *, permissions: frozenset[Permission] | None = None) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        identity_id="identity-a",
        organization_id=organization_id,
        membership_id=f"membership-{organization_id}",
        role="admin",
        permissions=permissions or frozenset({Permission.CONNECTOR_WRITE}),
        provider="test",
        subject="test-subject",
    )


def _session_factory(tmp_path, name: str = "recent-reconciliation-validation"):
    database_url = f"sqlite:///{(tmp_path / f'{name}.db').as_posix()}"
    engine = create_engine(database_url)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession


def _seed(
    TestingSession,
    *,
    organization_id: str = "org-a",
    organization_slug: str = "org-a",
    vehicle_count: int = 1,
) -> None:
    with TestingSession.begin() as session:
        if session.get(Organization, organization_id) is None:
            session.add(Organization(id=organization_id, slug=organization_slug, display_name=organization_id))
        for index in range(vehicle_count):
            session.add(
                MotiveVehicleRecord(
                    organization_id=organization_id,
                    organization_slug=organization_slug,
                    provider_vehicle_id=f"veh-{index}",
                )
            )


def _rollup_item(
    provider_vehicle_id: str,
    *,
    metric_units: Any = True,
    utilization: Any = 50,
    idle_time: Any = 1,
    driving_time: Any = 2,
    idle_fuel: Any = 3,
    driving_fuel: Any = 4,
    vin: str = UNSAFE_VIN,
    unit_number: str = UNSAFE_UNIT_NUMBER,
    email: str = UNSAFE_DRIVER_EMAIL,
) -> dict[str, Any]:
    return {
        "vehicle_idle_rollup": {
            "vehicle": {
                "id": provider_vehicle_id,
                "metric_units": metric_units,
                "vin": vin,
                "number": unit_number,
                "email": email,
            },
            "utilization": utilization,
            "idle_time": idle_time,
            "driving_time": driving_time,
            "idle_fuel": idle_fuel,
            "driving_fuel": driving_fuel,
        }
    }


def _page(
    rollup_items: list[dict[str, Any]],
    *,
    page_no: int = 1,
    per_page: int = 100,
    total: int | None = None,
    pagination_override: Any = "__unset__",
) -> dict[str, Any]:
    payload: dict[str, Any] = {"vehicle_idle_rollups": rollup_items}
    if pagination_override != "__unset__":
        payload["pagination"] = pagination_override
    else:
        payload["pagination"] = {
            "per_page": per_page,
            "page_no": page_no,
            "total": len(rollup_items) if total is None else total,
        }
    return payload


def _client_for_pages(pages: list[dict[str, Any]], calls: list[httpx.Request], *, status_code: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status_code, json=pages[len(calls) - 1])

    return httpx.Client(transport=httpx.MockTransport(handler))


def _row_count(TestingSession) -> int:
    with TestingSession() as session:
        return session.query(MotiveVehicleUtilizationRecord).count()


def _checkpoint_and_history_counts(TestingSession) -> tuple[int, int]:
    with TestingSession() as session:
        return (
            session.query(MotiveSyncCheckpoint).count(),
            session.query(MotiveSyncHistory).count(),
        )


def _enable_both_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    monkeypatch.setenv(RECENT_RECONCILIATION_VALIDATION_ENABLED_ENV_VAR, "true")


def _patch_route_with_mock_client(monkeypatch: pytest.MonkeyPatch, mock_client: httpx.Client) -> None:
    """Inject a mocked httpx.Client into the real orchestration function so
    the route's real code path runs end to end without ever making a real
    HTTP request. Mirrors the sibling controlled-write test suite's
    established pattern."""
    monkeypatch.setattr(
        motive_api,
        "run_recent_vehicle_utilization_reconciliation_live_validation",
        lambda session, **kwargs: run_recent_vehicle_utilization_reconciliation_live_validation(
            session, http_client=mock_client, **kwargs
        ),
    )


def _call_route(
    TestingSession,
    *,
    confirm: bool = True,
    organization_id: str = "org-a",
    principal: AuthenticatedPrincipal | None = None,
) -> dict[str, Any]:
    with TestingSession() as session:
        return motive_api.verify_motive_vehicle_utilization_recent_reconciliation(
            body=motive_api.VehicleUtilizationRecentReconciliationValidationRequest(confirm=confirm),
            principal=principal or _principal(organization_id),
            session=session,
        )


# ---------------------------------------------------------------------------
# Constants / bounds sanity.
# ---------------------------------------------------------------------------
def test_horizon_is_hardcoded_to_one_day() -> None:
    assert RECENT_RECONCILIATION_VALIDATION_HORIZON_DAYS == 1


def test_max_selected_vehicles_is_100() -> None:
    assert RECENT_RECONCILIATION_VALIDATION_MAX_SELECTED_VEHICLES == 100


def test_max_windows_batches_pages_calls_are_all_one() -> None:
    assert RECENT_RECONCILIATION_VALIDATION_MAX_WINDOWS == 1
    assert RECENT_RECONCILIATION_VALIDATION_MAX_BATCHES == 1
    assert RECENT_RECONCILIATION_VALIDATION_MAX_PAGES == 1
    assert RECENT_RECONCILIATION_VALIDATION_MAX_PROVIDER_CALLS == 1


def test_validation_flag_is_genuinely_separate_from_runner_flag() -> None:
    assert RECENT_RECONCILIATION_VALIDATION_ENABLED_ENV_VAR != RECENT_RECONCILIATION_ENABLED_ENV_VAR
    assert RECENT_RECONCILIATION_VALIDATION_ENABLED_ENV_VAR == "MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_VALIDATION_ENABLED"


def test_request_body_accepts_only_confirm_field() -> None:
    fields = motive_api.VehicleUtilizationRecentReconciliationValidationRequest.model_fields
    assert set(fields) == {"confirm"}
    assert fields["confirm"].default is False


def test_route_registered_at_expected_path() -> None:
    route_paths = {getattr(route, "path", "") for route in motive_api.router.routes}
    assert "/api/v1/motive/verify/vehicle-utilization-recent-reconciliation" in route_paths


def test_route_requires_connector_write_permission_source() -> None:
    source = inspect.getsource(motive_api.verify_motive_vehicle_utilization_recent_reconciliation)
    assert "require_permission(Permission.CONNECTOR_WRITE)" in source


def test_route_never_accepts_horizon_days_or_other_parameters_from_caller() -> None:
    # Only "confirm" is an accepted field -- horizon_days, dates, vehicle
    # ids, batch/page size, and retry options can never be supplied by a
    # caller regardless of what the model's docstring prose discusses.
    assert set(motive_api.VehicleUtilizationRecentReconciliationValidationRequest.model_fields) == {"confirm"}


# ---------------------------------------------------------------------------
# A/B/C -- disabled-flag matrix. Every combination fails closed with zero
# provider calls, before the orchestration function (and therefore the
# runner and any provider HTTP) is ever invoked.
# ---------------------------------------------------------------------------
def _assert_disabled(TestingSession, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("live validation orchestration must not run while a required flag is disabled")

    monkeypatch.setattr(motive_api, "run_recent_vehicle_utilization_reconciliation_live_validation", fail_if_called)
    checkpoints_before, history_before = _checkpoint_and_history_counts(TestingSession)

    with pytest.raises(HTTPException) as exc_info:
        _call_route(TestingSession)

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert detail["error_code"] == "recent_reconciliation_validation_disabled"
    assert detail["provider_calls_attempted"] == 0
    assert detail["provider_calls_completed"] == 0
    assert detail["checkpoint_advanced"] is False
    assert detail["sync_history_written"] is False
    assert detail["scheduled_ingestion_enabled"] is False
    assert _row_count(TestingSession) == 0
    checkpoints_after, history_after = _checkpoint_and_history_counts(TestingSession)
    assert checkpoints_after == checkpoints_before
    assert history_after == history_before


def test_a_route_flag_false_runner_flag_true_returns_503_zero_calls(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    monkeypatch.delenv(RECENT_RECONCILIATION_VALIDATION_ENABLED_ENV_VAR, raising=False)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession)
    _assert_disabled(TestingSession, monkeypatch)


def test_b_runner_flag_false_route_flag_true_returns_503_zero_calls(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, raising=False)
    monkeypatch.setenv(RECENT_RECONCILIATION_VALIDATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession)
    _assert_disabled(TestingSession, monkeypatch)


def test_c_both_flags_false_returns_503_zero_calls(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, raising=False)
    monkeypatch.delenv(RECENT_RECONCILIATION_VALIDATION_ENABLED_ENV_VAR, raising=False)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession)
    _assert_disabled(TestingSession, monkeypatch)


def test_orchestration_function_itself_fails_closed_when_runner_flag_disabled(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, raising=False)
    monkeypatch.setenv(RECENT_RECONCILIATION_VALIDATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession)
    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationRecentReconciliationValidationError) as exc_info:
            run_recent_vehicle_utilization_reconciliation_live_validation(
                session, organization_id="org-a", organization_slug="org-a"
            )
    assert exc_info.value.code == "recent_reconciliation_disabled"


def test_orchestration_function_itself_fails_closed_when_route_flag_disabled(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    monkeypatch.delenv(RECENT_RECONCILIATION_VALIDATION_ENABLED_ENV_VAR, raising=False)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession)
    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationRecentReconciliationValidationError) as exc_info:
            run_recent_vehicle_utilization_reconciliation_live_validation(
                session, organization_id="org-a", organization_slug="org-a"
            )
    assert exc_info.value.code == "recent_reconciliation_validation_disabled"


# ---------------------------------------------------------------------------
# D -- confirmation required.
# ---------------------------------------------------------------------------
def test_d_confirm_false_returns_400_zero_calls(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession)

    def fail_if_called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("must not run without explicit confirmation")

    monkeypatch.setattr(motive_api, "run_recent_vehicle_utilization_reconciliation_live_validation", fail_if_called)

    with pytest.raises(HTTPException) as exc_info:
        _call_route(TestingSession, confirm=False)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error_code"] == "confirmation_required"
    assert _row_count(TestingSession) == 0


def test_d_confirm_missing_defaults_to_rejected(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession)

    def fail_if_called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("must not run without explicit confirmation")

    monkeypatch.setattr(motive_api, "run_recent_vehicle_utilization_reconciliation_live_validation", fail_if_called)

    with TestingSession() as session:
        with pytest.raises(HTTPException) as exc_info:
            motive_api.verify_motive_vehicle_utilization_recent_reconciliation(principal=_principal("org-a"), session=session)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error_code"] == "confirmation_required"


# ---------------------------------------------------------------------------
# E -- missing CONNECTOR_WRITE permission.
# ---------------------------------------------------------------------------
def test_e_missing_connector_write_permission_is_rejected_before_route_body() -> None:
    principal_without_write = _principal("org-a", permissions=frozenset({Permission.CONNECTOR_READ}))
    with pytest.raises(HTTPException) as exc_info:
        require_permission(Permission.CONNECTOR_WRITE)(principal=principal_without_write)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# F -- zero eligible vehicles.
# ---------------------------------------------------------------------------
def test_f_zero_vehicles_is_success_no_op_zero_provider_calls(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, vehicle_count=0)
    calls: list[httpx.Request] = []
    _patch_route_with_mock_client(monkeypatch, _client_for_pages([], calls))

    result = _call_route(TestingSession)

    assert result["status"] == "no_op"
    assert result["provider_calls_attempted"] == 0
    assert result["provider_calls_completed"] == 0
    assert result["selected_vehicle_count"] == 0
    assert len(calls) == 0
    assert _row_count(TestingSession) == 0
    assert result["checkpoint_advanced"] is False
    assert result["sync_history_written"] is False
    assert result["scheduled_ingestion_enabled"] is False


# ---------------------------------------------------------------------------
# G -- one vehicle: runner invoked with horizon_days=1, exactly one call.
# ---------------------------------------------------------------------------
def test_g_one_vehicle_invokes_runner_with_horizon_one_and_at_most_one_call(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, vehicle_count=1)
    calls: list[httpx.Request] = []
    pages = [_page([_rollup_item("veh-0")], total=1)]
    _patch_route_with_mock_client(monkeypatch, _client_for_pages(pages, calls))

    result = _call_route(TestingSession)

    assert len(calls) == 1
    request = calls[0]
    assert request.url.params["start_date"] == FIXED_END_DATE.isoformat()
    assert request.url.params["end_date"] == FIXED_END_DATE.isoformat()
    assert result["status"] == "success"
    assert result["horizon_days"] == 1
    assert result["provider_calls_attempted"] == 1
    assert result["provider_calls_completed"] == 1


def test_g_orchestration_calls_runner_with_hardcoded_horizon_days_one(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, vehicle_count=1)
    observed: dict[str, Any] = {}
    real_runner = runner_module.run_recent_vehicle_utilization_reconciliation

    def capturing_runner(session, **kwargs):
        observed.update(kwargs)
        return real_runner(session, **kwargs)

    import app.motive.vehicle_utilization_recent_reconciliation_validation as validation_module

    monkeypatch.setattr(validation_module, "run_recent_vehicle_utilization_reconciliation", capturing_runner)
    pages = [_page([_rollup_item("veh-0")], total=1)]
    calls: list[httpx.Request] = []
    with TestingSession() as session:
        run_recent_vehicle_utilization_reconciliation_live_validation(
            session, organization_id="org-a", organization_slug="org-a", http_client=_client_for_pages(pages, calls)
        )

    assert observed["horizon_days"] == 1


# ---------------------------------------------------------------------------
# H / I -- vehicle-count bound: 100 allowed, 101 fails closed pre-flight.
# ---------------------------------------------------------------------------
def test_h_exactly_100_vehicles_is_allowed_max_one_call(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, vehicle_count=100)
    calls: list[httpx.Request] = []
    pages = [_page([_rollup_item("veh-0")], total=1)]
    _patch_route_with_mock_client(monkeypatch, _client_for_pages(pages, calls))

    result = _call_route(TestingSession)

    assert result["selected_vehicle_count"] == 100
    assert len(calls) == 1
    assert result["provider_calls_attempted"] == 1


def test_i_101_vehicles_fails_closed_before_any_provider_http(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, vehicle_count=101)
    calls: list[httpx.Request] = []
    _patch_route_with_mock_client(monkeypatch, _client_for_pages([], calls))

    with pytest.raises(HTTPException) as exc_info:
        _call_route(TestingSession)

    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert detail["error_code"] == "controlled_validation_vehicle_limit_exceeded"
    assert detail["eligible_vehicle_count"] == 101
    assert detail["max_selected_vehicles"] == 100
    assert detail["provider_calls_attempted"] == 0
    assert len(calls) == 0
    assert _row_count(TestingSession) == 0
    # No vehicle identity in the error detail.
    assert "veh-0" not in repr(detail)


# ---------------------------------------------------------------------------
# J/K/L/M -- success matrix (insert, exact replay, correction, omission).
# ---------------------------------------------------------------------------
def test_j_success_with_insert_200_one_call_no_checkpoint_or_history(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, vehicle_count=1)
    checkpoints_before, history_before = _checkpoint_and_history_counts(TestingSession)
    calls: list[httpx.Request] = []
    pages = [_page([_rollup_item("veh-0")], total=1)]
    _patch_route_with_mock_client(monkeypatch, _client_for_pages(pages, calls))

    result = _call_route(TestingSession)

    assert result["status"] == "success"
    assert len(calls) == 1
    assert result["records_inserted"] == 1
    assert result["checkpoint_advanced"] is False
    assert result["sync_history_written"] is False
    assert result["scheduled_ingestion_enabled"] is False
    assert _row_count(TestingSession) == 1
    checkpoints_after, history_after = _checkpoint_and_history_counts(TestingSession)
    assert checkpoints_after == checkpoints_before
    assert history_after == history_before


def test_k_exact_replay_reports_records_unchanged(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, vehicle_count=1)
    pages = [_page([_rollup_item("veh-0")], total=1)]

    _patch_route_with_mock_client(monkeypatch, _client_for_pages(pages, []))
    first = _call_route(TestingSession)
    assert first["records_inserted"] == 1

    _patch_route_with_mock_client(monkeypatch, _client_for_pages(pages, []))
    second = _call_route(TestingSession)

    assert second["status"] == "success"
    assert second["records_inserted"] == 0
    assert second["records_unchanged"] == 1
    assert second["records_updated"] == 0
    assert _row_count(TestingSession) == 1


def test_l_provider_correction_reports_records_updated(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, vehicle_count=1)

    _patch_route_with_mock_client(monkeypatch, _client_for_pages([_page([_rollup_item("veh-0", idle_time=100)], total=1)], []))
    _call_route(TestingSession)

    _patch_route_with_mock_client(monkeypatch, _client_for_pages([_page([_rollup_item("veh-0", idle_time=999)], total=1)], []))
    result = _call_route(TestingSession)

    assert result["status"] == "success"
    assert result["records_inserted"] == 0
    assert result["records_unchanged"] == 0
    assert result["records_updated"] == 1
    assert result["reconciled_fields_count"] == 1
    assert _row_count(TestingSession) == 1
    with TestingSession() as session:
        row = session.query(MotiveVehicleUtilizationRecord).one()
        assert row.idle_time == Decimal("999")


def test_m_provider_omission_creates_no_synthetic_row(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, vehicle_count=2)  # veh-0, veh-1
    calls: list[httpx.Request] = []
    # provider omits veh-1 from the response entirely.
    pages = [_page([_rollup_item("veh-0")], total=1)]
    _patch_route_with_mock_client(monkeypatch, _client_for_pages(pages, calls))

    result = _call_route(TestingSession)

    assert result["status"] == "success"
    assert result["missing_requested_vehicle_count"] == 1
    assert _row_count(TestingSession) == 1
    with TestingSession() as session:
        row = session.query(MotiveVehicleUtilizationRecord).one()
        assert row.provider_vehicle_id == "veh-0"


# ---------------------------------------------------------------------------
# N -- known provider HTTP error -> safe 502, sanitized body.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("status_code", "expected_code"), [(500, "provider_unavailable"), (429, "rate_limited"), (401, "authorization_required")])
def test_n_known_provider_http_error_maps_to_safe_502(
    tmp_path, monkeypatch: pytest.MonkeyPatch, status_code: int, expected_code: str
) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, vehicle_count=1)
    calls: list[httpx.Request] = []
    _patch_route_with_mock_client(monkeypatch, _client_for_pages([{"error": "boom"}], calls, status_code=status_code))

    with pytest.raises(HTTPException) as exc_info:
        _call_route(TestingSession)

    assert len(calls) == 1
    assert exc_info.value.status_code == 502
    detail = exc_info.value.detail
    assert detail["error_code"] == expected_code
    assert detail["status"] == "failed"
    assert _row_count(TestingSession) == 0
    assert FAKE_API_KEY not in repr(detail)


# ---------------------------------------------------------------------------
# O -- pagination/unit/writer safe failure -> safe 502, sanitized body.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("build_pages", "expected_code"),
    [
        (lambda: [_page([_rollup_item("veh-0")], total=2)], "cumulative_rollup_count_below_total"),
        (lambda: [_page([_rollup_item("veh-0"), _rollup_item("veh-0")], total=2)], "duplicate_vehicle_observed"),
        (lambda: [_page([_rollup_item("veh-unexpected")], total=1)], "unexpected_vehicle_observed"),
    ],
)
def test_o_pagination_safe_failure_maps_to_502(
    tmp_path, monkeypatch: pytest.MonkeyPatch, build_pages, expected_code: str
) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, vehicle_count=1)
    calls: list[httpx.Request] = []
    _patch_route_with_mock_client(monkeypatch, _client_for_pages(build_pages(), calls))

    with pytest.raises(HTTPException) as exc_info:
        _call_route(TestingSession)

    assert len(calls) == 1
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["error_code"] == expected_code
    assert _row_count(TestingSession) == 0


def test_o_unresolved_unit_indicator_writer_failure_maps_to_502(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, vehicle_count=1)
    calls: list[httpx.Request] = []
    pages = [_page([_rollup_item("veh-0", metric_units=None)], total=1)]
    _patch_route_with_mock_client(monkeypatch, _client_for_pages(pages, calls))

    with pytest.raises(HTTPException) as exc_info:
        _call_route(TestingSession)

    assert len(calls) == 1
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["error_code"] == "provider_unit_indicator_semantics_unresolved"
    assert _row_count(TestingSession) == 0


# ---------------------------------------------------------------------------
# P -- unexpected exception -> safe 500, sanitized body, no raw details.
# ---------------------------------------------------------------------------
def test_p_unexpected_exception_maps_to_sanitized_500(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, vehicle_count=1)

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("some sensitive internal detail that must never leak: sk-secret-token-123")

    monkeypatch.setattr(motive_api, "run_recent_vehicle_utilization_reconciliation_live_validation", boom)

    with pytest.raises(HTTPException) as exc_info:
        _call_route(TestingSession)

    assert exc_info.value.status_code == 500
    detail = exc_info.value.detail
    assert detail["error_code"] == "unexpected_error"
    assert "sk-secret-token-123" not in repr(detail)
    assert "RuntimeError" not in repr(detail)


def test_p_provider_call_budget_invariant_violation_maps_to_500(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Defense-in-depth: if the orchestration function's own post-hoc
    one-call assertion is ever violated, that is a genuine invariant
    failure, not an expected/sanitized rejection, and must map to 500."""
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, vehicle_count=1)

    def fake_orchestration(session, **_kwargs: Any) -> Any:
        raise MotiveVehicleUtilizationRecentReconciliationValidationError(
            "provider_call_budget_invariant_violated",
            "synthetic invariant violation for test",
            provider_calls_attempted=2,
            provider_calls_completed=2,
        )

    monkeypatch.setattr(motive_api, "run_recent_vehicle_utilization_reconciliation_live_validation", fake_orchestration)

    with pytest.raises(HTTPException) as exc_info:
        _call_route(TestingSession)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail["error_code"] == "provider_call_budget_invariant_violated"


def test_no_known_error_code_maps_to_http_500_except_the_genuine_invariant_violation() -> None:
    """Locks in the same status-mapping lesson already fixed once in
    ``_controlled_write_http_status``: every EXPECTED, sanitized, safely
    caught rejection this route's own pre-flight raises must map to a
    non-500 status; only a genuine invariant violation may map to 500."""
    expected_non_500_codes = {
        "recent_reconciliation_disabled": 503,
        "recent_reconciliation_validation_disabled": 503,
        "controlled_validation_vehicle_limit_exceeded": 409,
    }
    for code, expected_status in expected_non_500_codes.items():
        exc = MotiveVehicleUtilizationRecentReconciliationValidationError(code, "synthetic")
        assert motive_api._recent_reconciliation_validation_http_status(exc) == expected_status

    invariant_exc = MotiveVehicleUtilizationRecentReconciliationValidationError(
        "provider_call_budget_invariant_violated", "synthetic"
    )
    assert motive_api._recent_reconciliation_validation_http_status(invariant_exc) == 500


# ---------------------------------------------------------------------------
# Q -- security: response never contains secrets, vehicle identity, VIN,
# driver PII, raw metrics, or raw provider payload.
# ---------------------------------------------------------------------------
def test_q_response_never_contains_sensitive_values(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, vehicle_count=1)
    calls: list[httpx.Request] = []
    pages = [_page([_rollup_item("veh-0")], total=1)]
    _patch_route_with_mock_client(monkeypatch, _client_for_pages(pages, calls))

    result = _call_route(TestingSession)

    serialized = repr(result)
    forbidden_tokens = [
        FAKE_API_KEY,
        "x-api-key",
        "X-API-Key",
        "Authorization",
        "Bearer",
        "veh-0",
        UNSAFE_VIN,
        UNSAFE_UNIT_NUMBER,
        UNSAFE_DRIVER_EMAIL,
    ]
    for token in forbidden_tokens:
        assert token not in serialized, f"forbidden token {token!r} leaked into the response"


def test_q_failed_response_never_contains_sensitive_values(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, vehicle_count=1)
    calls: list[httpx.Request] = []
    pages = [_page([_rollup_item("veh-unexpected")], total=1)]
    _patch_route_with_mock_client(monkeypatch, _client_for_pages(pages, calls))

    with pytest.raises(HTTPException) as exc_info:
        _call_route(TestingSession)

    serialized = repr(exc_info.value.detail)
    forbidden_tokens = [FAKE_API_KEY, "Authorization", "Bearer", "veh-0", "veh-unexpected", UNSAFE_VIN, UNSAFE_DRIVER_EMAIL]
    for token in forbidden_tokens:
        assert token not in serialized


# ---------------------------------------------------------------------------
# Section 13 -- checkpoint / history / scheduler always false, never touched.
# ---------------------------------------------------------------------------
def test_checkpoint_and_history_always_false_and_never_persisted(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_both_flags(monkeypatch)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, vehicle_count=1)
    before = _checkpoint_and_history_counts(TestingSession)
    calls: list[httpx.Request] = []
    pages = [_page([_rollup_item("veh-0")], total=1)]
    _patch_route_with_mock_client(monkeypatch, _client_for_pages(pages, calls))

    result = _call_route(TestingSession)

    after = _checkpoint_and_history_counts(TestingSession)
    assert before == after
    assert result["checkpoint_advanced"] is False
    assert result["sync_history_written"] is False
    assert result["scheduled_ingestion_enabled"] is False


def test_no_scheduler_or_cron_code_in_new_module_source() -> None:
    from app.motive import vehicle_utilization_recent_reconciliation_validation as validation_module

    source = inspect.getsource(validation_module)
    assert not hasattr(validation_module, "APIRouter")
    assert not hasattr(validation_module, "router")
    assert "celery" not in source.lower()
    assert "cron" not in source.lower()
    assert "@scheduler" not in source.lower()
