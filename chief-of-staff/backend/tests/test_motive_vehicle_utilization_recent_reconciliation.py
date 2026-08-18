"""Tests for the bounded, manually-invoked Motive vehicle-utilization
RECENT-WINDOW RECONCILIATION runner
(``app/motive/vehicle_utilization_recent_reconciliation.py``).

This gate proves the orchestration primitive described in
``docs/engineering/MOTIVE_UTILIZATION_RECENT_WINDOW_RECONCILIATION_DESIGN.md``:
bounded day-window generation, tenant-safe vehicle selection, deterministic
batching, a pre-flight call-budget guard, reuse (never duplication) of the
general certified pagination reader and the merged writer transaction,
per-unit failure isolation with no automatic retry, and a fully sanitized
result contract that never advances a checkpoint or writes sync history.

No live Motive provider call is made anywhere in this module. All provider
interaction is mocked via ``httpx.MockTransport``.
"""

from __future__ import annotations

import ast
import dataclasses
from datetime import date, timedelta
from decimal import Decimal
import inspect
import logging
import math
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.database import Base
from app.database.models import register_models
from app.models.motive import (
    MotiveSyncCheckpoint,
    MotiveSyncHistory,
    MotiveVehicleRecord,
    MotiveVehicleUtilizationRecord,
)
from app.motive import vehicle_utilization_recent_reconciliation as runner_module
from app.motive.vehicle_utilization_recent_reconciliation import (
    DEFAULT_RECENT_RECONCILIATION_DAYS,
    MAX_RECENT_RECONCILIATION_DAYS,
    MAX_VEHICLES_PER_BATCH,
    RECENT_RECONCILIATION_ENABLED_ENV_VAR,
    RUNNER_MAX_AUTHORIZED_PROVIDER_CALLS,
    RUNNER_MAX_PAGES_PER_UNIT,
    MotiveVehicleUtilizationRecentReconciliationError,
    _batch_provider_vehicle_ids,
    _generate_day_windows,
    _max_authorized_provider_calls,
    _validate_horizon_days,
    recent_reconciliation_enabled,
    run_recent_vehicle_utilization_reconciliation,
)
from app.organizations.models import Organization

register_models()

FAKE_API_KEY = "fake-motive-secret"
UNSAFE_VIN = "VINSHOULDNOTLEAK12"
UNSAFE_UNIT_NUMBER = "unit-should-not-leak-778"
UNSAFE_DRIVER_EMAIL = "driver-should-not-leak@example.com"
FIXED_END_DATE = date(2026, 8, 17)  # frozen "yesterday" for deterministic day-window tests


@pytest.fixture(autouse=True)
def _fixed_window_and_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(runner_module, "_completed_recent_reconciliation_window", lambda: FIXED_END_DATE)
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    yield


# ---------------------------------------------------------------------------
# Shared fixtures / helpers.
# ---------------------------------------------------------------------------
def _session_factory(tmp_path, name: str = "recent-reconciliation"):
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
    provider_vehicle_ids: tuple[str, ...] = ("veh-1",),
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


def _run(
    TestingSession,
    *,
    pages: list[dict[str, Any]] | None = None,
    calls: list[httpx.Request] | None = None,
    http_client: httpx.Client | None = None,
    organization_id: str = "org-a",
    organization_slug: str = "org-a",
    horizon_days: int = 1,
    status_code: int = 200,
):
    observed_calls = calls if calls is not None else []
    client = http_client or _client_for_pages(pages or [], observed_calls, status_code=status_code)
    with TestingSession() as session:
        return run_recent_vehicle_utilization_reconciliation(
            session,
            organization_id=organization_id,
            organization_slug=organization_slug,
            horizon_days=horizon_days,
            http_client=client,
        )


# ---------------------------------------------------------------------------
# Feature gate -- default off, genuinely separate from the controlled-write
# flag, fails closed before any provider call or vehicle selection.
# ---------------------------------------------------------------------------
def test_flag_defaults_disabled_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, raising=False)
    assert recent_reconciliation_enabled() is False


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "", "garbage", "TrUe_typo"])
def test_flag_disabled_for_falsy_or_unrecognized_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, value)
    assert recent_reconciliation_enabled() is False


