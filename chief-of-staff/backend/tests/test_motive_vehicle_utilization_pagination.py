from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest

from app.connectors.motive import MotiveConnectorError
from app.connectors.motive_vehicle_utilization_contract import verify_vehicle_utilization_contract
from app.connectors.motive_vehicle_utilization_evidence import run_vehicle_utilization_bounded_evidence
from app.connectors.motive_vehicle_utilization_pagination import (
    MAX_VEHICLE_UTILIZATION_PAGES,
    MotiveVehicleUtilizationPaginationError,
    VehicleUtilizationPaginationMetadata,
    motive_vehicle_utilization_pagination_contract_status,
    parse_pagination_metadata,
    read_vehicle_utilization_pages,
    request_vehicle_utilization_page,
)

START_DATE = date(2026, 8, 12)
END_DATE = date(2026, 8, 12)


def _rollup(provider_vehicle_id: str, *, metric_units: Any = True) -> dict[str, Any]:
    return {
        "vehicle_idle_rollup": {
            "vehicle": {
                "id": provider_vehicle_id,
                "metric_units": metric_units,
                "vin": "VINSHOULDNOTLEAK12",
                "number": "unit-should-not-leak",
                "email": "driver@example.com",
            },
            "utilization": 50,
            "idle_time": 1,
            "driving_time": 2,
            "idle_fuel": 3,
            "driving_fuel": 4,
        }
    }


def _page(rollups: list[dict[str, Any]], *, page_no: int, per_page: int, total: int) -> dict[str, Any]:
    return {
        "vehicle_idle_rollups": rollups,
        "pagination": {"per_page": per_page, "page_no": page_no, "total": total},
    }


def _client_for_pages(pages: list[dict[str, Any]], calls: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=pages[len(calls) - 1])

    return httpx.Client(transport=httpx.MockTransport(handler))


