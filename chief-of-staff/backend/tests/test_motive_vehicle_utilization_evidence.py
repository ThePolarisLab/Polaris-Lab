from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import inspect
import json
from typing import Any

from fastapi import HTTPException
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import motive as motive_api
from app.connectors.motive_vehicle_utilization_evidence import run_vehicle_utilization_bounded_evidence
from app.database.database import Base
from app.database.models import register_models
from app.models.motive import MotiveSyncCheckpoint, MotiveVehicleRecord, MotiveVehicleUtilizationRecord
from app.organizations.models import Organization
from app.security.models import AuthenticatedPrincipal, Permission

register_models()


def _principal(org_id: str = "org-a", *, permissions: frozenset[Permission] | None = None) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        identity_id="identity-a",
        organization_id=org_id,
        membership_id="membership-a",
        role="admin",
        permissions=permissions or frozenset({Permission.CONNECTOR_WRITE}),
        provider="test",
        subject="test-user",
    )


def _payload(
    values_by_vehicle: dict[str, dict[str, Any]],
    *,
    total: int | None = None,
    wrapper: str = "vehicle_idle_rollup",
    container: str = "vehicle_idle_rollups",
) -> dict[str, Any]:
    rows = []
    for provider_vehicle_id, values in values_by_vehicle.items():
        rollup = {
            "vehicle": {
                "id": provider_vehicle_id,
                "metric_units": values.get("metric_units", True),
                "vin": "VINSHOULDNOTLEAK12",
                "number": "unit-should-not-leak",
            },
            "utilization": values.get("utilization", 50),
            "idle_time": values.get("idle_time", 0),
            "driving_time": values.get("driving_time", 0),
            "idle_fuel": values.get("idle_fuel", 0),
            "driving_fuel": values.get("driving_fuel", 0),
        }
        rows.append({wrapper: rollup})
    return {
        container: rows,
        "pagination": {"total": len(rows) if total is None else total, "page_no": 1, "per_page": 3},
    }


def _three_payloads() -> list[dict[str, Any]]:
    return [
        _payload(
            {
                "provider-vehicle-a": {"idle_time": "1.0", "driving_time": "2.0", "idle_fuel": "3.0", "driving_fuel": "4.0"},
                "provider-vehicle-b": {"idle_time": 0, "driving_time": 0, "idle_fuel": 0, "driving_fuel": 0},
                "provider-vehicle-c": {"idle_time": "5", "driving_time": "6", "idle_fuel": "7", "driving_fuel": "8"},
            }
        ),
        _payload(
            {
                "provider-vehicle-a": {"idle_time": "10.0", "driving_time": "20.0", "idle_fuel": "30.0", "driving_fuel": "40.0"},
                "provider-vehicle-b": {"idle_time": 0, "driving_time": 0, "idle_fuel": 0, "driving_fuel": 0},
                "provider-vehicle-c": {"idle_time": "50", "driving_time": "60", "idle_fuel": "70", "driving_fuel": "80"},
            }
        ),
        _payload(
            {
                "provider-vehicle-a": {"idle_time": "11.0", "driving_time": "22.0", "idle_fuel": "33.0", "driving_fuel": "44.0"},
                "provider-vehicle-b": {"idle_time": 0, "driving_time": 0, "idle_fuel": 0, "driving_fuel": 0},
                "provider-vehicle-c": {"idle_time": "55", "driving_time": "66", "idle_fuel": "77", "driving_fuel": "88"},
            }
        ),
    ]


def _client_for_payloads(payloads: list[dict[str, Any]], calls: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=payloads[len(calls) - 1])

    return httpx.Client(transport=httpx.MockTransport(handler))


def _run(payloads: list[dict[str, Any]], calls: list[httpx.Request] | None = None) -> dict[str, Any]:
    observed_calls = calls if calls is not None else []
    client = _client_for_payloads(payloads, observed_calls)
    return run_vehicle_utilization_bounded_evidence(
        organization_id="org-a",
        organization_slug="org-a",
        provider_vehicle_ids=["provider-vehicle-a", "provider-vehicle-b", "provider-vehicle-c"],
        day_a=date(2026, 8, 11),
        day_b=date(2026, 8, 12),
        http_client=client,
    )