@pytest.mark.parametrize("value", ["true", "1", "yes", "on", "TRUE", "On"])
def test_flag_enabled_only_for_explicit_truthy_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, value)
    assert recent_reconciliation_enabled() is True


def test_flag_is_a_genuinely_separate_env_var_from_controlled_write() -> None:
    from app.motive.vehicle_utilization_controlled_write import CONTROLLED_WRITE_ENABLED_ENV_VAR

    assert RECENT_RECONCILIATION_ENABLED_ENV_VAR != CONTROLLED_WRITE_ENABLED_ENV_VAR
    assert RECENT_RECONCILIATION_ENABLED_ENV_VAR == "MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_ENABLED"


def test_runner_fails_closed_before_any_vehicle_selection_or_provider_call_when_disabled(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, raising=False)
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession)

    def fail_if_called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("must not select vehicles while the flag is disabled")

    monkeypatch.setattr(runner_module, "_select_tenant_vehicles", fail_if_called)
    calls: list[httpx.Request] = []

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationRecentReconciliationError) as exc_info:
            run_recent_vehicle_utilization_reconciliation(
                session, organization_id="org-a", organization_slug="org-a", http_client=_client_for_pages([], calls)
            )
    assert exc_info.value.code == "recent_reconciliation_disabled"
    assert len(calls) == 0
    assert _row_count(TestingSession) == 0


# ---------------------------------------------------------------------------
# Horizon (default 7, hard max 14, strict positive validation).
# ---------------------------------------------------------------------------
def test_default_horizon_is_seven_days() -> None:
    assert DEFAULT_RECENT_RECONCILIATION_DAYS == 7


def test_max_horizon_is_fourteen_days() -> None:
    assert MAX_RECENT_RECONCILIATION_DAYS == 14


@pytest.mark.parametrize("horizon_days", [1, DEFAULT_RECENT_RECONCILIATION_DAYS, MAX_RECENT_RECONCILIATION_DAYS])
def test_valid_horizon_days_accepted(horizon_days: int) -> None:
    _validate_horizon_days(horizon_days)  # must not raise


@pytest.mark.parametrize(
    ("horizon_days", "expected_code"),
    [
        (0, "horizon_days_not_positive"),
        (-1, "horizon_days_not_positive"),
        (MAX_RECENT_RECONCILIATION_DAYS + 1, "horizon_days_exceeds_maximum"),
        (100, "horizon_days_exceeds_maximum"),
        (True, "invalid_horizon_days"),
        ("7", "invalid_horizon_days"),
        (7.0, "invalid_horizon_days"),
    ],
)
def test_invalid_horizon_days_rejected(horizon_days: Any, expected_code: str) -> None:
    with pytest.raises(MotiveVehicleUtilizationRecentReconciliationError) as exc_info:
        _validate_horizon_days(horizon_days)
    assert exc_info.value.code == expected_code


def test_runner_rejects_invalid_horizon_before_any_vehicle_selection(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession)

    def fail_if_called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("must not select vehicles for an invalid horizon")

    monkeypatch.setattr(runner_module, "_select_tenant_vehicles", fail_if_called)

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationRecentReconciliationError) as exc_info:
            run_recent_vehicle_utilization_reconciliation(
                session, organization_id="org-a", organization_slug="org-a", horizon_days=0
            )
    assert exc_info.value.code == "horizon_days_not_positive"


# ---------------------------------------------------------------------------
# Day-window generation: exact count, no "today", start==end, consecutive,
# oldest -> newest, deterministic.
# ---------------------------------------------------------------------------
def test_day_windows_default_horizon_count_and_shape() -> None:
    windows = _generate_day_windows(7, end_date=FIXED_END_DATE)
    assert len(windows) == 7
    for start, end in windows:
        assert start == end


def test_day_windows_never_include_today() -> None:
    windows = _generate_day_windows(1, end_date=FIXED_END_DATE)
    assert windows == [(FIXED_END_DATE, FIXED_END_DATE)]
    latest_window_end = windows[-1][1]
    assert latest_window_end == FIXED_END_DATE  # never later than the completed "yesterday" boundary