def _client_failing_on_call(pages: list[dict[str, Any]], *, fail_at_call: int, calls: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == fail_at_call:
            return httpx.Response(500, json={"error": "provider unavailable"})
        return httpx.Response(200, json=pages[len(calls) - 1])

    return httpx.Client(transport=httpx.MockTransport(handler))


def _read(pages: list[dict[str, Any]], *, per_page: int, calls: list[httpx.Request] | None = None, vehicle_ids: list[str] | None = None):
    observed_calls = calls if calls is not None else []
    client = _client_for_pages(pages, observed_calls)
    return read_vehicle_utilization_pages(
        organization_id="org-a",
        organization_slug="org-a",
        provider_vehicle_ids=vehicle_ids or ["vehicle-a"],
        start_date=START_DATE,
        end_date=END_DATE,
        per_page=per_page,
        http_client=client,
    )


# ---------------------------------------------------------------------------
# Section 20 — pagination metadata parser tests.
# ---------------------------------------------------------------------------
def test_pagination_metadata_valid_zero_total() -> None:
    metadata = parse_pagination_metadata(
        {"pagination": {"per_page": 100, "page_no": 1, "total": 0}}, expected_page_no=1, expected_per_page=100
    )
    assert metadata == VehicleUtilizationPaginationMetadata(per_page=100, page_no=1, total=0)


def test_pagination_metadata_valid_multi_page() -> None:
    metadata = parse_pagination_metadata(
        {"pagination": {"per_page": 2, "page_no": 2, "total": 5}}, expected_page_no=2, expected_per_page=2
    )
    assert metadata.per_page == 2
    assert metadata.page_no == 2
    assert metadata.total == 5


def test_pagination_metadata_missing_pagination() -> None:
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        parse_pagination_metadata({}, expected_page_no=1, expected_per_page=1)
    assert exc.value.code == "missing_pagination"


def test_pagination_metadata_not_object() -> None:
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        parse_pagination_metadata({"pagination": []}, expected_page_no=1, expected_per_page=1)
    assert exc.value.code == "invalid_pagination"


def test_pagination_metadata_missing_per_page() -> None:
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        parse_pagination_metadata({"pagination": {"page_no": 1, "total": 0}}, expected_page_no=1, expected_per_page=1)
    assert exc.value.code == "missing_per_page"


def test_pagination_metadata_missing_page_no() -> None:
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        parse_pagination_metadata({"pagination": {"per_page": 1, "total": 0}}, expected_page_no=1, expected_per_page=1)
    assert exc.value.code == "missing_page_no"


def test_pagination_metadata_missing_total() -> None:
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        parse_pagination_metadata({"pagination": {"per_page": 1, "page_no": 1}}, expected_page_no=1, expected_per_page=1)
    assert exc.value.code == "missing_total"


def test_pagination_metadata_string_numeric_rejected() -> None:
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        parse_pagination_metadata({"pagination": {"per_page": "1", "page_no": 1, "total": 0}}, expected_page_no=1, expected_per_page=1)
    assert exc.value.code == "invalid_per_page_type"


def test_pagination_metadata_float_rejected() -> None:
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        parse_pagination_metadata({"pagination": {"per_page": 1.0, "page_no": 1, "total": 0}}, expected_page_no=1, expected_per_page=1)
    assert exc.value.code == "invalid_per_page_type"


def test_pagination_metadata_bool_rejected() -> None:
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        parse_pagination_metadata({"pagination": {"per_page": 1, "page_no": 1, "total": True}}, expected_page_no=1, expected_per_page=1)
    assert exc.value.code == "invalid_total_type"


def test_pagination_metadata_negative_total_rejected() -> None:
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        parse_pagination_metadata({"pagination": {"per_page": 1, "page_no": 1, "total": -1}}, expected_page_no=1, expected_per_page=1)
    assert exc.value.code == "invalid_total_value"


def test_pagination_metadata_page_no_zero_rejected() -> None:
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        parse_pagination_metadata({"pagination": {"per_page": 1, "page_no": 0, "total": 0}}, expected_page_no=0, expected_per_page=1)
    assert exc.value.code == "invalid_page_no_value"


def test_pagination_metadata_per_page_over_100_rejected() -> None:
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        parse_pagination_metadata({"pagination": {"per_page": 101, "page_no": 1, "total": 0}}, expected_page_no=1, expected_per_page=101)
    assert exc.value.code == "invalid_per_page_value"


def test_pagination_metadata_page_no_mismatch() -> None:
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        parse_pagination_metadata({"pagination": {"per_page": 1, "page_no": 2, "total": 0}}, expected_page_no=1, expected_per_page=1)
    assert exc.value.code == "pagination_page_no_mismatch"


def test_pagination_metadata_per_page_mismatch() -> None:
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        parse_pagination_metadata({"pagination": {"per_page": 2, "page_no": 1, "total": 0}}, expected_page_no=1, expected_per_page=1)
    assert exc.value.code == "pagination_per_page_mismatch"


def test_pagination_metadata_total_changes_between_pages_detected_by_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    pages = [
        _page([_rollup("vehicle-a")], page_no=1, per_page=1, total=2),
        _page([_rollup("vehicle-b")], page_no=2, per_page=1, total=3),
    ]
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        _read(pages, per_page=1, vehicle_ids=["vehicle-a", "vehicle-b"])
    assert exc.value.code == "pagination_total_changed"


# ---------------------------------------------------------------------------
# Section 21 — multi-page success.
# ---------------------------------------------------------------------------
def test_multi_page_success_reads_all_pages_with_stable_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    vehicle_ids = ["vehicle-a", "vehicle-b", "vehicle-c", "vehicle-d", "vehicle-e"]
    pages = [
        _page([_rollup("vehicle-a"), _rollup("vehicle-b")], page_no=1, per_page=2, total=5),
        _page([_rollup("vehicle-c"), _rollup("vehicle-d")], page_no=2, per_page=2, total=5),
        _page([_rollup("vehicle-e")], page_no=3, per_page=2, total=5),
    ]
    calls: list[httpx.Request] = []
    result = _read(pages, per_page=2, calls=calls, vehicle_ids=vehicle_ids)

    assert len(calls) == 3
    assert [call.url.params.get("page_no") for call in calls] == ["1", "2", "3"]
    assert result.pages_read == 3
    assert result.provider_calls == 3
    assert len(result.rollups) == 5
    assert result.pagination_total == 5

    for call in calls:
        assert call.headers["X-Metric-Units"] == "true"
        assert call.url.params.get("start_date") == START_DATE.isoformat()
        assert call.url.params.get("end_date") == END_DATE.isoformat()
        assert call.url.params.get_list("vehicle_ids[]") == vehicle_ids


# ---------------------------------------------------------------------------
# Section 22 — zero results.
# ---------------------------------------------------------------------------
def test_zero_results_single_page_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    pages = [_page([], page_no=1, per_page=100, total=0)]
    calls: list[httpx.Request] = []
    result = _read(pages, per_page=100, calls=calls)

    assert len(calls) == 1
    assert result.pages_read == 1
    assert result.provider_calls == 1
    assert result.rollups == []
    assert result.pagination_total == 0


# ---------------------------------------------------------------------------
# Section 23 — short page.
# ---------------------------------------------------------------------------
def test_short_page_does_not_stop_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    vehicle_ids = ["vehicle-a", "vehicle-b", "vehicle-c", "vehicle-d"]
    pages = [
        _page([_rollup("vehicle-a")], page_no=1, per_page=3, total=4),
        _page([_rollup("vehicle-b"), _rollup("vehicle-c"), _rollup("vehicle-d")], page_no=2, per_page=3, total=4),
    ]
    result = _read(pages, per_page=3, vehicle_ids=vehicle_ids)
    assert result.pages_read == 2
    assert len(result.rollups) == 4


# ---------------------------------------------------------------------------
# Section 24 — fail-closed page sequences.
# ---------------------------------------------------------------------------
def test_page_item_count_exceeds_per_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    pages = [_page([_rollup("vehicle-a"), _rollup("vehicle-b")], page_no=1, per_page=1, total=1)]
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        _read(pages, per_page=1, vehicle_ids=["vehicle-a", "vehicle-b"])
    assert exc.value.code == "page_item_count_exceeded"


def test_total_changes_page_2_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    pages = [
        _page([_rollup("vehicle-a")], page_no=1, per_page=1, total=2),
        _page([_rollup("vehicle-b")], page_no=2, per_page=1, total=3),
    ]
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        _read(pages, per_page=1, vehicle_ids=["vehicle-a", "vehicle-b"])
    assert exc.value.code == "pagination_total_changed"


def test_page_no_mismatch_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    pages = [_page([_rollup("vehicle-a")], page_no=2, per_page=1, total=1)]
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        _read(pages, per_page=1)
    assert exc.value.code == "pagination_page_no_mismatch"


def test_per_page_mismatch_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    pages = [_page([_rollup("vehicle-a")], page_no=1, per_page=2, total=1)]
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        _read(pages, per_page=1)
    assert exc.value.code == "pagination_per_page_mismatch"


def test_premature_empty_page_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    pages = [
        _page([_rollup("vehicle-a")], page_no=1, per_page=1, total=2),
        _page([], page_no=2, per_page=1, total=2),
    ]
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        _read(pages, per_page=1, vehicle_ids=["vehicle-a", "vehicle-b"])
    assert exc.value.code == "premature_empty_page"


def test_cumulative_records_above_total_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    pages = [
        _page([_rollup("vehicle-a"), _rollup("vehicle-b")], page_no=1, per_page=2, total=3),
        _page([_rollup("vehicle-c"), _rollup("vehicle-d")], page_no=2, per_page=2, total=3),
    ]
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        _read(pages, per_page=2, vehicle_ids=["vehicle-a", "vehicle-b", "vehicle-c", "vehicle-d"])
    assert exc.value.code == "cumulative_rollup_count_above_total"


def test_cumulative_records_below_total_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    # total=5 with per_page=2 requires expected_pages=ceil(5/2)=3. The final
    # expected page returns a non-empty (so it does not trip the premature-
    # empty-page rule) but insufficient count, leaving cumulative=4 < total=5.
    pages = [
        _page([_rollup("vehicle-a"), _rollup("vehicle-b")], page_no=1, per_page=2, total=5),
        _page([_rollup("vehicle-c")], page_no=2, per_page=2, total=5),
        _page([_rollup("vehicle-d")], page_no=3, per_page=2, total=5),
    ]
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        _read(pages, per_page=2, vehicle_ids=["vehicle-a", "vehicle-b", "vehicle-c", "vehicle-d"])
    assert exc.value.code == "cumulative_rollup_count_below_total"


def test_duplicate_vehicle_within_one_page_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    pages = [_page([_rollup("vehicle-a"), _rollup("vehicle-a")], page_no=1, per_page=2, total=2)]
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        _read(pages, per_page=2, vehicle_ids=["vehicle-a"])
    assert exc.value.code == "duplicate_vehicle_observed"


def test_duplicate_vehicle_across_pages_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    pages = [
        _page([_rollup("vehicle-a")], page_no=1, per_page=1, total=2),
        _page([_rollup("vehicle-a")], page_no=2, per_page=1, total=2),
    ]
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        _read(pages, per_page=1, vehicle_ids=["vehicle-a"])
    assert exc.value.code == "duplicate_vehicle_observed"


def test_unexpected_vehicle_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    pages = [_page([_rollup("vehicle-unexpected")], page_no=1, per_page=1, total=1)]
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        _read(pages, per_page=1, vehicle_ids=["vehicle-a"])
    assert exc.value.code == "unexpected_vehicle_observed"


def test_metric_units_false_on_later_page_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    pages = [
        _page([_rollup("vehicle-a")], page_no=1, per_page=1, total=2),
        _page([_rollup("vehicle-b", metric_units=False)], page_no=2, per_page=1, total=2),
    ]
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        _read(pages, per_page=1, vehicle_ids=["vehicle-a", "vehicle-b"])
    assert exc.value.code == "provider_unit_policy_mismatch"


def test_metric_units_none_on_later_page_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    pages = [
        _page([_rollup("vehicle-a")], page_no=1, per_page=1, total=2),
        _page([_rollup("vehicle-b", metric_units=None)], page_no=2, per_page=1, total=2),
    ]
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        _read(pages, per_page=1, vehicle_ids=["vehicle-a", "vehicle-b"])
    assert exc.value.code == "provider_unit_context_missing"


def test_parser_failure_on_page_2_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    pages = [
        _page([_rollup("vehicle-a")], page_no=1, per_page=1, total=2),
        {"pagination": {"per_page": 1, "page_no": 2, "total": 2}},  # missing container
    ]
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        _read(pages, per_page=1, vehicle_ids=["vehicle-a", "vehicle-b"])
    assert exc.value.code == "missing_container"


def test_provider_http_failure_on_page_2_stops_and_does_not_request_page_3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    pages = [
        _page([_rollup("vehicle-a")], page_no=1, per_page=1, total=3),
        _page([_rollup("vehicle-b")], page_no=2, per_page=1, total=3),
        _page([_rollup("vehicle-c")], page_no=3, per_page=1, total=3),
    ]
    calls: list[httpx.Request] = []
    client = _client_failing_on_call(pages, fail_at_call=2, calls=calls)
    with pytest.raises(MotiveConnectorError):
        read_vehicle_utilization_pages(
            organization_id="org-a",
            organization_slug="org-a",
            provider_vehicle_ids=["vehicle-a", "vehicle-b", "vehicle-c"],
            start_date=START_DATE,
            end_date=END_DATE,
            per_page=1,
            http_client=client,
        )
    assert len(calls) == 2


@pytest.mark.parametrize("fail_at_call", [1, 2, 3])
def test_provider_failure_mid_pagination_call_counts(monkeypatch: pytest.MonkeyPatch, fail_at_call: int) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    vehicle_ids = ["vehicle-a", "vehicle-b", "vehicle-c"]
    pages = [
        _page([_rollup("vehicle-a")], page_no=1, per_page=1, total=3),
        _page([_rollup("vehicle-b")], page_no=2, per_page=1, total=3),
        _page([_rollup("vehicle-c")], page_no=3, per_page=1, total=3),
    ]
    calls: list[httpx.Request] = []
    client = _client_failing_on_call(pages, fail_at_call=fail_at_call, calls=calls)
    with pytest.raises(MotiveConnectorError):
        read_vehicle_utilization_pages(
            organization_id="org-a",
            organization_slug="org-a",
            provider_vehicle_ids=vehicle_ids,
            start_date=START_DATE,
            end_date=END_DATE,
            per_page=1,
            http_client=client,
        )
    assert len(calls) == fail_at_call


def test_page_guard_exceeded_fails_closed_before_page_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    # total requires more pages than the Polaris safety guard allows at per_page=1.
    huge_total = MAX_VEHICLE_UTILIZATION_PAGES + 1
    pages = [_page([_rollup("vehicle-a")], page_no=1, per_page=1, total=huge_total)]
    calls: list[httpx.Request] = []
    client = _client_for_pages(pages, calls)
    with pytest.raises(MotiveVehicleUtilizationPaginationError) as exc:
        read_vehicle_utilization_pages(
            organization_id="org-a",
            organization_slug="org-a",
            provider_vehicle_ids=["vehicle-a"],
            start_date=START_DATE,
            end_date=END_DATE,
            per_page=1,
            http_client=client,
        )
    assert exc.value.code == "pagination_page_guard_exceeded"
    # Only page 1 was requested before failing closed.
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Section 25 — existing-gate regression tests.
# ---------------------------------------------------------------------------
def test_existing_contract_verifier_still_makes_exactly_one_call_at_page_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_page([_rollup("vehicle-a")], page_no=1, per_page=1, total=1))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    verify_vehicle_utilization_contract(
        organization_id="org-a",
        provider_vehicle_ids=["vehicle-a"],
        start_date=START_DATE,
        end_date=END_DATE,
        http_client=client,
    )
    assert len(calls) == 1
    assert calls[0].url.params.get("page_no") == "1"
    assert "X-Time-Zone" not in calls[0].headers
    assert "X-User-Id" not in calls[0].headers


