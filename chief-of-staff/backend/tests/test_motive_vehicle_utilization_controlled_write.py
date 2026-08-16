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
from app.organizations.models import Organization
from app.security.models import AuthenticatedPrincipal, Permission

register_models()

UNSAFE_PROVIDER_VEHICLE_ID = "provider-vehicle-should-not-leak-4471"
UNSAFE_VIN = "VINSHOULDNOTLEAK12"
UNSAFE_UNIT_NUMBER = "unit-should-not-leak-778"
UNSAFE_UTILIZATION = "13.3700"
FAKE_API_KEY = "fake-motive-secret"


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
# Section 22 -- success insert.
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


# ---------------------------------------------------------------------------
# Section 24 -- conflicting replay.
# ---------------------------------------------------------------------------
def test_conflicting_replay_fails_closed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    checkpoints_before, history_before = _checkpoint_and_history_counts(TestingSession)

    first_pages = [_page([_rollup_item("veh-1", idle_time=100)], total=1)]
    _run_controlled_write(TestingSession, pages=first_pages)
    assert _row_count(TestingSession) == 1

    second_pages = [_page([_rollup_item("veh-1", idle_time=999)], total=1)]
    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=second_pages)

    assert exc_info.value.code == "conflicting_existing_identity"
    assert _row_count(TestingSession) == 1
    with TestingSession() as session:
        row = session.query(MotiveVehicleUtilizationRecord).one()
        assert row.idle_time == Decimal("100")
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
# ---------------------------------------------------------------------------
def test_metric_units_false_fails_closed_before_writer_commit(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    pages = [_page([_rollup_item("veh-1", metric_units=False)], total=1)]

    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=pages)

    assert exc_info.value.code == "provider_unit_policy_mismatch"
    assert _row_count(TestingSession) == 0


def test_metric_units_missing_fails_closed_before_writer_commit(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    pages = [_page([_rollup_item("veh-1", metric_units=None)], total=1)]

    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=pages)

    assert exc_info.value.code == "provider_unit_context_missing"
    assert _row_count(TestingSession) == 0


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
    # Conflicting metric value on replay triggers a sanitized writer failure.
    first_pages = [_page([_rollup_item(UNSAFE_PROVIDER_VEHICLE_ID, idle_time=1)], total=1)]
    _run_controlled_write(TestingSession, pages=first_pages, selected_provider_vehicle_ids=(UNSAFE_PROVIDER_VEHICLE_ID, "veh-2", "veh-3"))

    second_pages = [_page([_rollup_item(UNSAFE_PROVIDER_VEHICLE_ID, idle_time=999, utilization=UNSAFE_UTILIZATION)], total=1)]
    with pytest.raises(MotiveVehicleUtilizationControlledWriteError) as exc_info:
        _run_controlled_write(TestingSession, pages=second_pages, selected_provider_vehicle_ids=(UNSAFE_PROVIDER_VEHICLE_ID, "veh-2", "veh-3"))

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
