from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import inspect
import json
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import motive as motive_api
from app.connectors.motive import MotiveConnectorError
from app.connectors.motive_vehicle_utilization_contract import (
    MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES,
    PROVIDER_400_GENERIC_MESSAGE,
    PROVIDER_400_MESSAGE_BY_CATEGORY,
    request_vehicle_utilization_payload,
    verify_vehicle_utilization_contract,
)
from app.database.database import Base
from app.models.motive import MotiveSyncCheckpoint, MotiveVehicleRecord, MotiveVehicleUtilizationRecord
from app.security.models import AuthenticatedPrincipal, Permission


EXPECTED_SEMANTIC_FIELDS = {
    "mentions_header",
    "mentions_parameter",
    "mentions_user_context",
    "mentions_vehicle_context",
    "mentions_date_context",
    "mentions_permission_context",
    "mentions_required_or_missing",
    "mentions_invalid_or_rejected",
}


@dataclass
class NoWriteSession:
    commits: int = 0
    adds: int = 0
    rollbacks: int = 0

    def add(self, value: Any) -> None:
        self.adds += 1
        raise AssertionError("contract verification must not add database rows")

    def commit(self) -> None:
        self.commits += 1
        raise AssertionError("contract verification must not commit database writes")

    def rollback(self) -> None:
        self.rollbacks += 1
        raise AssertionError("contract verification must not mutate transaction state")


def _principal(org_id: str = "org-a") -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        identity_id="identity-a",
        organization_id=org_id,
        membership_id="membership-a",
        role="admin",
        permissions=frozenset({Permission.CONNECTOR_WRITE}),
        provider="test",
        subject="test-user",
    )


def _successful_payload() -> dict[str, Any]:
    return {
        "vehicle_idle_rollups": [
            {
                "vehicle_idle_rollup": {
                    "driving_fuel": 19.47,
                    "driving_time": 240.25,
                    "idle_fuel": 1.75,
                    "idle_time": 38.5,
                    "utilization": 83.23,
                    "vehicle": {
                        "id": "provider-vehicle-secret",
                        "make": "SyntheticMake",
                        "metric_units": "metric-value-should-not-return",
                        "model": "SyntheticModel",
                        "number": "unit-should-not-return",
                        "vin": "vin-should-not-return",
                        "year": 2024,
                    },
                }
            }
        ],
        "pagination": {"total": 1, "page_no": 1, "per_page": 1},
    }


def _legacy_payload_with_provider_period_fields() -> dict[str, Any]:
    return {
        "vehicle_utilization": [
            {
                "vehicle": {"id": "provider-vehicle-secret", "number": "unit-should-not-return"},
                "start_date": "2026-08-06",
                "end_date": "2026-08-06",
                "utilization": 83.2,
                "idle_time": None,
                "idle_fuel": 1.75,
                "driving_time": 240,
                "driving_fuel": 19.4,
                "vin": "vin-should-not-return",
                "license_plate": "plate-should-not-return",
                "unit": "minutes",
            }
        ],
        "pagination": {"total": 1, "page_no": 1, "per_page": 1},
    }


def _empty_vehicle_idle_rollups_payload() -> dict[str, Any]:
    return {
        "vehicle_idle_rollups": [],
        "pagination": {"total": 0, "page_no": 1, "per_page": 1},
    }