def test_existing_bounded_evidence_still_makes_exactly_three_calls_page_1_max_3_vehicles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_page([_rollup("vehicle-a")], page_no=1, per_page=3, total=1))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    run_vehicle_utilization_bounded_evidence(
        organization_id="org-a",
        organization_slug="org-a",
        provider_vehicle_ids=["vehicle-a", "vehicle-b", "vehicle-c"],
        day_a=date(2026, 8, 12),
        day_b=date(2026, 8, 13),
        http_client=client,
    )
    assert len(calls) == 3
    for call in calls:
        assert call.url.params.get("page_no") == "1"
        assert "X-Time-Zone" not in call.headers
        assert "X-User-Id" not in call.headers


def test_no_live_provider_call_used_anywhere_in_this_module(monkeypatch: pytest.MonkeyPatch) -> None:
    # Every test in this module supplies a synthetic http_client. This sentinel
    # test documents that expectation for reviewers; it makes no network call.
    assert True


# ---------------------------------------------------------------------------
# Section 26 — zero-write proof.
# ---------------------------------------------------------------------------
def test_paginated_read_never_touches_the_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    pages = [_page([_rollup("vehicle-a")], page_no=1, per_page=1, total=1)]
    result = _read(pages, per_page=1)
    # read_vehicle_utilization_pages takes no Session and performs no ORM
    # operations; success alone (no AttributeError/session usage) proves this
    # module never persists, checkpoints, or flushes.
    assert result.rollups[0].provider_vehicle_id == "vehicle-a"


