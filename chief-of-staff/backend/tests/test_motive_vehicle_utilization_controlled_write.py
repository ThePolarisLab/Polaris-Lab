"""Tests for the controlled, feature-flagged Motive vehicle-utilization WRITE
validation gate (sections 20-30 of the controlled write validation spec).

This gate proves the tightly bounded path:
certified Motive pagination read (ONE page, ONE provider call) -> certified
parser/unit validation -> merged all-or-nothing utilization writer transaction
for the fixed historical day 2026-08-13..2026-08-13.

No live Motive provider call is made anywhere in this module. All provider
interaction is mocked via ``httpx.MockTransport``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import inspect
import logging
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
from app.motive import vehicle_utilization_writer as writer_module
from app.motive.vehicle_utilization_controlled_write import (
    CONTROLLED_WRITE_ENABLED_ENV_VAR,
    CONTROLLED_WRITE_MAX_SELECTED_VEHICLES,
    CONTROLLED_WRITE_PAGE_SIZE,
    CONTROLLED_WRITE_WINDOW_END,
    CONTROLLED_WRITE_WINDOW_START,
    MotiveVehicleUtilizationControlledWriteError,
    controlled_write_enabled,
    run_controlled_vehicle_utilization_write,
)
from app.motive.vehicle_utilization_unit_policy import VehicleUtilizationUnitPersistenceReadiness
from app.organizations.models import Organization
from app.security.models import AuthenticatedPrincipal, Permission

register_models()

UNSAFE_PROVIDER_VEHICLE_ID = "provider-vehicle-should-not-leak-4471"
UNSAFE_VIN = "VINSHOULDNOTLEAK12"
UNSAFE_UNIT_NUMBER = "unit-should-not-leak-778"
UNSAFE_UTILIZATION = "13.3700"
FAKE_API_KEY = "fake-motive-secret"


# ---------------------------------------------------------------------------
# 2026-08-16 unit-context reconciliation gate.
#
# The controlled route's read stage no longer performs its own returned-
# unit-indicator check (provider schema parse success is distinct from
# durable persistence readiness). The single source of truth is now the
# writer transaction's persistence-readiness gate
# (app.motive.vehicle_utilization_writer), which fails closed for every
# returned unit-indicator value -- True included -- until Motive's semantics
# are explicitly certified. Tests marked ``unit_readiness_gate`` exercise
# that real, fail-closed behavior directly, matching the one real controlled
# production validation recorded in
# docs/engineering/MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md. The rest of
# this suite (pagination bounds, tenant isolation, replay, sanitization) is
# orthogonal to unit-indicator semantics and is bypassed past the still-
# unresolved gate so it can keep exercising what it was written to prove.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _bypass_unresolved_unit_gate_for_unrelated_concerns(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    if request.node.get_closest_marker("unit_readiness_gate") is not None:
        yield
        return
    monkeypatch.setattr(
        writer_module,
        "validate_vehicle_utilization_unit_persistence_readiness",
        lambda returned_metric_units: VehicleUtilizationUnitPersistenceReadiness(ready_for_durable_persistence=True),
    )
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


def _session_factory(tmp_path, name: str = "controlled-write"):
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
    provider_vehicle_ids: tuple[str, ...] = ("veh-1", "veh-2", "veh-3"),
) -> None:
    with TestingSession.begin() as session:
        if session.get(Organization, organization_id) is None:
            session.add(Organization(id=organization_id, slug=organization_slug, display_name=organization_id))
        for provider_vehicle_id in provider_vehicle_ids:
            session.add(
                MotiveVehicleRecord(
                    organization_id=organization_id,
                    organization_slug=organization_slug,
                    provider_vehicle_id=provider_vehicle_id,
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
) -> dict[str, Any]:
    return {
        "vehicle_idle_rollup": {
            "vehicle": {
                "id": provider_vehicle_id,
                "metric_units": metric_units,
                "vin": vin,
                "number": unit_number,
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
    per_page: int = CONTROLLED_WRITE_PAGE_SIZE,
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


def _raising_client(exc: Exception, calls: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise exc

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


def _run_controlled_write(
    TestingSession,
    *,
    pages: list[dict[str, Any]] | None = None,
    calls: list[httpx.Request] | None = None,
    http_client: httpx.Client | None = None,
    organization_id: str = "org-a",
    organization_slug: str = "org-a",
    selected_provider_vehicle_ids: tuple[str, ...] = ("veh-1", "veh-2", "veh-3"),
    status_code: int = 200,
) -> dict[str, Any]:
    observed_calls = calls if calls is not None else []
    client = http_client or _client_for_pages(pages or [], observed_calls, status_code=status_code)
    with TestingSession() as session:
        return run_controlled_vehicle_utilization_write(
            session,
            organization_id=organization_id,
            organization_slug=organization_slug,
            selected_provider_vehicle_ids=list(selected_provider_vehicle_ids),
            http_client=client,
        )


# ---------------------------------------------------------------------------
# Section 20 -- disabled by default.
# ---------------------------------------------------------------------------
def test_flag_defaults_disabled_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CONTROLLED_WRITE_ENABLED_ENV_VAR, raising=False)
    assert controlled_write_enabled() is False


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "", "garbage", "TrUe_typo"])
def test_flag_disabled_for_falsy_or_unrecognized_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(CONTROLLED_WRITE_ENABLED_ENV_VAR, value)
    assert controlled_write_enabled() is False


@pytest.mark.parametrize("value", ["true", "1", "yes", "on", "TRUE", "On"])
def test_flag_enabled_only_for_explicit_truthy_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(CONTROLLED_WRITE_ENABLED_ENV_VAR, value)
    assert controlled_write_enabled() is True


def test_route_returns_safe_disabled_response_and_makes_zero_calls_or_writes(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CONTROLLED_WRITE_ENABLED_ENV_VAR, raising=False)

    def fail_if_called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("controlled write orchestration must not run while the flag is disabled")

    monkeypatch.setattr(motive_api, "run_controlled_vehicle_utilization_write", fail_if_called)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession)
    checkpoints_before, history_before = _checkpoint_and_history_counts(TestingSession)

    with TestingSession() as session:
        with pytest.raises(HTTPException) as exc_info:
            motive_api.verify_motive_vehicle_utilization_write(
                body=motive_api.VehicleUtilizationControlledWriteRequest(confirm=True),
                principal=_principal("org-a"),
                session=session,
            )

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert detail["error_code"] == "controlled_write_disabled"
    assert detail["provider_calls_attempted"] == 0
    assert detail["provider_calls_completed"] == 0
    assert detail["checkpoint_advanced"] is False
    assert detail["sync_history_written"] is False
    assert _row_count(TestingSession) == 0
    checkpoints_after, history_after = _checkpoint_and_history_counts(TestingSession)
    assert checkpoints_after == checkpoints_before
    assert history_after == history_before


def test_route_disabled_when_flag_explicitly_false(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONTROLLED_WRITE_ENABLED_ENV_VAR, "false")

    def fail_if_called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("controlled write orchestration must not run while the flag is disabled")

    monkeypatch.setattr(motive_api, "run_controlled_vehicle_utilization_write", fail_if_called)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession)

    with TestingSession() as session:
        with pytest.raises(HTTPException) as exc_info:
            motive_api.verify_motive_vehicle_utilization_write(
                body=motive_api.VehicleUtilizationControlledWriteRequest(confirm=True),
                principal=_principal("org-a"),
                session=session,
            )
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error_code"] == "controlled_write_disabled"


def test_route_requires_connector_write_permission() -> None:
    route_paths = {getattr(route, "path", "") for route in motive_api.router.routes}
    source = inspect.getsource(motive_api.verify_motive_vehicle_utilization_write)
    assert "/api/v1/motive/verify/vehicle-utilization-write" in route_paths
    assert "require_permission(Permission.CONNECTOR_WRITE)" in source


def test_route_is_not_the_normal_sync_route() -> None:
    route_paths = {getattr(route, "path", "") for route in motive_api.router.routes}
    assert "/api/v1/motive/sync/vehicle-utilization" not in route_paths


def test_confirmation_required_before_provider_call(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONTROLLED_WRITE_ENABLED_ENV_VAR, "true")

    def fail_if_called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("controlled write orchestration must not run without explicit confirmation")

    monkeypatch.setattr(motive_api, "run_controlled_vehicle_utilization_write", fail_if_called)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession)

    with TestingSession() as session:
        with pytest.raises(HTTPException) as exc_info:
            motive_api.verify_motive_vehicle_utilization_write(
                body=motive_api.VehicleUtilizationControlledWriteRequest(confirm=False),
                principal=_principal("org-a"),
                session=session,
            )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error_code"] == "confirmation_required"
    assert _row_count(TestingSession) == 0


def test_missing_confirmation_defaults_to_rejected(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONTROLLED_WRITE_ENABLED_ENV_VAR, "true")

    def fail_if_called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("controlled write orchestration must not run without explicit confirmation")

    monkeypatch.setattr(motive_api, "run_controlled_vehicle_utilization_write", fail_if_called)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession)

    with TestingSession() as session:
        with pytest.raises(HTTPException) as exc_info:
            motive_api.verify_motive_vehicle_utilization_write(
                principal=_principal("org-a"),
                session=session,
            )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error_code"] == "confirmation_required"


def test_route_fails_safely_with_no_stored_vehicle(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONTROLLED_WRITE_ENABLED_ENV_VAR, "true")

    def fail_if_called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("controlled write orchestration must not run without a stored vehicle")

    monkeypatch.setattr(motive_api, "run_controlled_vehicle_utilization_write", fail_if_called)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=())

    with TestingSession() as session:
        with pytest.raises(HTTPException) as exc_info:
            motive_api.verify_motive_vehicle_utilization_write(
                body=motive_api.VehicleUtilizationControlledWriteRequest(confirm=True),
                principal=_principal("org-a"),
                session=session,
            )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error_code"] == "no_stored_vehicle"
    assert exc_info.value.detail["provider_calls_attempted"] == 0


# ---------------------------------------------------------------------------
# Section 21 -- exact request bounds.
# ---------------------------------------------------------------------------
def test_exact_request_bounds(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3", "veh-4"))
    calls: list[httpx.Request] = []
    pages = [_page([_rollup_item("veh-1")], total=1)]

    result = _run_controlled_write(
        TestingSession,
        pages=pages,
        calls=calls,
        selected_provider_vehicle_ids=("veh-1", "veh-2", "veh-3"),
    )

    assert len(calls) == 1
    request = calls[0]
    assert request.url.path == "/v1/vehicle_utilization"
    assert request.url.params["start_date"] == "2026-08-13"
    assert request.url.params["end_date"] == "2026-08-13"
    assert request.url.params["page_no"] == "1"
    assert request.url.params["per_page"] == "100"
    assert request.headers["X-Metric-Units"] == "true"
    assert "X-Time-Zone" not in request.headers
    assert "X-User-Id" not in request.headers
    assert result["selected_vehicle_count"] == 3
    assert result["provider_calls_attempted"] == 1
    assert result["provider_calls_completed"] == 1
    assert result["request_window_start"] == "2026-08-13"
    assert result["request_window_end"] == "2026-08-13"


def test_selected_vehicle_count_is_capped_at_three(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3", "veh-4", "veh-5"))
    calls: list[httpx.Request] = []
    pages = [_page([], total=0)]

    result = _run_controlled_write(
        TestingSession,
        pages=pages,
        calls=calls,
        selected_provider_vehicle_ids=("veh-1", "veh-2", "veh-3", "veh-4", "veh-5"),
    )

    assert result["selected_vehicle_count"] == CONTROLLED_WRITE_MAX_SELECTED_VEHICLES
    assert [key for key, _v in calls[0].url.params.multi_items() if key == "vehicle_ids[]"].__len__() == 3


# ---------------------------------------------------------------------------
# Section 22 -- success insert (WITH the unit gate bypassed -- see the
# module-level fixture -- to prove the read-to-write plumbing, sanitized
# response shape, and durable row fields independent of the currently-
# unresolved unit-indicator semantics).
# ---------------------------------------------------------------------------
def test_success_insert_persists_certified_row(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    checkpoints_before, history_before = _checkpoint_and_history_counts(TestingSession)
    pages = [_page([_rollup_item("veh-1")], total=1)]

    result = _run_controlled_write(TestingSession, pages=pages)

    assert result["status"] == "success"
    assert result["provider_calls_attempted"] == 1
    assert result["provider_calls_completed"] == 1
    assert result["pagination_total"] == 1
    assert result["returned_rollup_count"] == 1
    assert result["missing_requested_vehicle_count"] == 2
    assert result["records_inserted"] == 1
    assert result["records_unchanged"] == 0
    assert result["records_updated"] == 0
    assert result["committed"] is True
    assert result["checkpoint_advanced"] is False
    assert result["sync_history_written"] is False
    assert result["scheduled_ingestion_enabled"] is False

    with TestingSession() as session:
        row = session.query(MotiveVehicleUtilizationRecord).one()
        assert row.organization_id == "org-a"
        assert row.provider_vehicle_id == "veh-1"
        assert row.request_window_start == CONTROLLED_WRITE_WINDOW_START
        assert row.request_window_end == CONTROLLED_WRITE_WINDOW_END
        assert row.metric_units is True

    checkpoints_after, history_after = _checkpoint_and_history_counts(TestingSession)
    assert checkpoints_after == checkpoints_before
    assert history_after == history_before


# ---------------------------------------------------------------------------
# Section 1/17 -- this is the real, non-bypassed shape of the route today.
# It reproduces the sanitized facts of the one real controlled production
# validation recorded in
# docs/engineering/MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md: one provider
# call, one returned rollup, zero rows inserted, zero checkpoint/history
# writes, safe failure. The controlled route always requests
# X-Metric-Units: true; the recorded evidence returned
# vehicle.metric_units=false, which Motive API Support's 2026-08-17 written
# reply confirmed is a provider-confirmed unit-context mismatch.
# ---------------------------------------------------------------------------
@pytest.mark.unit_readiness_gate
def test_route_fails_closed_matching_recorded_production_evidence(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    checkpoints_before, history_before = _checkpoint_and_history_counts(TestingSession)
    pages = [_page([_rollup_item("veh-1", metric_units=False)], total=1)]

    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=pages)

    assert exc_info.value.code == "provider_unit_policy_mismatch"
    assert exc_info.value.provider_calls_attempted == 1
    assert exc_info.value.provider_calls_completed == 1
    assert exc_info.value.selected_vehicle_count == 3
    assert exc_info.value.returned_rollup_count == 1
    assert _row_count(TestingSession) == 0
    checkpoints_after, history_after = _checkpoint_and_history_counts(TestingSession)
    assert checkpoints_after == checkpoints_before
    assert history_after == history_before


# ---------------------------------------------------------------------------
# 2026-08-17 controlled-utilization live-staging 500 diagnosis gate.
#
# The test above proves run_controlled_vehicle_utilization_write raises
# MotiveVehicleUtilizationControlledWriteError(code="provider_unit_policy_mismatch")
# for exactly this scenario -- matching the one real live controlled-route
# attempt made against staging on 2026-08-17, which returned a raw HTTP 500
# with no traceback in Render logs. Root cause (found and fixed by this
# gate): app.api.motive._controlled_write_http_status special-cased every
# writer-originated fail-closed code -- including "provider_unit_policy_mismatch"
# and "provider_unit_indicator_semantics_unresolved" -- to
# HTTP_500_INTERNAL_SERVER_ERROR, a status HTTP convention reserves for
# genuine server defects, not expected, safely-handled provider rejections
# (the disabled/confirmation-required/no-stored-vehicle paths already used
# 503/400/404 for their own expected-rejection cases). This was a
# deliberately-raised HTTPException(status_code=500), not an unhandled
# Python exception -- Starlette's HTTPException handling does not log a
# traceback for it, which is exactly why the live Render logs showed only
# the access-log line. The fix removes that special case so these codes
# fall through to the same HTTP_502_BAD_GATEWAY already used for read-stage
# provider-data rejections (pagination/parse failures) -- "the upstream
# provider's data could not be safely used" is an accurate description of
# every code in this bucket, read-stage or write-stage alike.
#
# These two tests now serve as regression tests for the fix: they prove
# that a real provider round trip occurred (provider_calls_attempted ==
# provider_calls_completed == 1, matching the one-call budget), that the
# writer still correctly failed closed with zero rows written and zero
# checkpoint/history mutation, and that the route now reports this as
# HTTP 502 rather than HTTP 500.
# ---------------------------------------------------------------------------
@pytest.mark.unit_readiness_gate
def test_route_reports_provider_unit_policy_mismatch_as_http_502(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test for the 2026-08-17 live-staging controlled-route 500.

    A provider-confirmed, correctly-fail-closed unit-context mismatch
    (exactly the scenario proven safe by
    test_route_fails_closed_matching_recorded_production_evidence above) is
    surfaced to the API caller as HTTP 502 Bad Gateway -- not the raw
    HTTP 500 this route returned before this gate's fix. This was a
    status-code mapping defect, not an unsafe-persistence defect: the
    transaction still rolls back, zero rows are written, and zero
    checkpoint/history mutation occurs -- confirmed by the assertions below.
    """
    monkeypatch.setenv(CONTROLLED_WRITE_ENABLED_ENV_VAR, "true")
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    checkpoints_before, history_before = _checkpoint_and_history_counts(TestingSession)
    pages = [_page([_rollup_item("veh-1", metric_units=False)], total=1)]
    calls: list[httpx.Request] = []
    mock_client = _client_for_pages(pages, calls)

    monkeypatch.setattr(
        motive_api,
        "run_controlled_vehicle_utilization_write",
        lambda session, **kwargs: run_controlled_vehicle_utilization_write(session, http_client=mock_client, **kwargs),
    )

    with TestingSession() as session:
        with pytest.raises(HTTPException) as exc_info:
            motive_api.verify_motive_vehicle_utilization_write(
                body=motive_api.VehicleUtilizationControlledWriteRequest(confirm=True),
                principal=_principal("org-a"),
                session=session,
            )

    # Reproduces the exact live-staging observation: a real provider round
    # trip occurred (provider_calls_attempted == provider_calls_completed ==
    # 1, matching the one-call budget), the writer correctly failed closed
    # on the unit-context mismatch, and the route now reports it as
    # HTTP 502 (fixed) rather than HTTP 500 (the bug this gate found).
    assert len(calls) == 1
    assert exc_info.value.status_code == 502
    detail = exc_info.value.detail
    assert detail["error_code"] == "provider_unit_policy_mismatch"
    assert detail["provider_calls_attempted"] == 1
    assert detail["provider_calls_completed"] == 1
    assert _row_count(TestingSession) == 0
    checkpoints_after, history_after = _checkpoint_and_history_counts(TestingSession)
    assert checkpoints_after == checkpoints_before
    assert history_after == history_before