def _result_for_payload(monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> dict[str, Any]:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return verify_vehicle_utilization_contract(
        organization_id="org-a",
        provider_vehicle_ids=["provider-vehicle-secret"],
        start_date=date(2026, 8, 5),
        end_date=date(2026, 8, 6),
        http_client=client,
    )


def _contract_error_for_response(monkeypatch: pytest.MonkeyPatch, response: httpx.Response) -> MotiveConnectorError:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return response

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(MotiveConnectorError) as exc_info:
        verify_vehicle_utilization_contract(
            organization_id="org-a",
            provider_vehicle_ids=["provider-vehicle-secret"],
            start_date=date(2026, 8, 5),
            end_date=date(2026, 8, 6),
            http_client=client,
        )
    assert len(calls) == 1
    return exc_info.value


def _assert_fixed_diagnostic(diagnostics: dict[str, Any], *, category: str, original_message: str) -> None:
    assert diagnostics["provider_error_message_category"] == category
    assert diagnostics["provider_error_message"] == PROVIDER_400_MESSAGE_BY_CATEGORY[category]
    assert set(diagnostics["provider_error_semantics"]) == EXPECTED_SEMANTIC_FIELDS
    assert all(isinstance(value, bool) for value in diagnostics["provider_error_semantics"].values())
    rendered = json.dumps(diagnostics, sort_keys=True)
    assert original_message not in rendered
    assert "provider-vehicle-secret" not in rendered
    assert "fake-motive-key" not in rendered
    assert "X-API-Key" not in rendered
    assert "MOTIVE_API_KEY" not in rendered


def test_vehicle_utilization_contract_request_is_one_redacted_provider_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_successful_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = verify_vehicle_utilization_contract(
        organization_id="org-a",
        provider_vehicle_ids=["provider-vehicle-secret"],
        start_date=date(2026, 8, 5),
        end_date=date(2026, 8, 6),
        http_client=client,
    )

    assert len(calls) == 1
    request = calls[0]
    assert request.url.path == "/v1/vehicle_utilization"
    assert ("vehicle_ids[]", "provider-vehicle-secret") in list(request.url.params.multi_items())
    assert [value for key, value in request.url.params.multi_items() if key == "vehicle_ids[]"] == ["provider-vehicle-secret"]
    assert request.url.params["start_date"] == "2026-08-05"
    assert request.url.params["end_date"] == "2026-08-06"
    assert request.url.params["start_date"] < request.url.params["end_date"]
    assert request.url.params["per_page"] == "1"
    assert request.url.params["page_no"] == "1"
    assert request.headers["Accept"] == "application/json"
    assert request.headers["X-API-Key"] == "fake-motive-key"
    assert "X-Time-Zone" not in request.headers
    assert "X-User-Id" not in request.headers

    rendered = json.dumps(result, sort_keys=True)
    assert "provider-vehicle-secret" not in rendered
    assert "fake-motive-key" not in rendered
    assert "X-Time-Zone" not in rendered
    assert "vin-should-not-return" not in rendered
    assert "unit-should-not-return" not in rendered
    assert "metric-value-should-not-return" not in rendered
    assert "83.23" not in rendered
    assert "38.5" not in rendered
    assert "240.25" not in rendered
    assert "19.47" not in rendered
    assert "1.75" not in rendered
    assert result["request_shape"]["max_provider_attempts"] == 1
    assert result["request_shape"]["headers"]["Accept"] == "application/json"
    assert result["request_shape"]["headers"]["X-API-Key"] == "[REDACTED]"
    assert result["request_shape"]["headers"]["X-Metric-Units"] is None
    assert result["provider_vehicle_selected_count"] == 1
    assert result["top_level_type"] == "object"
    assert result["top_level_keys"] == ["pagination", "vehicle_idle_rollups"]
    assert result["item_container_key"] == "vehicle_idle_rollups"
    assert result["item_wrapper_key"] == "vehicle_idle_rollup"
    assert result["item_count_observed"] == 1
    assert result["item_keys"] == ["driving_fuel", "driving_time", "idle_fuel", "idle_time", "utilization", "vehicle"]
    assert result["nested_object_keys"] == {"vehicle": ["id", "make", "metric_units", "model", "number", "vin", "year"]}
    assert result["pagination_keys"] == ["page_no", "per_page", "total"]
    assert result["pagination_total_present"] is True
    assert result["pagination_page_no_present"] is True
    assert result["pagination_per_page_present"] is True
    assert result["vehicle_identity_paths"] == ["vehicle.id"]
    assert result["provider_utilization_record_id_paths"] == []
    for metric in ("utilization", "idle_time", "idle_fuel", "driving_time", "driving_fuel"):
        assert result["metrics"][metric] == {"present": True, "type": "number", "null": False, "paths": [metric]}
    assert result["period_fields"] == []
    assert "driving_time" not in result["period_fields"]
    assert "idle_time" not in result["period_fields"]
    assert result["period_source_candidate"] == "request_window_documented_summary_scope"
    assert result["schema_compatibility"] == "compatible"
    assert result["provider_schema_compatibility"] == "compatible"
    assert result["request_window"]["classification"] == "CONFIRMED"
    assert result["request_window"]["provider_returned_reporting_period_fields"] is False
    assert result["provider_reporting_period_fields"]["present"] is False
    assert result["persistence_readiness"]["status"] == "blocked"
    assert result["persistence_readiness"]["durable_identity_certified"] is False
    assert result["persistence_readiness"]["persistence_enabled"] is False
    assert result["unit_fields"] == ["vehicle_idle_rollups[].vehicle_idle_rollup.vehicle.metric_units"]
    assert result["secrets_exposed"] is False


def test_vehicle_utilization_contract_preserves_provider_period_and_nullability_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _result_for_payload(monkeypatch, _legacy_payload_with_provider_period_fields())

    assert result["item_container_key"] == "vehicle_utilization"
    assert result["period_fields"] == ["end_date", "start_date"]
    assert result["period_source_candidate"] == "provider_fields"
    assert result["schema_compatibility"] == "incomplete_provider_schema"
    assert result["metrics"]["idle_time"] == {"present": True, "type": "null", "null": True, "paths": ["idle_time"]}
    assert result["persistence_readiness"]["status"] == "blocked"


def test_vehicle_utilization_contract_requires_documented_production_envelope_for_compatibility(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _result_for_payload(monkeypatch, _successful_payload())

    assert result["item_container_key"] == "vehicle_idle_rollups"
    assert result["item_wrapper_key"] == "vehicle_idle_rollup"
    assert result["vehicle_identity_paths"] == ["vehicle.id"]
    assert result["schema_compatibility"] == "compatible"
    assert result["provider_schema_compatibility"] == "compatible"
    assert result["period_fields"] == []
    assert result["period_source_candidate"] == "request_window_documented_summary_scope"
    assert result["persistence_readiness"]["status"] == "blocked"


def test_vehicle_utilization_contract_fails_closed_for_identity_only_response(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "vehicle_idle_rollups": [{"vehicle_idle_rollup": {"vehicle": {"id": "provider-vehicle-secret"}}}],
        "pagination": {"total": 1, "page_no": 1, "per_page": 1},
    }

    result = _result_for_payload(monkeypatch, payload)

    assert result["vehicle_identity_paths"] == ["vehicle.id"]
    assert result["schema_compatibility"] == "incomplete_provider_schema"
    assert result["provider_schema_compatibility"] == "incomplete_provider_schema"
    assert result["persistence_readiness"]["status"] == "blocked"


@pytest.mark.parametrize("missing_metric", ("utilization", "idle_time", "driving_time", "idle_fuel", "driving_fuel"))
def test_vehicle_utilization_contract_fails_closed_when_required_metric_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    missing_metric: str,
) -> None:
    payload = _successful_payload()
    del payload["vehicle_idle_rollups"][0]["vehicle_idle_rollup"][missing_metric]

    result = _result_for_payload(monkeypatch, payload)

    assert result["vehicle_identity_paths"] == ["vehicle.id"]
    assert result["metrics"][missing_metric] == {"present": False, "type": None, "null": None, "paths": []}
    assert result["schema_compatibility"] == "incomplete_provider_schema"
    assert result["persistence_readiness"]["status"] == "blocked"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "vehicle_utilization": [_successful_payload()["vehicle_idle_rollups"][0]["vehicle_idle_rollup"]],
            "pagination": {"total": 1, "page_no": 1, "per_page": 1},
        },
        {
            "vehicle_idle_rollups": [{"vehicle_utilization": _successful_payload()["vehicle_idle_rollups"][0]["vehicle_idle_rollup"]}],
            "pagination": {"total": 1, "page_no": 1, "per_page": 1},
        },
    ],
)
def test_vehicle_utilization_contract_fails_closed_for_wrong_container_or_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
) -> None:
    result = _result_for_payload(monkeypatch, payload)

    assert result["vehicle_identity_paths"] == ["vehicle.id"]
    assert result["schema_compatibility"] == "incomplete_provider_schema"
    assert result["persistence_readiness"]["status"] == "blocked"