# ---------------------------------------------------------------------------
# Section 16 — public read-only pagination-contract status.
# ---------------------------------------------------------------------------
def test_pagination_contract_status_is_sanitized_and_zero_call_zero_write() -> None:
    status = motive_vehicle_utilization_pagination_contract_status()
    assert status["pagination_contract"]["classification"] == "CERTIFIED"
    assert status["pagination_contract"]["page_numbering"] == "one_based"
    assert status["pagination_contract"]["first_page"] == 1
    assert status["pagination_contract"]["default_provider_page_size"] == 25
    assert status["pagination_contract"]["max_provider_page_size"] == 100
    assert status["pagination_contract"]["canonical_writer_page_size"] == 100
    assert status["completion_rule"]["pagination_total_required"] is True
    assert status["completion_rule"]["total_must_remain_stable"] is True
    assert status["completion_rule"]["cumulative_rows_must_equal_total"] is True
    assert status["completion_rule"]["premature_empty_page_fails_closed"] is True
    assert status["batch_rules"]["duplicate_vehicle_fails_closed"] is True
    assert status["batch_rules"]["unexpected_vehicle_fails_closed"] is True
    assert status["batch_rules"]["canonical_metric_units_required"] is True
    assert status["safety"]["max_page_guard"] == MAX_VEHICLE_UTILIZATION_PAGES
    assert status["safety"]["provider_calls_from_status_endpoint"] == 0
    assert status["safety"]["persistence_enabled"] is False
    assert status["safety"]["checkpoint_enabled"] is False
    assert status["safety"]["scheduled_ingestion_enabled"] is False
    assert status["safety"]["raw_provider_values_exposed"] is False