@pytest.mark.unit_readiness_gate
def test_route_reports_missing_unit_indicator_as_http_502(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Same fixed status-code mapping for the other realistic live cause: a
    returned rollup with a missing/None metric_units indicator
    ("provider_unit_indicator_semantics_unresolved") now maps to HTTP 502,
    not the raw HTTP 500 this route returned before this gate's fix."""
    monkeypatch.setenv(CONTROLLED_WRITE_ENABLED_ENV_VAR, "true")
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    pages = [_page([_rollup_item("veh-1", metric_units=None)], total=1)]
    calls: list[httpx.Request] = []
    mock_client = _client_for_pages(pages, calls)

    monkeypatch.setattr(
        motive_api,
        "run_controlled_vehicle_utilization_write",
        lambda session, **kwargs: run_controlled_vehicle_utilization_write(session, http_client=mock_client, **kwargs),
    )

    with TestingSession() as session:
        with pytest.raises(HTTPException) as exc_info:
            motive_api.verify_motive_vehicle_utilization_write(
                body=motive_api.VehicleUtilizationControlledWriteRequest(confirm=True),
                principal=_principal("org-a"),
                session=session,
            )

    assert len(calls) == 1
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["error_code"] == "provider_unit_indicator_semantics_unresolved"
    assert _row_count(TestingSession) == 0


@pytest.mark.unit_readiness_gate
def test_no_controlled_write_error_code_maps_to_http_500(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Locks in the fix at the mapping-function level: no error code that
    MotiveVehicleUtilizationControlledWriteError or
    MotiveVehicleUtilizationWriterError can carry may map to HTTP 500.
    HTTP 500 is reserved for genuine unhandled exceptions escaping this
    route entirely (which FastAPI/Starlette handles on its own, outside
    this function) -- never for an expected, sanitized, caught error this
    function assigns a status to."""
    known_writer_codes = {
        "conflicting_existing_identity",
        "provider_rollup_reconciliation_conflict",
        "database_identity_conflict",
        "database_persistence_error",
        "unknown_vehicle",
        "invalid_writer_request",
        "organization_context_mismatch",
        "request_window_invalid",
        "request_window_missing",
        "parser_version_not_certified",
        "source_endpoint_not_certified",
        "provider_unit_indicator_semantics_unresolved",
        "provider_unit_policy_mismatch",
        "provider_unit_context_invalid_type",
    }
    known_read_stage_codes = {
        "no_stored_vehicle",
        "provider_timeout",
        "rate_limited",
        "authorization_required",
        "permission_denied",
        "network_failure",
        "provider_contract_error",
        "invalid_pagination_request",
        "pagination_total_exceeds_selected_vehicles",
        "returned_item_count_mismatch",
        "duplicate_returned_rollup",
        "unexpected_returned_vehicle",
        "some_unrecognized_future_code",
    }
    for code in known_writer_codes | known_read_stage_codes:
        exc = MotiveVehicleUtilizationControlledWriteError(code, "synthetic")
        assert motive_api._controlled_write_http_status(exc) != 500, f"error code {code!r} must not map to HTTP 500"


# ---------------------------------------------------------------------------
# Section 23 -- second identical execution (idempotent replay).
# ---------------------------------------------------------------------------
def test_second_identical_execution_is_a_no_op(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    pages = [_page([_rollup_item("veh-1")], total=1)]

    first = _run_controlled_write(TestingSession, pages=pages)
    assert first["records_inserted"] == 1
    assert _row_count(TestingSession) == 1

    second = _run_controlled_write(TestingSession, pages=pages)
    assert second["records_inserted"] == 0
    assert second["records_unchanged"] == 1
    assert second["records_updated"] == 0
    assert _row_count(TestingSession) == 1


@pytest.mark.unit_readiness_gate
def test_repeated_real_executions_each_independently_fail_closed_with_zero_rows(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    pages = [_page([_rollup_item("veh-1", metric_units=False)], total=1)]

    for _attempt in range(2):
        with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
            _run_controlled_write(TestingSession, pages=pages)
        assert exc_info.value.code == "provider_unit_policy_mismatch"
        assert _row_count(TestingSession) == 0


# ---------------------------------------------------------------------------
# Section 24 -- changed replay now reconciles (2026-08-17 historical-rollup
# reconciliation gate). A genuine identity/context conflict (never a mere
# metric-value change) still fails closed.
# ---------------------------------------------------------------------------
def test_changed_replay_reconciles_the_approved_field(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    checkpoints_before, history_before = _checkpoint_and_history_counts(TestingSession)

    first_pages = [_page([_rollup_item("veh-1", idle_time=100)], total=1)]
    _run_controlled_write(TestingSession, pages=first_pages)
    assert _row_count(TestingSession) == 1

    second_pages = [_page([_rollup_item("veh-1", idle_time=999)], total=1)]
    result = _run_controlled_write(TestingSession, pages=second_pages)

    assert result["records_inserted"] == 0
    assert result["records_unchanged"] == 0
    assert result["records_updated"] == 1
    assert result["reconciled_fields_count"] == 1
    assert _row_count(TestingSession) == 1
    with TestingSession() as session:
        row = session.query(MotiveVehicleUtilizationRecord).one()
        assert row.idle_time == Decimal("999")
    checkpoints_after, history_after = _checkpoint_and_history_counts(TestingSession)
    assert checkpoints_after == checkpoints_before
    assert history_after == history_before


def test_conflicting_identity_context_still_fails_closed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A metric-value difference now reconciles (see above). A genuine
    identity/context conflict -- here, an existing row that predates the
    certified writer contract (incompatible unit context) -- still fails
    closed and is never silently reconciled."""
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    checkpoints_before, history_before = _checkpoint_and_history_counts(TestingSession)

    with TestingSession.begin() as session:
        vehicle = session.query(MotiveVehicleRecord).filter_by(provider_vehicle_id="veh-1").one()
        session.add(
            MotiveVehicleUtilizationRecord(
                organization_id="org-a",
                organization_slug="org-a",
                provider_vehicle_id="veh-1",
                motive_vehicle_id=vehicle.id,
                source_endpoint=writer_module.CERTIFIED_SOURCE_ENDPOINT,
                request_window_start=CONTROLLED_WRITE_WINDOW_START,
                request_window_end=CONTROLLED_WRITE_WINDOW_END,
                utilization_percent=Decimal("50"),
                idle_time=Decimal("100"),
                driving_time=Decimal("200"),
                idle_fuel=Decimal("1"),
                driving_fuel=Decimal("2"),
                metric_units=False,
                parser_version=writer_module.CERTIFIED_PARSER_VERSION,
            )
        )
    assert _row_count(TestingSession) == 1

    pages = [_page([_rollup_item("veh-1", idle_time=999)], total=1)]
    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=pages)

    assert exc_info.value.code == "conflicting_existing_identity"
    assert _row_count(TestingSession) == 1
    with TestingSession() as session:
        row = session.query(MotiveVehicleUtilizationRecord).one()
        assert row.idle_time == Decimal("100")
        assert row.metric_units is False
    checkpoints_after, history_after = _checkpoint_and_history_counts(TestingSession)
    assert checkpoints_after == checkpoints_before
    assert history_after == history_before


# ---------------------------------------------------------------------------
# Section 25 -- zero-result case.
# ---------------------------------------------------------------------------
def test_zero_result_is_a_successful_no_op(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    pages = [_page([], total=0)]

    result = _run_controlled_write(TestingSession, pages=pages)

    assert result["status"] == "success"
    assert result["pagination_total"] == 0
    assert result["records_inserted"] == 0
    assert result["records_unchanged"] == 0
    assert result["records_updated"] == 0
    assert result["missing_requested_vehicle_count"] == 3
    assert _row_count(TestingSession) == 0


# ---------------------------------------------------------------------------
# Section 26 -- bad pagination matrix.
# ---------------------------------------------------------------------------
def test_pagination_total_exceeds_selected_vehicle_count_fails_closed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    # total (4) exceeds selected_vehicle_count (3), even though only 1 item is returned.
    pages = [_page([_rollup_item("veh-1")], total=4)]

    calls: list[httpx.Request] = []
    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=pages, calls=calls)

    assert exc_info.value.code == "pagination_total_exceeds_selected_vehicles"
    assert len(calls) == 1
    assert _row_count(TestingSession) == 0


def test_pagination_total_not_equal_to_returned_count_fails_closed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    # Declares total=2 but only returns 1 item.
    pages = [_page([_rollup_item("veh-1")], total=2)]

    calls: list[httpx.Request] = []
    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=pages, calls=calls)

    assert exc_info.value.code == "returned_item_count_mismatch"
    assert len(calls) == 1
    assert _row_count(TestingSession) == 0