def test_day_windows_are_consecutive_calendar_days_oldest_to_newest() -> None:
    windows = _generate_day_windows(7, end_date=FIXED_END_DATE)
    starts = [start for start, _end in windows]
    assert starts == sorted(starts)
    for earlier, later in zip(starts, starts[1:]):
        assert later - earlier == timedelta(days=1)
    assert windows[0] == (FIXED_END_DATE - timedelta(days=6), FIXED_END_DATE - timedelta(days=6))
    assert windows[-1] == (FIXED_END_DATE, FIXED_END_DATE)


def test_day_windows_deterministic_ordering_repeated_calls() -> None:
    assert _generate_day_windows(7, end_date=FIXED_END_DATE) == _generate_day_windows(7, end_date=FIXED_END_DATE)


def test_day_windows_single_day_horizon() -> None:
    assert _generate_day_windows(1, end_date=FIXED_END_DATE) == [(FIXED_END_DATE, FIXED_END_DATE)]


def test_day_windows_max_horizon_count() -> None:
    windows = _generate_day_windows(MAX_RECENT_RECONCILIATION_DAYS, end_date=FIXED_END_DATE)
    assert len(windows) == MAX_RECENT_RECONCILIATION_DAYS


# ---------------------------------------------------------------------------
# Tenant-safe vehicle selection.
# ---------------------------------------------------------------------------
def test_vehicle_selection_scoped_to_organization_and_ordered_by_id(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, organization_id="org-a", organization_slug="org-a", provider_vehicle_ids=("veh-3", "veh-1", "veh-2"))
    _seed(TestingSession, organization_id="org-b", organization_slug="org-b", provider_vehicle_ids=("veh-x",))
    with TestingSession() as session:
        vehicles = runner_module._select_tenant_vehicles(session, "org-a")
    assert [vehicle.provider_vehicle_id for vehicle in vehicles] == ["veh-3", "veh-1", "veh-2"]
    assert all(vehicle.organization_id == "org-a" for vehicle in vehicles)


def test_vehicle_selection_zero_eligible_vehicles_is_no_op(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=())
    calls: list[httpx.Request] = []

    result = _run(TestingSession, calls=calls)

    assert result.status == "no_op"
    assert result.selected_vehicle_count == 0
    assert result.provider_calls_attempted == 0
    assert result.provider_calls_completed == 0
    assert len(calls) == 0
    assert _row_count(TestingSession) == 0
    assert result.checkpoint_advanced is False
    assert result.sync_history_written is False
    assert result.scheduled_ingestion_enabled is False


# ---------------------------------------------------------------------------
# Vehicle batching.
# ---------------------------------------------------------------------------
def test_batch_size_constant_is_100() -> None:
    assert MAX_VEHICLES_PER_BATCH == 100


def test_batch_cap_is_not_the_controlled_write_three_vehicle_cap() -> None:
    from app.connectors.motive_vehicle_utilization_contract import MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES

    assert MAX_VEHICLES_PER_BATCH != MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES


@pytest.mark.parametrize("vehicle_count", [0, 1, 99, 100, 101, 250])
def test_batching_covers_every_vehicle_exactly_once_no_overlap_no_omission(vehicle_count: int) -> None:
    ids = [f"veh-{i}" for i in range(vehicle_count)]
    batches = _batch_provider_vehicle_ids(ids, MAX_VEHICLES_PER_BATCH)

    flattened = [vehicle_id for batch in batches for vehicle_id in batch]
    assert flattened == ids
    assert len(set(flattened)) == len(flattened)

    for batch in batches:
        assert 0 < len(batch) <= MAX_VEHICLES_PER_BATCH

    if vehicle_count == 0:
        assert batches == []
    else:
        assert len(batches) == math.ceil(vehicle_count / MAX_VEHICLES_PER_BATCH)