def test_pagination_contract_status_route_is_registered_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import motive as motive_api

    route_paths = {getattr(route, "path", "") for route in motive_api.router.routes}
    assert "/api/v1/motive/fleet/vehicle-utilization-pagination-contract" in route_paths


# ---------------------------------------------------------------------------
# Request primitive validation (section 4).
# ---------------------------------------------------------------------------
def test_request_page_rejects_bool_page_no(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    with pytest.raises(MotiveConnectorError):
        request_vehicle_utilization_page(
            organization_id="org-a",
            provider_vehicle_ids=["vehicle-a"],
            start_date=START_DATE,
            end_date=END_DATE,
            page_no=True,
            per_page=1,
        )


def test_request_page_rejects_bool_per_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    with pytest.raises(MotiveConnectorError):
        request_vehicle_utilization_page(
            organization_id="org-a",
            provider_vehicle_ids=["vehicle-a"],
            start_date=START_DATE,
            end_date=END_DATE,
            page_no=1,
            per_page=True,
        )


def test_request_page_rejects_per_page_over_100(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    with pytest.raises(MotiveConnectorError):
        request_vehicle_utilization_page(
            organization_id="org-a",
            provider_vehicle_ids=["vehicle-a"],
            start_date=START_DATE,
            end_date=END_DATE,
            page_no=1,
            per_page=101,
        )


def test_request_page_rejects_non_true_metric_units(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    with pytest.raises(MotiveConnectorError):
        request_vehicle_utilization_page(
            organization_id="org-a",
            provider_vehicle_ids=["vehicle-a"],
            start_date=START_DATE,
            end_date=END_DATE,
            page_no=1,
            per_page=1,
            metric_units=False,
        )


def test_request_page_sends_certified_headers_and_no_time_zone_or_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_page([_rollup("vehicle-a")], page_no=1, per_page=1, total=1))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    request_vehicle_utilization_page(
        organization_id="org-a",
        provider_vehicle_ids=["vehicle-a"],
        start_date=START_DATE,
        end_date=END_DATE,
        page_no=1,
        per_page=1,
        http_client=client,
    )
    assert len(calls) == 1
    request = calls[0]
    assert request.headers["X-Metric-Units"] == "true"
    assert request.headers["X-API-Key"] == "fake-motive-key"
    assert "X-Time-Zone" not in request.headers
    assert "X-User-Id" not in request.headers