def test_page_no_mismatch_fails_closed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    pages = [_page([_rollup_item("veh-1")], page_no=2, total=1)]

    calls: list[httpx.Request] = []
    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=pages, calls=calls)

    assert exc_info.value.code == "pagination_page_no_mismatch"
    assert len(calls) == 1
    assert _row_count(TestingSession) == 0


def test_per_page_mismatch_fails_closed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    pages = [_page([_rollup_item("veh-1")], per_page=25, total=1)]

    calls: list[httpx.Request] = []
    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=pages, calls=calls)

    assert exc_info.value.code == "pagination_per_page_mismatch"
    assert len(calls) == 1
    assert _row_count(TestingSession) == 0


def test_missing_pagination_fails_closed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    pages = [{"vehicle_idle_rollups": [_rollup_item("veh-1")]}]

    calls: list[httpx.Request] = []
    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=pages, calls=calls)

    assert exc_info.value.code == "missing_pagination"
    assert len(calls) == 1
    assert _row_count(TestingSession) == 0


@pytest.mark.parametrize(
    "pagination_override",
    [
        {"per_page": 100, "page_no": 1, "total": True},
        {"per_page": 100, "page_no": True, "total": 1},
        {"per_page": True, "page_no": 1, "total": 1},
        {"per_page": 100, "page_no": 1, "total": "1"},
        {"per_page": "100", "page_no": 1, "total": 1},
    ],
)
def test_non_integer_or_boolean_pagination_fields_fail_closed(tmp_path, monkeypatch: pytest.MonkeyPatch, pagination_override: dict[str, Any]) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    pages = [_page([_rollup_item("veh-1")], pagination_override=pagination_override)]

    calls: list[httpx.Request] = []
    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=pages, calls=calls)

    assert exc_info.value.code.startswith("invalid_")
    assert len(calls) == 1
    assert _row_count(TestingSession) == 0