def test_vehicle_utilization_contract_filters_unsafe_container_and_wrapper_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    payload = {
        "api_key_results": [{"vehicle": {"id": "provider-vehicle-secret"}}],
        "vehicle_idle_rollups": [{"secret_wrapper": {"vehicle": {"id": "provider-vehicle-secret"}}}],
        "pagination": {"total": 1, "page_no": 1, "per_page": 1},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = verify_vehicle_utilization_contract(
        organization_id="org-a",
        provider_vehicle_ids=["provider-vehicle-secret"],
        start_date=date(2026, 8, 5),
        end_date=date(2026, 8, 6),
        http_client=client,
    )

    rendered = json.dumps(result, sort_keys=True)
    assert result["item_container_key"] == "vehicle_idle_rollups"
    assert result["item_wrapper_key"] is None
    assert "api_key_results" not in rendered
    assert "secret_wrapper" not in rendered
    assert "provider-vehicle-secret" not in rendered


def test_vehicle_utilization_contract_encodes_up_to_three_vehicle_ids_in_one_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_empty_vehicle_idle_rollups_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = verify_vehicle_utilization_contract(
        organization_id="org-a",
        provider_vehicle_ids=["provider-vehicle-a", "provider-vehicle-b", "provider-vehicle-c"],
        start_date=date(2026, 8, 5),
        end_date=date(2026, 8, 6),
        http_client=client,
    )

    assert len(calls) == 1
    request = calls[0]
    assert [value for key, value in request.url.params.multi_items() if key == "vehicle_ids[]"] == [
        "provider-vehicle-a",
        "provider-vehicle-b",
        "provider-vehicle-c",
    ]
    assert request.url.params["per_page"] == "1"
    assert request.url.params["page_no"] == "1"
    assert request.url.params["start_date"] == "2026-08-05"
    assert request.url.params["end_date"] == "2026-08-06"
    assert request.headers["Accept"] == "application/json"
    assert request.headers["X-API-Key"] == "fake-motive-key"
    assert "X-Time-Zone" not in request.headers
    assert "X-User-Id" not in request.headers
    assert result["provider_vehicle_selected_count"] == 3
    assert result["top_level_type"] == "object"
    assert result["top_level_keys"] == ["pagination", "vehicle_idle_rollups"]
    assert result["item_container_key"] == "vehicle_idle_rollups"
    assert result["item_count_observed"] == 0
    assert result["pagination_keys"] == ["page_no", "per_page", "total"]
    assert result["pagination_total_present"] is True
    assert result["pagination_page_no_present"] is True
    assert result["pagination_per_page_present"] is True
    assert result["schema_compatibility"] == "insufficient_identity"
    assert result["period_source_candidate"] == "request_window_documented_summary_scope"
    rendered = json.dumps(result, sort_keys=True)
    assert "provider-vehicle-a" not in rendered
    assert "provider-vehicle-b" not in rendered
    assert "provider-vehicle-c" not in rendered
    assert "fake-motive-key" not in rendered


def test_vehicle_utilization_contract_rejects_more_than_three_vehicle_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_successful_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(MotiveConnectorError) as exc_info:
        verify_vehicle_utilization_contract(
            organization_id="org-a",
            provider_vehicle_ids=["vehicle-a", "vehicle-b", "vehicle-c", "vehicle-d"],
            start_date=date(2026, 8, 5),
            end_date=date(2026, 8, 6),
            http_client=client,
        )

    assert exc_info.value.code == "provider_contract_error"
    assert calls == []


def test_vehicle_utilization_contract_preserves_optional_metric_units_without_time_zone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    monkeypatch.setenv("POLARIS_MOTIVE_X_METRIC_UNITS", "true")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_successful_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = verify_vehicle_utilization_contract(
        organization_id="org-a",
        provider_vehicle_ids=["provider-vehicle-secret"],
        start_date=date(2026, 8, 5),
        end_date=date(2026, 8, 6),
        http_client=client,
    )

    assert len(calls) == 1
    assert calls[0].headers["X-Metric-Units"] == "true"
    assert "X-Time-Zone" not in calls[0].headers
    assert "X-User-Id" not in calls[0].headers
    assert result["request_shape"]["headers"]["X-Metric-Units"] == "true"
    assert "X-Time-Zone" not in json.dumps(result["request_shape"], sort_keys=True)


@pytest.mark.parametrize(("explicit_metric_units", "expected_header"), [(True, "true"), (False, "false")])
def test_vehicle_utilization_request_helper_allows_explicit_writer_unit_mode(
    explicit_metric_units: bool,
    expected_header: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    monkeypatch.setenv("POLARIS_MOTIVE_X_METRIC_UNITS", "false" if explicit_metric_units is True else "true")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_successful_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    payload, http_status = request_vehicle_utilization_payload(
        organization_id="org-a",
        provider_vehicle_ids=["provider-vehicle-a", "provider-vehicle-b"],
        start_date=date(2026, 8, 5),
        end_date=date(2026, 8, 6),
        per_page=2,
        metric_units=explicit_metric_units,
        http_client=client,
    )

    assert payload == _successful_payload()
    assert http_status == 200
    assert len(calls) == 1
    assert calls[0].headers["X-Metric-Units"] == expected_header
    assert "X-Time-Zone" not in calls[0].headers
    assert "X-User-Id" not in calls[0].headers
    assert calls[0].headers["X-API-Key"] == "fake-motive-key"
    assert calls[0].url.params.multi_items() == [
        ("vehicle_ids[]", "provider-vehicle-a"),
        ("vehicle_ids[]", "provider-vehicle-b"),
        ("start_date", "2026-08-05"),
        ("end_date", "2026-08-06"),
        ("per_page", "2"),
        ("page_no", "1"),
    ]


def test_vehicle_utilization_request_helper_default_preserves_probe_environment_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    monkeypatch.setenv("POLARIS_MOTIVE_X_METRIC_UNITS", "false")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_successful_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    request_vehicle_utilization_payload(
        organization_id="org-a",
        provider_vehicle_ids=["provider-vehicle-a"],
        start_date=date(2026, 8, 5),
        end_date=date(2026, 8, 6),
        per_page=1,
        http_client=client,
    )

    assert len(calls) == 1
    assert calls[0].headers["X-Metric-Units"] == "false"


@pytest.mark.parametrize("invalid_metric_units", [1, 0, "true", "false", "metric"])
def test_vehicle_utilization_request_helper_rejects_invalid_explicit_unit_mode_before_provider_call(
    invalid_metric_units: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    monkeypatch.setenv("POLARIS_MOTIVE_X_METRIC_UNITS", "true")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_successful_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="explicit Boolean"):
        request_vehicle_utilization_payload(
            organization_id="org-a",
            provider_vehicle_ids=["provider-vehicle-a"],
            start_date=date(2026, 8, 5),
            end_date=date(2026, 8, 6),
            per_page=1,
            metric_units=invalid_metric_units,  # type: ignore[arg-type]
            http_client=client,
        )

    assert calls == []


def test_vehicle_utilization_contract_window_uses_completed_winnipeg_days(monkeypatch: pytest.MonkeyPatch) -> None:
    observed_time_zones: list[str] = []

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            observed_time_zones.append(getattr(tz, "key", str(tz)))
            return cls(2026, 8, 9, 0, 30, tzinfo=tz)

    monkeypatch.setattr(motive_api, "datetime", FixedDateTime)

    start_date, end_date = motive_api._completed_vehicle_utilization_contract_window()

    assert observed_time_zones == ["America/Winnipeg"]
    assert end_date == date(2026, 8, 8)
    assert start_date == date(2026, 8, 7)
    assert start_date < end_date
    assert start_date.isoformat() == "2026-08-07"
    assert end_date.isoformat() == "2026-08-08"


def test_vehicle_utilization_contract_does_not_retry_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = _contract_error_for_response(monkeypatch, httpx.Response(429, json={"error": "rate limited"}, headers={"Retry-After": "3"}))

    assert exc.code == "rate_limited"
    assert exc.retryable is False
    assert exc.retry_after == 3.0
    assert not hasattr(exc, "provider_diagnostics")


@pytest.mark.parametrize(
    ("payload", "expected_category", "expected_keys"),
    [
        ({"error": "X-User-Id is required"}, "missing_user_context", ["error"]),
        ({"error_message": "user id required"}, "missing_user_context", ["error_message"]),
        ({"error_message": "missing start_date"}, "missing_date_parameter", ["error_message"]),
        ({"error_message": "missing end_date"}, "missing_date_parameter", ["error_message"]),
        ({"error_message": "invalid date range"}, "invalid_date_parameter", ["error_message"]),
        ({"error_message": "vehicle_ids required"}, "missing_vehicle_parameter", ["error_message"]),
        ({"error_message": "invalid vehicle id"}, "invalid_vehicle_parameter", ["error_message"]),
        ({"error_message": "page_no parameter invalid"}, "invalid_pagination_parameter", ["error_message"]),
        ({"error_message": "authorization context required"}, "permission_context_required", ["error_message"]),
        ({"error_message": "provider refused the thing"}, "unknown_provider_rejection", ["error_message"]),
        ({"errors": [{"message": "Required context is missing", "code": "missing_context"}]}, "permission_context_required", ["errors", "errors[].code", "errors[].message"]),
    ],
)
def test_vehicle_utilization_contract_classifies_400_without_returning_provider_text(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    expected_category: str,
    expected_keys: list[str],
) -> None:
    original_message = json.dumps(payload)
    exc = _contract_error_for_response(monkeypatch, httpx.Response(400, json=payload))

    diagnostics = exc.provider_diagnostics
    assert diagnostics["provider_error_keys"] == expected_keys
    _assert_fixed_diagnostic(diagnostics, category=expected_category, original_message=original_message)


@pytest.mark.parametrize(
    ("payload", "expected_true"),
    [
        ({"error_message": "user header must be present"}, {"mentions_header", "mentions_user_context", "mentions_required_or_missing"}),
        ({"error_message": "provider could not use the vehicle argument"}, {"mentions_vehicle_context", "mentions_parameter"}),
        ({"error_message": "Vehicle reference was not allowed"}, {"mentions_vehicle_context", "mentions_invalid_or_rejected"}),
        ({"error_message": "report range could not be evaluated"}, {"mentions_date_context"}),
        ({"error_message": "scope does not include this role"}, {"mentions_permission_context", "mentions_user_context"}),
    ],
)
def test_vehicle_utilization_contract_400_semantics_for_unknown_provider_phrases(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    expected_true: set[str],
) -> None:
    original_message = json.dumps(payload)
    exc = _contract_error_for_response(monkeypatch, httpx.Response(400, json=payload))

    diagnostics = exc.provider_diagnostics
    assert diagnostics["provider_error_message_category"] == "unknown_provider_rejection"
    assert diagnostics["provider_error_message"] == PROVIDER_400_MESSAGE_BY_CATEGORY["unknown_provider_rejection"]
    semantics = diagnostics["provider_error_semantics"]
    assert set(semantics) == EXPECTED_SEMANTIC_FIELDS
    assert expected_true <= {key for key, value in semantics.items() if value}
    assert original_message not in json.dumps(diagnostics, sort_keys=True)


def test_vehicle_utilization_contract_400_semantics_inspects_error_message_string_arrays(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"error_message": ["user header must provide context", "vehicle query rejected"]}
    exc = _contract_error_for_response(monkeypatch, httpx.Response(400, json=payload))

    diagnostics = exc.provider_diagnostics
    semantics = diagnostics["provider_error_semantics"]
    assert semantics["mentions_header"] is True
    assert semantics["mentions_user_context"] is True
    assert semantics["mentions_required_or_missing"] is True
    assert semantics["mentions_vehicle_context"] is True
    assert semantics["mentions_parameter"] is True
    assert semantics["mentions_invalid_or_rejected"] is True
    rendered = json.dumps(diagnostics, sort_keys=True)
    assert "user header must provide context" not in rendered
    assert "vehicle query rejected" not in rendered


def test_vehicle_utilization_contract_400_semantics_inspects_nested_mixed_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"errors": [{"message": ["Fleet user role needed", "date range unsupported"], "code": "missing_context"}]}
    exc = _contract_error_for_response(monkeypatch, httpx.Response(400, json=payload))

    diagnostics = exc.provider_diagnostics
    assert diagnostics["provider_error_keys"] == ["errors", "errors[].code", "errors[].message"]
    semantics = diagnostics["provider_error_semantics"]
    assert semantics["mentions_user_context"] is True
    assert semantics["mentions_permission_context"] is True
    assert semantics["mentions_required_or_missing"] is True
    assert semantics["mentions_date_context"] is True
    assert semantics["mentions_invalid_or_rejected"] is True
    rendered = json.dumps(diagnostics, sort_keys=True)
    assert "Fleet user role needed" not in rendered
    assert "date range unsupported" not in rendered


@pytest.mark.parametrize(
    "payload",
    [
        {"error_message": "Vehicle id 123e4567-e89b-12d3-a456-426614174000 is invalid", "code": "invalid_parameter"},
        {"error_message": "User dispatcher@example.com cannot access this report"},
        {"error_message": "Vehicle VIN 1HGCM82633A004352 is invalid"},
        {"error_message": "Header X-API-Key fake-motive-key rejected"},
        {"error_message": "Authorization Bearer fake-token rejected"},
        {"error_message": "X-User-Id value user-123 rejected"},
        {"error_message": "vehicle_ids[]=123456 and start_date=2026-08-06 rejected"},
    ],
)
def test_vehicle_utilization_contract_400_hostile_messages_never_return_raw_text(monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> None:
    exc = _contract_error_for_response(monkeypatch, httpx.Response(400, json=payload))

    rendered = json.dumps(exc.provider_diagnostics, sort_keys=True)
    for unsafe in (
        "123e4567",
        "dispatcher@example.com",
        "1HGCM82633A004352",
        "fake-motive-key",
        "fake-token",
        "user-123",
        "123456",
        "2026-08-06",
        "X-API-Key",
        "Authorization",
        "MOTIVE_API_KEY",
        "provider-vehicle-secret",
        "X-User-Id",
        "X-User-Id value",
    ):
        assert unsafe not in rendered
    assert exc.provider_diagnostics["provider_error_message"] in PROVIDER_400_MESSAGE_BY_CATEGORY.values()
    assert set(exc.provider_diagnostics["provider_error_semantics"]) == EXPECTED_SEMANTIC_FIELDS


@pytest.mark.parametrize("response", [httpx.Response(400, text="bad request with vehicle 123456"), httpx.Response(400, content=b"")])
def test_vehicle_utilization_contract_non_json_or_empty_400_is_generic(monkeypatch: pytest.MonkeyPatch, response: httpx.Response) -> None:
    exc = _contract_error_for_response(monkeypatch, response)

    assert exc.provider_diagnostics == {
        "provider_error_keys": [],
        "provider_error_message_category": "unknown_provider_rejection",
        "provider_error_message": PROVIDER_400_GENERIC_MESSAGE,
        "provider_error_semantics": {field: False for field in EXPECTED_SEMANTIC_FIELDS},
    }


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [(401, "authorization_required"), (403, "permission_denied"), (500, "provider_unavailable")],
)
def test_vehicle_utilization_contract_existing_error_behavior_unchanged(monkeypatch: pytest.MonkeyPatch, status_code: int, expected_code: str) -> None:
    exc = _contract_error_for_response(monkeypatch, httpx.Response(status_code, json={"error": "provider failure"}))

    assert exc.code == expected_code
    assert not hasattr(exc, "provider_diagnostics")


def test_vehicle_utilization_contract_route_returns_sanitized_400_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    connector_error = MotiveConnectorError("Motive vehicle utilization contract request failed with HTTP 400", code="http_400")
    connector_error.provider_diagnostics = {
        "provider_error_keys": ["error_message"],
        "provider_error_message_category": "missing_user_context",
        "provider_error_message": PROVIDER_400_MESSAGE_BY_CATEGORY["missing_user_context"],
        "provider_error_semantics": {
            "mentions_header": True,
            "mentions_parameter": False,
            "mentions_user_context": True,
            "mentions_vehicle_context": False,
            "mentions_date_context": False,
            "mentions_permission_context": False,
            "mentions_required_or_missing": True,
            "mentions_invalid_or_rejected": False,
        },
    }
    monkeypatch.setattr(motive_api, "_organization", lambda session, organization_id: SimpleNamespace(id=organization_id, slug="org-a"))
    monkeypatch.setattr(motive_api, "_vehicles_for_utilization_contract", lambda session, organization_id: [SimpleNamespace(provider_vehicle_id="provider-vehicle-secret")])
    monkeypatch.setattr(motive_api, "_completed_vehicle_utilization_contract_window", lambda: (date(2026, 8, 5), date(2026, 8, 6)))

    def fake_contract_verify(**kwargs: Any) -> dict[str, Any]:
        raise connector_error

    monkeypatch.setattr(motive_api, "run_vehicle_utilization_contract_verification", fake_contract_verify)

    with pytest.raises(HTTPException) as exc_info:
        motive_api.verify_motive_vehicle_utilization_contract(principal=_principal("org-a"), session=NoWriteSession())

    detail = exc_info.value.detail
    assert detail["error_code"] == "http_400"
    assert detail["provider_error_keys"] == ["error_message"]
    assert detail["provider_error_message_category"] == "missing_user_context"
    assert detail["provider_error_message"] == PROVIDER_400_MESSAGE_BY_CATEGORY["missing_user_context"]
    assert detail["provider_error_semantics"]["mentions_header"] is True
    assert detail["provider_error_semantics"]["mentions_user_context"] is True
    assert "provider-vehicle-secret" not in json.dumps(detail)


def test_vehicle_utilization_contract_selects_up_to_three_org_vehicles_in_internal_order() -> None:
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestingSession() as session:
        session.add(MotiveVehicleRecord(id=30, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-c"))
        session.add(MotiveVehicleRecord(id=10, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-a"))
        session.add(MotiveVehicleRecord(id=25, organization_id="org-b", organization_slug="org-b", provider_vehicle_id="provider-vehicle-other"))
        session.add(MotiveVehicleRecord(id=40, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-d"))
        session.add(MotiveVehicleRecord(id=20, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-b"))
        session.commit()

        vehicles = motive_api._vehicles_for_utilization_contract(session, "org-a")

    assert MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES == 3
    assert [vehicle.provider_vehicle_id for vehicle in vehicles] == [
        "provider-vehicle-a",
        "provider-vehicle-b",
        "provider-vehicle-c",
    ]


def test_vehicle_utilization_contract_route_uses_authenticated_org_vehicles(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    selected: dict[str, Any] = {}

    monkeypatch.setattr(motive_api, "_organization", lambda session, organization_id: SimpleNamespace(id=organization_id, slug="org-a"))

    def fake_vehicles_for_contract(session: Any, organization_id: str) -> list[Any]:
        selected["organization_id"] = organization_id
        return [
            SimpleNamespace(provider_vehicle_id="provider-vehicle-a"),
            SimpleNamespace(provider_vehicle_id="provider-vehicle-b"),
        ]

    def fake_contract_verify(**kwargs: Any) -> dict[str, Any]:
        selected.update(kwargs)
        return {
            "status": "success",
            "endpoint": "/v1/vehicle_utilization",
            "provider_vehicle_selected": True,
            "provider_vehicle_selected_count": 2,
            "vehicle_id_redacted": True,
            "request_period": {"start_date": "2026-08-05", "end_date": "2026-08-06"},
            "top_level_type": "object",
            "item_count_observed": 1,
            "schema_compatibility": "compatible",
            "secrets_exposed": False,
        }

    monkeypatch.setattr(motive_api, "_vehicles_for_utilization_contract", fake_vehicles_for_contract)
    monkeypatch.setattr(motive_api, "_completed_vehicle_utilization_contract_window", lambda: (date(2026, 8, 5), date(2026, 8, 6)))
    monkeypatch.setattr(motive_api, "run_vehicle_utilization_contract_verification", fake_contract_verify)

    result = motive_api.verify_motive_vehicle_utilization_contract(principal=_principal("org-a"), session=NoWriteSession())

    assert selected["organization_id"] == "org-a"
    assert selected["provider_vehicle_ids"] == ["provider-vehicle-a", "provider-vehicle-b"]
    assert selected["start_date"] == date(2026, 8, 5)
    assert selected["end_date"] == date(2026, 8, 6)
    assert selected["start_date"] < selected["end_date"]
    assert result["vehicle_id_redacted"] is True
    assert result["provider_vehicle_selected_count"] == 2
    rendered = json.dumps(result, sort_keys=True)
    assert "provider-vehicle-a" not in rendered
    assert "provider-vehicle-b" not in rendered
    assert "provider-vehicle-a" not in caplog.text
    assert "provider-vehicle-b" not in caplog.text


def test_vehicle_utilization_contract_route_has_no_client_vehicle_parameter_or_persistence() -> None:
    signature = inspect.signature(motive_api.verify_motive_vehicle_utilization_contract)
    assert "vehicle_id" not in signature.parameters
    assert "provider_vehicle_id" not in signature.parameters

    source = inspect.getsource(motive_api.verify_motive_vehicle_utilization_contract)
    assert "session.commit" not in source
    assert "session.add" not in source
    assert "MotiveVehicleUtilizationRecord" not in source
    assert "MotiveSyncCheckpoint" not in source
    assert "quickbooks" not in source.lower()
    assert "outlook" not in source.lower()
    assert MotiveVehicleUtilizationRecord.__tablename__ == "motive_vehicle_utilization"
    assert MotiveSyncCheckpoint.__tablename__ == "motive_sync_checkpoints"


def test_vehicle_utilization_contract_route_fails_safely_without_stored_vehicle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(motive_api, "_organization", lambda session, organization_id: SimpleNamespace(id=organization_id, slug="org-a"))
    monkeypatch.setattr(motive_api, "_vehicles_for_utilization_contract", lambda session, organization_id: [])

    with pytest.raises(HTTPException) as exc_info:
        motive_api.verify_motive_vehicle_utilization_contract(principal=_principal("org-a"), session=NoWriteSession())

    assert exc_info.value.status_code == 404
    detail = exc_info.value.detail
    assert detail["error_code"] == "no_stored_vehicle"
    assert detail["secrets_exposed"] is False
    assert "provider_vehicle" not in json.dumps(detail)