# ---------------------------------------------------------------------------
# Provider read: reuse the general certified reader unmodified, ACCOUNT_DEFAULT,
# no X-Metric-Units, no X-Time-Zone invention, page size 100.
# ---------------------------------------------------------------------------
def test_provider_read_uses_account_default_no_forced_headers_page_size_100(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    calls: list[httpx.Request] = []
    pages = [_page([_rollup_item("veh-1")], total=1)]

    _run(TestingSession, pages=pages, calls=calls)

    assert len(calls) == 1
    request = calls[0]
    assert request.url.path == "/v1/vehicle_utilization"
    assert request.url.params["per_page"] == "100"
    assert request.url.params["start_date"] == FIXED_END_DATE.isoformat()
    assert request.url.params["end_date"] == FIXED_END_DATE.isoformat()
    header_keys_lower = {key.lower() for key in request.headers.keys()}
    assert "x-metric-units" not in header_keys_lower
    assert "x-time-zone" not in header_keys_lower
    assert "x-user-id" not in header_keys_lower


def test_runner_explicitly_selects_account_default_unit_mode() -> None:
    source = inspect.getsource(run_recent_vehicle_utilization_reconciliation)
    assert source.count("MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT") == 2


def test_runner_reuses_general_reader_and_writer_without_duplicating_their_logic() -> None:
    source = inspect.getsource(runner_module)
    assert "read_vehicle_utilization_pages(" in source
    assert "write_vehicle_utilization_transaction(" in source
    assert "def parse_pagination_metadata" not in source
    assert "MUTABLE_ON_PROVIDER_RECONCILIATION" not in source


# ---------------------------------------------------------------------------
# Write reuse / transaction boundary: exactly one writer call per unit.
# ---------------------------------------------------------------------------
def test_writer_called_exactly_once_per_unit(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    call_count = {"n": 0}
    original = runner_module.write_vehicle_utilization_transaction

    def counting_writer(*args: Any, **kwargs: Any) -> Any:
        call_count["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(runner_module, "write_vehicle_utilization_transaction", counting_writer)
    pages = [_page([_rollup_item("veh-1", idle_time=100)], total=1)]

    result = _run(TestingSession, pages=pages)

    assert call_count["n"] == 1
    assert result.records_inserted == 1


# ---------------------------------------------------------------------------
# Call-budget safety (D x B x P, runner-owned P and safety cap).
# ---------------------------------------------------------------------------
def test_runner_max_pages_per_unit_is_one() -> None:
    assert RUNNER_MAX_PAGES_PER_UNIT == 1


def test_call_budget_formula_is_d_times_b_times_p() -> None:
    assert _max_authorized_provider_calls(7, 1) == 7 * 1 * RUNNER_MAX_PAGES_PER_UNIT
    assert _max_authorized_provider_calls(14, 3) == 14 * 3 * RUNNER_MAX_PAGES_PER_UNIT


def test_call_budget_worked_example_matches_design_doc(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Design doc Section 12: D=7, B=1, P=1 -> 7 provider calls for one
    complete bounded run at current (materially smaller than 100 vehicles)
    fleet size."""
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    pages = [_page([_rollup_item("veh-1")], total=1) for _ in range(7)]
    calls: list[httpx.Request] = []

    result = _run(TestingSession, pages=pages, calls=calls, horizon_days=7)

    assert len(calls) == 7
    assert result.provider_calls_attempted == 7
    assert result.provider_calls_completed == 7
    assert result.status == "success"


def test_call_budget_exceeded_fails_closed_before_any_provider_call(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    # 1,501 synthetic vehicles -> 16 batches; 14 (max horizon) x 16 x 1 = 224
    # > RUNNER_MAX_AUTHORIZED_PROVIDER_CALLS (200). Synthetic, never-flushed
    # records avoid seeding 1,500+ real database rows.
    synthetic_vehicles = [
        MotiveVehicleRecord(organization_id="org-a", organization_slug="org-a", provider_vehicle_id=f"veh-{i}")
        for i in range(15 * MAX_VEHICLES_PER_BATCH + 1)
    ]
    monkeypatch.setattr(runner_module, "_select_tenant_vehicles", lambda session, organization_id: synthetic_vehicles)
    calls: list[httpx.Request] = []

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationRecentReconciliationError) as exc_info:
            run_recent_vehicle_utilization_reconciliation(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                horizon_days=MAX_RECENT_RECONCILIATION_DAYS,
                http_client=_client_for_pages([], calls),
            )

    assert exc_info.value.code == "call_budget_exceeded"
    assert len(calls) == 0
    assert _row_count(TestingSession) == 0


def test_call_budget_within_cap_at_max_horizon_and_realistic_fleet_growth(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """250-vehicle fleet (the design doc's illustrative growth example) at
    the max horizon stays well inside the runner safety cap."""
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    synthetic_vehicles = [
        MotiveVehicleRecord(organization_id="org-a", organization_slug="org-a", provider_vehicle_id=f"veh-{i}")
        for i in range(250)
    ]
    monkeypatch.setattr(runner_module, "_select_tenant_vehicles", lambda session, organization_id: synthetic_vehicles)
    assert _max_authorized_provider_calls(MAX_RECENT_RECONCILIATION_DAYS, math.ceil(250 / MAX_VEHICLES_PER_BATCH)) <= RUNNER_MAX_AUTHORIZED_PROVIDER_CALLS


# ---------------------------------------------------------------------------
# Idempotency / replay (Section 17 A-F).
# ---------------------------------------------------------------------------
def test_idempotency_a_first_run_inserts(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    pages = [_page([_rollup_item("veh-1")], total=1)]

    result = _run(TestingSession, pages=pages)

    assert result.status == "success"
    assert result.records_inserted == 1
    assert _row_count(TestingSession) == 1


def test_idempotency_b_exact_replay_is_a_no_op_no_duplicate_no_mutable_field_touch(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    pages = [_page([_rollup_item("veh-1")], total=1)]
    _run(TestingSession, pages=pages)

    second = _run(TestingSession, pages=pages)

    assert second.records_inserted == 0
    assert second.records_unchanged == 1
    assert second.records_updated == 0
    assert _row_count(TestingSession) == 1


def test_idempotency_c_later_provider_correction_updates_same_durable_row(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    _run(TestingSession, pages=[_page([_rollup_item("veh-1", idle_time=100)], total=1)])

    result = _run(TestingSession, pages=[_page([_rollup_item("veh-1", idle_time=999)], total=1)])

    assert result.records_inserted == 0
    assert result.records_unchanged == 0
    assert result.records_updated == 1
    assert result.reconciled_fields_count == 1
    assert _row_count(TestingSession) == 1
    with TestingSession() as session:
        row = session.query(MotiveVehicleUtilizationRecord).one()
        assert row.idle_time == Decimal("999")


def test_idempotency_d_omitted_requested_vehicle_creates_no_row_and_leaves_existing_untouched(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2"))
    # veh-2 is selected but the provider omits it from the response.
    pages = [_page([_rollup_item("veh-1")], total=1)]

    result = _run(TestingSession, pages=pages)

    assert result.missing_requested_vehicle_count == 1
    assert _row_count(TestingSession) == 1
    with TestingSession() as session:
        row = session.query(MotiveVehicleUtilizationRecord).one()
        assert row.provider_vehicle_id == "veh-1"


def test_idempotency_e_immutable_context_conflict_rolls_back_only_that_unit_later_independent_unit_still_runs(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    # Establish an existing row for the single (newer) day with metric_units=True.
    _run(TestingSession, pages=[_page([_rollup_item("veh-1", metric_units=True)], total=1)])
    assert _row_count(TestingSession) == 1

    # A fresh 2-day horizon: oldest day is a brand-new insert; the newer day
    # (matching the existing row's identity) now returns a conflicting
    # metric_units and must fail closed without touching the existing row.
    pages = [
        _page([_rollup_item("veh-1", metric_units=True)], total=1),  # older day: fresh insert
        _page([_rollup_item("veh-1", metric_units=False)], total=1),  # newer day: conflict
    ]

    result = _run(TestingSession, pages=pages, horizon_days=2)

    assert result.windows_attempted == 2
    assert result.windows_completed == 1
    assert result.windows_failed == 1
    assert result.vehicle_batches_completed == 1
    assert result.vehicle_batches_failed == 1
    assert result.records_inserted == 1
    assert len(result.failed_units) == 1
    assert result.failed_units[0].error_code == "conflicting_existing_identity"
    assert result.status == "partial_success"
    assert _row_count(TestingSession) == 2
    with TestingSession() as session:
        original_row = session.query(MotiveVehicleUtilizationRecord).filter_by(request_window_start=FIXED_END_DATE).one()
        assert original_row.metric_units is True  # untouched, never flipped


def test_idempotency_f_one_failed_unit_earlier_committed_unit_remains_no_retry(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    calls: list[httpx.Request] = []
    pages = [
        _page([_rollup_item("veh-1")], total=2),  # older day: total mismatch -> fails
        _page([_rollup_item("veh-1")], total=1),  # newer day: succeeds
    ]

    result = _run(TestingSession, pages=pages, calls=calls, horizon_days=2)

    assert len(calls) == 2  # exactly one call per unit -- no retry on the failed unit
    assert result.windows_attempted == 2
    assert result.windows_completed == 1
    assert result.windows_failed == 1
    assert result.vehicle_batches_attempted == 2
    assert result.vehicle_batches_completed == 1
    assert result.vehicle_batches_failed == 1
    assert result.status == "partial_success"
    assert result.records_inserted == 1
    assert _row_count(TestingSession) == 1  # only the successful unit committed


# ---------------------------------------------------------------------------
# Pagination / provider failure propagation (already-certified reader
# behavior, exercised through the runner's orchestration).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("build_pages", "expected_code"),
    [
        (lambda: [_page([_rollup_item("veh-1")], total=2)], "cumulative_rollup_count_below_total"),
        (lambda: [_page([_rollup_item("veh-1"), _rollup_item("veh-1")], total=2)], "duplicate_vehicle_observed"),
        (lambda: [_page([_rollup_item("veh-unexpected")], total=1)], "unexpected_vehicle_observed"),
        (lambda: [_page([], total=1)], "premature_empty_page"),
    ],
)
def test_pagination_contract_failures_recorded_as_sanitized_failed_unit(
    tmp_path, monkeypatch: pytest.MonkeyPatch, build_pages, expected_code: str
) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    calls: list[httpx.Request] = []

    result = _run(TestingSession, pages=build_pages(), calls=calls)

    assert len(calls) == 1
    assert result.status == "failed"
    assert result.vehicle_batches_failed == 1
    assert len(result.failed_units) == 1
    assert result.failed_units[0].error_code == expected_code
    assert result.failed_units[0].batch_ordinal == 1
    assert result.failed_units[0].window_start == FIXED_END_DATE.isoformat()
    assert _row_count(TestingSession) == 0


@pytest.mark.parametrize(("status_code", "expected_code"), [(500, "provider_unavailable"), (429, "rate_limited"), (401, "authorization_required")])
def test_provider_http_error_recorded_as_sanitized_failed_unit(
    tmp_path, monkeypatch: pytest.MonkeyPatch, status_code: int, expected_code: str
) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    calls: list[httpx.Request] = []

    result = _run(TestingSession, pages=[{"error": "boom"}], calls=calls, status_code=status_code)

    assert len(calls) == 1
    assert result.status == "failed"
    assert result.failed_units[0].error_code == expected_code
    assert _row_count(TestingSession) == 0


@pytest.mark.parametrize(
    ("metric_units", "expected_code"),
    [
        (None, "provider_unit_indicator_semantics_unresolved"),
        ("not-a-boolean", "provider_unit_indicator_semantics_unresolved"),
    ],
)
def test_missing_or_malformed_metric_units_fails_closed_before_any_write(
    tmp_path, monkeypatch: pytest.MonkeyPatch, metric_units: Any, expected_code: str
) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    pages = [_page([_rollup_item("veh-1", metric_units=metric_units)], total=1)]

    result = _run(TestingSession, pages=pages)

    assert result.status == "failed"
    assert result.failed_units[0].error_code == expected_code
    assert _row_count(TestingSession) == 0


def test_runner_returns_true_metric_units_readiness_under_account_default(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ACCOUNT_DEFAULT never forces a unit system, so both a returned True and
    a returned False are ready for durable persistence -- proven separately
    for False by test_idempotency_e above (an inserted row with
    metric_units=True) and here for the symmetric True case."""
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    pages = [_page([_rollup_item("veh-1", metric_units=False)], total=1)]

    result = _run(TestingSession, pages=pages)

    assert result.status == "success"
    assert result.records_inserted == 1
    with TestingSession() as session:
        row = session.query(MotiveVehicleUtilizationRecord).one()
        assert row.metric_units is False


# ---------------------------------------------------------------------------
# Unexpected exceptions: never silently swallowed; propagate and abort the
# whole run, but do not roll back already-committed earlier units.
# ---------------------------------------------------------------------------
def test_unexpected_exception_propagates_and_is_not_swallowed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    def boom(**_kwargs: Any) -> Any:
        raise RuntimeError("unexpected programming bug, not a known safe operational failure")

    monkeypatch.setattr(runner_module, "read_vehicle_utilization_pages", boom)

    with TestingSession() as session:
        with pytest.raises(RuntimeError, match="unexpected programming bug"):
            run_recent_vehicle_utilization_reconciliation(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                horizon_days=1,
                http_client=_client_for_pages([], []),
            )
    assert _row_count(TestingSession) == 0


def test_unexpected_exception_on_later_window_leaves_earlier_committed_rows_intact(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    real_read = runner_module.read_vehicle_utilization_pages
    call_state = {"n": 0}
    calls: list[httpx.Request] = []
    client = _client_for_pages([_page([_rollup_item("veh-1")], total=1)], calls)

    def flaky_read(**kwargs: Any) -> Any:
        call_state["n"] += 1
        if call_state["n"] == 2:
            raise RuntimeError("boom on the second window")
        return real_read(**kwargs)

    monkeypatch.setattr(runner_module, "read_vehicle_utilization_pages", flaky_read)

    with TestingSession() as session:
        with pytest.raises(RuntimeError, match="boom on the second window"):
            run_recent_vehicle_utilization_reconciliation(
                session, organization_id="org-a", organization_slug="org-a", horizon_days=2, http_client=client
            )

    assert _row_count(TestingSession) == 1  # first window's commit survived the later abort


def test_no_blanket_except_exception_continue_in_module_source() -> None:
    """AST-based (not string-based) so this only inspects real ``except``
    handlers, never the module's own docstring prose describing this
    constraint."""
    tree = ast.parse(inspect.getsource(runner_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            assert node.type is not None, "bare 'except:' is not allowed"
            assert not (isinstance(node.type, ast.Name) and node.type.id == "Exception"), "blanket 'except Exception:' is not allowed"


# ---------------------------------------------------------------------------
# No checkpoint / no sync history, ever, on any outcome.
# ---------------------------------------------------------------------------
def test_checkpoint_and_sync_history_are_never_touched(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    before = _checkpoint_and_history_counts(TestingSession)
    pages = [_page([_rollup_item("veh-1")], total=1)]

    result = _run(TestingSession, pages=pages)

    after = _checkpoint_and_history_counts(TestingSession)
    assert before == after == (0, 0)
    assert result.checkpoint_advanced is False
    assert result.sync_history_written is False
    assert result.scheduled_ingestion_enabled is False


def test_no_checkpoint_or_sync_history_reference_in_module_source() -> None:
    """Checks the module's actual bound names (i.e. real imports/usage), not
    its docstring prose, which legitimately names these classes to describe
    what this module deliberately never touches."""
    assert not hasattr(runner_module, "MotiveSyncCheckpoint")
    assert not hasattr(runner_module, "MotiveSyncHistory")
    tree = ast.parse(inspect.getsource(runner_module))
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "MotiveSyncCheckpoint" not in imported_names
    assert "MotiveSyncHistory" not in imported_names


# ---------------------------------------------------------------------------
# Result contract shape + status semantics.
# ---------------------------------------------------------------------------
def test_result_contains_all_required_sanitized_fields(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    pages = [_page([_rollup_item("veh-1")], total=1)]

    result = _run(TestingSession, pages=pages)

    required_fields = {
        "status",
        "resource",
        "run_mode",
        "horizon_days",
        "windows_attempted",
        "windows_completed",
        "windows_failed",
        "selected_vehicle_count",
        "vehicle_batches_attempted",
        "vehicle_batches_completed",
        "vehicle_batches_failed",
        "provider_calls_attempted",
        "provider_calls_completed",
        "rollups_returned",
        "missing_requested_vehicle_count",
        "records_inserted",
        "records_unchanged",
        "records_updated",
        "reconciled_fields_count",
        "checkpoint_advanced",
        "sync_history_written",
        "scheduled_ingestion_enabled",
        "secrets_exposed",
    }
    field_names = {field.name for field in dataclasses.fields(result)}
    assert required_fields <= field_names
    assert result.checkpoint_advanced is False
    assert result.sync_history_written is False
    assert result.scheduled_ingestion_enabled is False
    assert result.secrets_exposed is False


def test_status_success_all_units_completed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    result = _run(TestingSession, pages=[_page([_rollup_item("veh-1")], total=1)])
    assert result.status == "success"
    assert result.vehicle_batches_completed == result.vehicle_batches_attempted
    assert result.vehicle_batches_failed == 0


def test_status_failed_when_no_unit_succeeds(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    result = _run(TestingSession, pages=[_page([], total=1)])  # premature empty page
    assert result.status == "failed"
    assert result.vehicle_batches_completed == 0
    assert result.vehicle_batches_attempted > 0


def test_status_partial_success_when_some_units_fail_and_some_succeed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    pages = [_page([], total=1), _page([_rollup_item("veh-1")], total=1)]
    result = _run(TestingSession, pages=pages, horizon_days=2)
    assert result.status == "partial_success"
    assert 0 < result.vehicle_batches_completed < result.vehicle_batches_attempted


def test_status_no_op_when_zero_eligible_vehicles(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=())
    result = _run(TestingSession)
    assert result.status == "no_op"


# ---------------------------------------------------------------------------
# Manual invocation boundary: no public route, no scheduler, no FastAPI
# surface added by this module.
# ---------------------------------------------------------------------------
def test_no_new_public_route_added() -> None:
    from app.api import motive as motive_api

    route_paths = {getattr(route, "path", "") for route in motive_api.router.routes}
    assert "/api/v1/motive/sync/vehicle-utilization" not in route_paths
    assert "/api/v1/motive/reconcile/vehicle-utilization" not in route_paths
    for path in route_paths:
        assert "reconcil" not in path.lower()


def test_module_defines_no_fastapi_route_or_scheduler() -> None:
    """Checks the module's actual imports and decorators (AST-based), not
    its docstring prose, which legitimately names "FastAPI route" and
    "scheduler" to describe what this module deliberately does not add."""
    assert not hasattr(runner_module, "APIRouter")
    assert not hasattr(runner_module, "router")
    tree = ast.parse(inspect.getsource(runner_module))
    imported_modules = {
        (alias.name if isinstance(node, ast.Import) else node.module)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any(module and "fastapi" in module.lower() for module in imported_modules)
    assert not any(module and "celery" in module.lower() for module in imported_modules)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                decorator_source = ast.dump(decorator)
                assert "router" not in decorator_source.lower()


# ---------------------------------------------------------------------------
# Security: never leak secrets, vehicle identity, VIN, driver info, or raw
# provider values in the result or in log records.
# ---------------------------------------------------------------------------
def test_result_never_contains_sensitive_values(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2"))
    pages = [_page([_rollup_item("veh-1"), _rollup_item("veh-2")], total=2)]

    result = _run(TestingSession, pages=pages)

    serialized = repr(dataclasses.asdict(result))
    forbidden_tokens = [
        FAKE_API_KEY,
        "X-API-Key",
        "x-api-key",
        "Authorization",
        "Bearer",
        "veh-1",
        "veh-2",
        UNSAFE_VIN,
        UNSAFE_UNIT_NUMBER,
        UNSAFE_DRIVER_EMAIL,
    ]
    for token in forbidden_tokens:
        assert token not in serialized


def test_failed_unit_detail_never_contains_vehicle_identity(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    pages = [_page([_rollup_item("veh-unexpected")], total=1)]

    result = _run(TestingSession, pages=pages)

    serialized = repr(dataclasses.asdict(result))
    assert "veh-1" not in serialized
    assert "veh-unexpected" not in serialized
    assert result.failed_units[0].error_code == "unexpected_vehicle_observed"


def test_log_record_never_contains_sensitive_values(tmp_path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv(RECENT_RECONCILIATION_ENABLED_ENV_VAR, "true")
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    pages = [_page([_rollup_item("veh-1")], total=1)]

    with caplog.at_level(logging.INFO, logger=runner_module.logger.name):
        _run(TestingSession, pages=pages)

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    log_text += "\n".join(str(getattr(record, "__dict__", {})) for record in caplog.records)
    assert FAKE_API_KEY not in log_text
    assert "veh-1" not in log_text
    assert UNSAFE_VIN not in log_text
    assert UNSAFE_DRIVER_EMAIL not in log_text