def test_duplicate_returned_rollup_fails_closed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    pages = [_page([_rollup_item("veh-1"), _rollup_item("veh-1")], total=2)]

    calls: list[httpx.Request] = []
    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=pages, calls=calls)

    assert exc_info.value.code == "duplicate_returned_rollup"
    assert len(calls) == 1
    assert _row_count(TestingSession) == 0


def test_unexpected_returned_vehicle_fails_closed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    pages = [_page([_rollup_item("veh-unexpected")], total=1)]

    calls: list[httpx.Request] = []
    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=pages, calls=calls)

    assert exc_info.value.code == "unexpected_returned_vehicle"
    assert len(calls) == 1
    assert _row_count(TestingSession) == 0


# ---------------------------------------------------------------------------
# Section 27 -- unit / parser failure.
#
# These fail closed at the WRITER's persistence-readiness gate (not a
# read-stage pre-check) -- provider schema parse success is distinct from
# durable persistence readiness. The controlled route always requests
# X-Metric-Units: true, so a returned True now agrees and is unit-ready
# (proven separately in test_route_succeeds_when_returned_unit_matches_the_
# canonical_request below); False and None each still fail closed, with
# their own distinct, provider-confirmed codes.
# ---------------------------------------------------------------------------
@pytest.mark.unit_readiness_gate
@pytest.mark.parametrize(
    ("metric_units", "expected_code"),
    [(False, "provider_unit_policy_mismatch"), (None, "provider_unit_indicator_semantics_unresolved")],
)
def test_every_disagreeing_or_missing_returned_unit_value_fails_closed_before_any_write(
    tmp_path, monkeypatch: pytest.MonkeyPatch, metric_units, expected_code
) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    pages = [_page([_rollup_item("veh-1", metric_units=metric_units)], total=1)]

    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=pages)

    assert exc_info.value.code == expected_code
    assert exc_info.value.returned_rollup_count == 1
    assert _row_count(TestingSession) == 0