def test_vehicle_utilization_evidence_route_requires_connector_write() -> None:
    route_paths = {getattr(route, "path", "") for route in motive_api.router.routes}
    source = inspect.getsource(motive_api.verify_motive_vehicle_utilization_evidence)

    assert "/api/v1/motive/verify/vehicle-utilization-evidence" in route_paths
    assert "require_permission(Permission.CONNECTOR_WRITE)" in source


def test_vehicle_utilization_evidence_route_selects_org_vehicles_and_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_evidence(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "success", "request_contract": {"provider_calls_attempted": 3, "provider_calls_completed": 3}}

    monkeypatch.setattr(motive_api, "run_vehicle_utilization_bounded_evidence", fake_evidence)
    monkeypatch.setattr(motive_api, "_completed_vehicle_utilization_evidence_days", lambda: (date(2026, 8, 11), date(2026, 8, 12)))

    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestingSession() as session:
        session.add(Organization(id="org-a", slug="org-a", display_name="Org A"))
        session.add(Organization(id="org-b", slug="org-b", display_name="Org B"))
        session.add(MotiveVehicleRecord(id=3, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-c"))
        session.add(MotiveVehicleRecord(id=1, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-a"))
        session.add(MotiveVehicleRecord(id=2, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-b"))
        session.add(MotiveVehicleRecord(id=4, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-d"))
        session.add(MotiveVehicleRecord(id=5, organization_id="org-b", organization_slug="org-b", provider_vehicle_id="provider-vehicle-x"))
        session.commit()

        result = motive_api.verify_motive_vehicle_utilization_evidence(principal=_principal("org-a"), session=session)

    assert result["status"] == "success"
    assert captured["organization_id"] == "org-a"
    assert captured["organization_slug"] == "org-a"
    assert captured["provider_vehicle_ids"] == ["provider-vehicle-a", "provider-vehicle-b", "provider-vehicle-c"]
    assert captured["day_a"] == date(2026, 8, 11)
    assert captured["day_b"] == date(2026, 8, 12)


def test_vehicle_utilization_evidence_route_fails_without_stored_vehicle() -> None:
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestingSession() as session:
        session.add(Organization(id="org-a", slug="org-a", display_name="Org A"))
        session.commit()
        with pytest.raises(HTTPException) as exc_info:
            motive_api.verify_motive_vehicle_utilization_evidence(principal=_principal("org-a"), session=session)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["provider_calls_attempted"] == 0


def test_vehicle_utilization_evidence_success_uses_exactly_three_bounded_provider_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    calls: list[httpx.Request] = []

    result = _run(_three_payloads(), calls)

    assert len(calls) == 3
    assert result["request_contract"]["provider_calls_attempted"] == 3
    assert result["request_contract"]["provider_calls_completed"] == 3
    assert result["request_contract"]["max_provider_calls"] == 3
    assert result["request_contract"]["max_attempts_per_call"] == 1
    expected_windows = [("2026-08-11", "2026-08-11"), ("2026-08-12", "2026-08-12"), ("2026-08-11", "2026-08-12")]
    for request, (start_date, end_date) in zip(calls, expected_windows, strict=True):
        assert request.url.path == "/v1/vehicle_utilization"
        assert [value for key, value in request.url.params.multi_items() if key == "vehicle_ids[]"] == [
            "provider-vehicle-a",
            "provider-vehicle-b",
            "provider-vehicle-c",
        ]
        assert request.url.params["start_date"] == start_date
        assert request.url.params["end_date"] == end_date
        assert request.url.params["page_no"] == "1"
        assert request.url.params["per_page"] == "3"
        assert "X-Time-Zone" not in request.headers
        assert "X-User-Id" not in request.headers
    assert result["completed_day_composition"]["two_single_days_match_combined_window"] is True
    assert result["completed_day_composition"]["supports_inclusive_date_window_interpretation"] is True
    assert result["completed_day_composition"]["utilization_percentage_added"] is False
    assert result["cardinality"]["returned_row_cardinality"]["one_unique_rollup_per_selected_vehicle_all_windows"] is True
    assert result["no_activity_evidence"]["zero_activity_shaped_rollup_observed"] is True
    assert result["persistence_readiness"]["status"] == "blocked"


@pytest.mark.parametrize(("status_code", "expected_calls"), [(400, 1), (429, 2), (500, 3)])
def test_vehicle_utilization_evidence_stops_without_retry_or_fallback(monkeypatch: pytest.MonkeyPatch, status_code: int, expected_calls: int) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == expected_calls:
            return httpx.Response(status_code, json={"error": "provider rejected the request"})
        return httpx.Response(200, json=_three_payloads()[len(calls) - 1])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = run_vehicle_utilization_bounded_evidence(
        organization_id="org-a",
        organization_slug="org-a",
        provider_vehicle_ids=["provider-vehicle-a", "provider-vehicle-b", "provider-vehicle-c"],
        day_a=date(2026, 8, 11),
        day_b=date(2026, 8, 12),
        http_client=client,
    )

    assert len(calls) == expected_calls
    assert result["status"] == "failed"
    assert result["request_contract"]["provider_calls_attempted"] == expected_calls
    assert result["request_contract"]["provider_calls_completed"] == expected_calls - 1


def test_vehicle_utilization_contract_verifier_remains_one_provider_call(monkeypatch: pytest.MonkeyPatch) -> None:
    source = inspect.getsource(motive_api.verify_motive_vehicle_utilization_contract)

    assert "run_vehicle_utilization_bounded_evidence" not in source
    assert "run_vehicle_utilization_contract_verification" in source


def test_vehicle_utilization_evidence_rounding_bound_and_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    within = _run(
        [
            _payload({"provider-vehicle-a": {"idle_time": "1.1", "driving_time": "2", "idle_fuel": "3", "driving_fuel": "4"}}),
            _payload({"provider-vehicle-a": {"idle_time": "2.2", "driving_time": "3", "idle_fuel": "4", "driving_fuel": "5"}}),
            _payload({"provider-vehicle-a": {"idle_time": "3.4", "driving_time": "5", "idle_fuel": "7", "driving_fuel": "9"}}),
        ]
    )
    mismatch = _run(
        [
            _payload({"provider-vehicle-a": {"idle_time": "1", "driving_time": "2", "idle_fuel": "3", "driving_fuel": "4"}}),
            _payload({"provider-vehicle-a": {"idle_time": "1", "driving_time": "2", "idle_fuel": "3", "driving_fuel": "4"}}),
            _payload({"provider-vehicle-a": {"idle_time": "9", "driving_time": "4", "idle_fuel": "6", "driving_fuel": "8"}}),
        ]
    )

    assert within["completed_day_composition"]["vehicle_slots"]["vehicle_slot_1"]["metrics"]["idle_time"] == "within_rounding_bound"
    assert mismatch["completed_day_composition"]["vehicle_slots"]["vehicle_slot_1"]["metrics"]["idle_time"] == "mismatch"
    assert mismatch["completed_day_composition"]["supports_inclusive_date_window_interpretation"] is False


def test_vehicle_utilization_evidence_indeterminate_states(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    result = _run(
        [
            _payload({"provider-vehicle-a": {"idle_time": None, "driving_time": "2", "idle_fuel": "3", "driving_fuel": "4", "metric_units": True}}),
            _payload({"provider-vehicle-a": {"idle_time": "1", "driving_time": "2", "idle_fuel": "3", "driving_fuel": "4", "metric_units": False}}),
            _payload({"provider-vehicle-a": {"idle_time": "1", "driving_time": "4", "idle_fuel": "6", "driving_fuel": "8", "metric_units": True}}),
        ]
    )

    metrics = result["completed_day_composition"]["vehicle_slots"]["vehicle_slot_1"]["metrics"]
    assert metrics["idle_time"] == "indeterminate_null"
    assert metrics["idle_fuel"] == "indeterminate_unit_mismatch"


def test_vehicle_utilization_evidence_missing_rollups_duplicate_unexpected_and_wrong_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    missing = _run(
        [
            _payload({"provider-vehicle-a": {"idle_time": "1"}}),
            _payload({}),
            _payload({"provider-vehicle-a": {"idle_time": "1"}}),
        ]
    )
    duplicate = _run(
        [
            _payload({"provider-vehicle-a": {"idle_time": "1"}}),
            _payload({"provider-vehicle-a": {"idle_time": "1"}}),
            {
                "vehicle_idle_rollups": [
                    _payload({"provider-vehicle-a": {"idle_time": "1"}})["vehicle_idle_rollups"][0],
                    _payload({"provider-vehicle-a": {"idle_time": "1"}})["vehicle_idle_rollups"][0],
                ],
                "pagination": {"total": 2, "page_no": 1, "per_page": 3},
            },
        ]
    )
    unexpected = _run(
        [
            _payload({"provider-vehicle-a": {"idle_time": "1"}}),
            _payload({"provider-vehicle-a": {"idle_time": "1"}}),
            _payload({"unexpected-provider-vehicle": {"idle_time": "1"}}),
        ]
    )
    wrong_envelope = _run(
        [
            _payload({"provider-vehicle-a": {"idle_time": "1"}}, container="vehicle_utilization"),
            _payload({"provider-vehicle-a": {"idle_time": "1"}}),
            _payload({"provider-vehicle-a": {"idle_time": "1"}}),
        ]
    )

    assert missing["completed_day_composition"]["vehicle_slots"]["vehicle_slot_1"]["metrics"]["idle_time"] == "indeterminate_missing_rollup"
    assert duplicate["cardinality"]["duplicate_selected_vehicle_rollup_observed"] is True
    assert duplicate["completed_day_composition"]["supports_inclusive_date_window_interpretation"] is False
    assert unexpected["cardinality"]["unexpected_vehicle_observed"] is True
    assert unexpected["completed_day_composition"]["supports_inclusive_date_window_interpretation"] is False
    assert wrong_envelope["status"] == "failed"
    assert wrong_envelope["error_code"] == "missing_container"


def test_vehicle_utilization_evidence_pagination_truncation_and_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    payloads = _three_payloads()
    payloads[0] = _payload(
        {
            "provider-vehicle-a": {
                "idle_time": "999999",
                "driving_time": "888888",
                "idle_fuel": "777777",
                "driving_fuel": "666666",
                "utilization": "555555",
            }
        },
        total=9,
    )

    result = _run(payloads)

    rendered = json.dumps(result, sort_keys=True, default=str)
    for unsafe in (
        "provider-vehicle-a",
        "provider-vehicle-b",
        "provider-vehicle-c",
        "VINSHOULDNOTLEAK12",
        "unit-should-not-leak",
        "999999",
        "888888",
        "777777",
        "666666",
        "555555",
        "fake-motive-key",
        "X-API-Key",
        "X-Time-Zone",
        "X-User-Id",
    ):
        assert unsafe not in rendered
    assert result["pagination_total"]["result_truncated_possible"] is True
    assert result["cardinality"]["windows"]["day_a"]["result_truncated_possible"] is True
    assert result["security"]["provider_ids_exposed"] is False
    assert result["security"]["metric_values_exposed"] is False


def test_vehicle_utilization_evidence_route_and_calculation_do_not_write(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    calls: list[httpx.Request] = []
    client = _client_for_payloads(_three_payloads(), calls)

    with TestingSession() as session:
        session.add(Organization(id="org-a", slug="org-a", display_name="Org A"))
        session.add(MotiveVehicleRecord(id=1, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-a"))
        session.commit()
        result = run_vehicle_utilization_bounded_evidence(
            organization_id="org-a",
            organization_slug="org-a",
            provider_vehicle_ids=["provider-vehicle-a"],
            day_a=date(2026, 8, 11),
            day_b=date(2026, 8, 12),
            http_client=client,
        )

        assert result["status"] == "success"
        assert session.query(MotiveVehicleUtilizationRecord).count() == 0
        assert session.query(MotiveSyncCheckpoint).count() == 0
        assert session.query(MotiveVehicleRecord).count() == 1