@pytest.mark.unit_readiness_gate
def test_route_succeeds_when_returned_unit_matches_the_canonical_request(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A returned True agrees with the controlled route's canonical
    X-Metric-Units: true request and is durably persisted -- the real,
    non-bypassed unit-readiness gate, not the module-level test bypass."""
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    pages = [_page([_rollup_item("veh-1", metric_units=True)], total=1)]

    result = _run_controlled_write(TestingSession, pages=pages)

    assert result["status"] == "success"
    assert result["records_inserted"] == 1
    assert _row_count(TestingSession) == 1


def test_bad_parser_shape_fails_closed_before_writer_commit(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    # Missing the "vehicle_idle_rollup" wrapper key entirely.
    pages = [{"vehicle_idle_rollups": [{"not_the_certified_wrapper": {}}], "pagination": {"per_page": 100, "page_no": 1, "total": 1}}]

    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=pages)

    assert exc_info.value.code == "missing_wrapper"
    assert _row_count(TestingSession) == 0


def test_invalid_container_shape_fails_closed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    pages = [{"vehicle_idle_rollups": "not-a-list", "pagination": {"per_page": 100, "page_no": 1, "total": 1}}]

    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=pages)

    assert exc_info.value.code == "invalid_container"
    assert _row_count(TestingSession) == 0


# ---------------------------------------------------------------------------
# Section 28 -- provider failure.
# ---------------------------------------------------------------------------
def test_provider_timeout_fails_closed_with_no_retry(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    calls: list[httpx.Request] = []
    client = _raising_client(httpx.ReadTimeout("boom", request=None), calls)

    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, http_client=client, calls=calls)

    assert exc_info.value.code == "provider_timeout"
    assert exc_info.value.provider_calls_attempted == 1
    assert exc_info.value.provider_calls_completed == 0
    assert len(calls) == 1
    assert _row_count(TestingSession) == 0


def test_provider_network_failure_fails_closed_with_no_retry(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    calls: list[httpx.Request] = []
    client = _raising_client(httpx.ConnectError("boom", request=None), calls)

    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, http_client=client, calls=calls)

    assert exc_info.value.code == "network_failure"
    assert exc_info.value.provider_calls_attempted == 1
    assert exc_info.value.provider_calls_completed == 0
    assert len(calls) == 1
    assert _row_count(TestingSession) == 0


@pytest.mark.parametrize("status_code", [400, 429, 500, 502, 503])
def test_provider_non_success_response_fails_closed_with_no_retry(tmp_path, monkeypatch: pytest.MonkeyPatch, status_code: int) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    calls: list[httpx.Request] = []
    pages = [{"error": "provider rejected the request"}]

    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=pages, calls=calls, status_code=status_code)

    assert exc_info.value.provider_calls_attempted == 1
    assert exc_info.value.provider_calls_completed == 0
    assert len(calls) == 1
    assert _row_count(TestingSession) == 0
    checkpoints, history = _checkpoint_and_history_counts(TestingSession)
    assert checkpoints == 0
    assert history == 0


# ---------------------------------------------------------------------------
# Section 14 -- transaction failure after successful provider read.
# ---------------------------------------------------------------------------
def test_writer_transaction_failure_rolls_back_with_no_partial_writes(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    # veh-1 is selected but has no stored MotiveVehicleRecord in this org,
    # forcing the writer to fail with "unknown_vehicle" at the persistence step
    # even though the provider read itself is fully valid.
    with TestingSession.begin() as session:
        session.add(Organization(id="org-a", slug="org-a", display_name="org-a"))
        session.add(MotiveVehicleRecord(organization_id="org-a", organization_slug="org-a", provider_vehicle_id="veh-2"))
        session.add(MotiveVehicleRecord(organization_id="org-a", organization_slug="org-a", provider_vehicle_id="veh-3"))
    pages = [_page([_rollup_item("veh-1")], total=1)]

    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=pages, selected_provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))

    assert exc_info.value.code == "unknown_vehicle"
    assert exc_info.value.provider_calls_attempted == 1
    assert exc_info.value.provider_calls_completed == 1
    assert _row_count(TestingSession) == 0
    checkpoints, history = _checkpoint_and_history_counts(TestingSession)
    assert checkpoints == 0
    assert history == 0


# ---------------------------------------------------------------------------
# Section 29 -- tenant isolation.
# ---------------------------------------------------------------------------
def test_route_selects_only_authenticated_organization_vehicles(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONTROLLED_WRITE_ENABLED_ENV_VAR, "true")
    captured: dict[str, Any] = {}

    def fake_run(session, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "success", "selected_vehicle_count": len(kwargs["selected_provider_vehicle_ids"])}

    monkeypatch.setattr(motive_api, "run_controlled_vehicle_utilization_write", fake_run)
    TestingSession = _session_factory(tmp_path)
    with TestingSession.begin() as session:
        session.add(Organization(id="org-a", slug="org-a", display_name="Org A"))
        session.add(Organization(id="org-b", slug="org-b", display_name="Org B"))
        session.add(MotiveVehicleRecord(id=1, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-a"))
        session.add(MotiveVehicleRecord(id=2, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-b"))
        session.add(MotiveVehicleRecord(id=3, organization_id="org-b", organization_slug="org-b", provider_vehicle_id="provider-vehicle-cross-tenant"))

    with TestingSession() as session:
        result = motive_api.verify_motive_vehicle_utilization_write(
            body=motive_api.VehicleUtilizationControlledWriteRequest(confirm=True),
            principal=_principal("org-a"),
            session=session,
        )

    assert result["status"] == "success"
    assert captured["organization_id"] == "org-a"
    assert captured["organization_slug"] == "org-a"
    assert "provider-vehicle-cross-tenant" not in captured["selected_provider_vehicle_ids"]
    assert set(captured["selected_provider_vehicle_ids"]) == {"provider-vehicle-a", "provider-vehicle-b"}


def test_cross_tenant_vehicle_never_persists_for_requesting_org(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, organization_id="org-a", organization_slug="org-a", provider_vehicle_ids=())
    _seed(TestingSession, organization_id="org-b", organization_slug="org-b", provider_vehicle_ids=("shared-vehicle-id",))
    pages = [_page([_rollup_item("shared-vehicle-id")], total=1)]

    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(
            TestingSession,
            pages=pages,
            organization_id="org-a",
            organization_slug="org-a",
            selected_provider_vehicle_ids=("shared-vehicle-id",),
        )

    assert exc_info.value.code == "unknown_vehicle"
    assert "shared-vehicle-id" not in str(exc_info.value)
    with TestingSession() as session:
        assert session.query(MotiveVehicleUtilizationRecord).filter_by(organization_id="org-a").count() == 0


# ---------------------------------------------------------------------------
# Section 30 -- public output security.
# ---------------------------------------------------------------------------
def test_success_response_never_leaks_unsafe_values(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=(UNSAFE_PROVIDER_VEHICLE_ID, "veh-2", "veh-3"))
    pages = [
        _page(
            [_rollup_item(UNSAFE_PROVIDER_VEHICLE_ID, utilization=UNSAFE_UTILIZATION)],
            total=1,
        )
    ]

    result = _run_controlled_write(
        TestingSession,
        pages=pages,
        selected_provider_vehicle_ids=(UNSAFE_PROVIDER_VEHICLE_ID, "veh-2", "veh-3"),
    )

    rendered = repr(result)
    assert UNSAFE_PROVIDER_VEHICLE_ID not in rendered
    assert UNSAFE_VIN not in rendered
    assert UNSAFE_UNIT_NUMBER not in rendered
    assert UNSAFE_UTILIZATION not in rendered
    assert FAKE_API_KEY not in rendered
    expected_keys = {
        "status",
        "resource",
        "validation_mode",
        "request_window_start",
        "request_window_end",
        "selected_vehicle_count",
        "provider_calls_attempted",
        "provider_calls_completed",
        "pagination_total",
        "returned_rollup_count",
        "missing_requested_vehicle_count",
        "records_inserted",
        "records_unchanged",
        "records_updated",
        "reconciled_fields_count",
        "committed",
        "checkpoint_advanced",
        "sync_history_written",
        "scheduled_ingestion_enabled",
        "secrets_exposed",
    }
    assert set(result.keys()) == expected_keys


def test_error_response_never_leaks_unsafe_values(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=(UNSAFE_PROVIDER_VEHICLE_ID, "veh-2", "veh-3"))

    # A genuine identity/context conflict (incompatible legacy unit context)
    # -- a mere metric-value difference now reconciles rather than erroring
    # (see test_changed_replay_reconciles_the_approved_field above), so this
    # sanitized-error proof needs a real conflict to trigger a writer
    # failure at all.
    with TestingSession.begin() as session:
        vehicle = session.query(MotiveVehicleRecord).filter_by(provider_vehicle_id=UNSAFE_PROVIDER_VEHICLE_ID).one()
        session.add(
            MotiveVehicleUtilizationRecord(
                organization_id="org-a",
                organization_slug="org-a",
                provider_vehicle_id=UNSAFE_PROVIDER_VEHICLE_ID,
                motive_vehicle_id=vehicle.id,
                source_endpoint=writer_module.CERTIFIED_SOURCE_ENDPOINT,
                request_window_start=CONTROLLED_WRITE_WINDOW_START,
                request_window_end=CONTROLLED_WRITE_WINDOW_END,
                utilization_percent=Decimal("50"),
                idle_time=Decimal("1"),
                driving_time=Decimal("200"),
                idle_fuel=Decimal("1"),
                driving_fuel=Decimal("2"),
                metric_units=False,
                parser_version=writer_module.CERTIFIED_PARSER_VERSION,
            )
        )

    second_pages = [_page([_rollup_item(UNSAFE_PROVIDER_VEHICLE_ID, idle_time=999, utilization=UNSAFE_UTILIZATION)], total=1)]
    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=second_pages, selected_provider_vehicle_ids=(UNSAFE_PROVIDER_VEHICLE_ID, "veh-2", "veh-3"))

    assert exc_info.value.code == "conflicting_existing_identity"
    rendered = str(exc_info.value)
    assert UNSAFE_PROVIDER_VEHICLE_ID not in rendered
    assert UNSAFE_UTILIZATION not in rendered
    assert FAKE_API_KEY not in rendered


def test_log_records_never_leak_unsafe_values(tmp_path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=(UNSAFE_PROVIDER_VEHICLE_ID, "veh-2", "veh-3"))
    pages = [_page([_rollup_item(UNSAFE_PROVIDER_VEHICLE_ID, utilization=UNSAFE_UTILIZATION)], total=1)]

    with caplog.at_level(logging.INFO):
        _run_controlled_write(
            TestingSession,
            pages=pages,
            selected_provider_vehicle_ids=(UNSAFE_PROVIDER_VEHICLE_ID, "veh-2", "veh-3"),
        )

    # Only inspect Polaris application loggers. Third-party libraries (e.g.
    # httpx's own request-logging middleware, exercised here only because the
    # test drives a real httpx.Client against a MockTransport) are out of
    # scope for this application-level sanitization contract.
    app_records = [record for record in caplog.records if record.name.startswith("app.")]
    assert app_records, "expected at least one sanitized application log record"
    for record in app_records:
        rendered = record.getMessage() + " ".join(str(v) for v in vars(record).values())
        assert UNSAFE_PROVIDER_VEHICLE_ID not in rendered
        assert UNSAFE_VIN not in rendered
        assert UNSAFE_UNIT_NUMBER not in rendered
        assert UNSAFE_UTILIZATION not in rendered
        assert FAKE_API_KEY not in rendered
