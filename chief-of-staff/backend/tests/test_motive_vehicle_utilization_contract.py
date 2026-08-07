from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import inspect
import json
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException
import httpx
import pytest

from app.api import motive as motive_api
from app.connectors.motive import MotiveConnectorError
from app.connectors.motive_vehicle_utilization_contract import PROVIDER_400_GENERIC_MESSAGE, PROVIDER_400_MESSAGE_BY_CATEGORY, verify_vehicle_utilization_contract
from app.models.motive import MotiveSyncCheckpoint, MotiveVehicleUtilizationRecord
from app.security.models import AuthenticatedPrincipal, Permission


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
            provider_vehicle_id="provider-vehicle-secret",
            request_date=date(2026, 8, 6),
            http_client=client,
        )
    assert len(calls) == 1
    return exc_info.value


def _assert_fixed_diagnostic(diagnostics: dict[str, Any], *, category: str, original_message: str) -> None:
    assert diagnostics["provider_error_message_category"] == category
    assert diagnostics["provider_error_message"] == PROVIDER_400_MESSAGE_BY_CATEGORY[category]
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
        provider_vehicle_id="provider-vehicle-secret",
        request_date=date(2026, 8, 6),
        http_client=client,
    )

    assert len(calls) == 1
    request = calls[0]
    assert request.url.path == "/v1/vehicle_utilization"
    assert ("vehicle_ids[]", "provider-vehicle-secret") in list(request.url.params.multi_items())
    assert request.url.params["start_date"] == "2026-08-06"
    assert request.url.params["end_date"] == "2026-08-06"
    assert request.url.params["per_page"] == "1"
    assert request.url.params["page_no"] == "1"
    assert request.headers["X-API-Key"] == "fake-motive-key"
    assert request.headers["X-Time-Zone"] == "America/Winnipeg"
    assert "X-User-Id" not in request.headers

    rendered = json.dumps(result, sort_keys=True)
    assert "provider-vehicle-secret" not in rendered
    assert "fake-motive-key" not in rendered
    assert "vin-should-not-return" not in rendered
    assert "plate-should-not-return" not in rendered
    assert "83.2" not in rendered
    assert result["request_shape"]["max_provider_attempts"] == 1
    assert result["item_container_key"] == "vehicle_utilization"
    assert result["pagination_keys"] == ["page_no", "per_page", "total"]
    assert result["pagination_total_present"] is True
    assert result["vehicle_identity_paths"] == ["vehicle.id"]
    assert result["metrics"]["utilization"] == {"present": True, "type": "number", "null": False, "paths": ["utilization"]}
    assert result["metrics"]["idle_time"] == {"present": True, "type": "null", "null": True, "paths": ["idle_time"]}
    assert result["schema_compatibility"] == "compatible"
    assert result["secrets_exposed"] is False


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
    "payload",
    [
        {"error_message": "Vehicle id 123e4567-e89b-12d3-a456-426614174000 is invalid", "code": "invalid_parameter"},
        {"error_message": "User dispatcher@example.com cannot access this report"},
        {"error_message": "Vehicle VIN 1HGCM82633A004352 is invalid"},
        {"error_message": "Header X-API-Key fake-motive-key rejected"},
        {"error_message": "vehicle_ids[]=123456 and start_date=2026-08-06 rejected"},
    ],
)
def test_vehicle_utilization_contract_400_hostile_messages_never_return_raw_text(monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> None:
    exc = _contract_error_for_response(monkeypatch, httpx.Response(400, json=payload))

    rendered = json.dumps(exc.provider_diagnostics, sort_keys=True)
    for unsafe in ("123e4567", "dispatcher@example.com", "1HGCM82633A004352", "fake-motive-key", "123456", "2026-08-06", "X-API-Key"):
        assert unsafe not in rendered
    assert exc.provider_diagnostics["provider_error_message"] in PROVIDER_400_MESSAGE_BY_CATEGORY.values()


@pytest.mark.parametrize("response", [httpx.Response(400, text="bad request with vehicle 123456"), httpx.Response(400, content=b"")])
def test_vehicle_utilization_contract_non_json_or_empty_400_is_generic(monkeypatch: pytest.MonkeyPatch, response: httpx.Response) -> None:
    exc = _contract_error_for_response(monkeypatch, response)

    assert exc.provider_diagnostics == {
        "provider_error_keys": [],
        "provider_error_message_category": "unknown_provider_rejection",
        "provider_error_message": PROVIDER_400_GENERIC_MESSAGE,
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
    }
    monkeypatch.setattr(motive_api, "_organization", lambda session, organization_id: SimpleNamespace(id=organization_id, slug="org-a"))
    monkeypatch.setattr(motive_api, "_vehicle_for_utilization_contract", lambda session, organization_id: SimpleNamespace(provider_vehicle_id="provider-vehicle-secret"))
    monkeypatch.setattr(motive_api, "_completed_vehicle_utilization_contract_date", lambda: date(2026, 8, 6))

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
    assert "provider-vehicle-secret" not in json.dumps(detail)


def test_vehicle_utilization_contract_route_uses_authenticated_org_vehicle(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    selected: dict[str, Any] = {}

    monkeypatch.setattr(motive_api, "_organization", lambda session, organization_id: SimpleNamespace(id=organization_id, slug="org-a"))

    def fake_vehicle_for_contract(session: Any, organization_id: str) -> Any:
        selected["organization_id"] = organization_id
        return SimpleNamespace(provider_vehicle_id="provider-vehicle-secret")

    def fake_contract_verify(**kwargs: Any) -> dict[str, Any]:
        selected.update(kwargs)
        return {
            "status": "success",
            "endpoint": "/v1/vehicle_utilization",
            "provider_vehicle_selected": True,
            "vehicle_id_redacted": True,
            "request_period": {"start_date": "2026-08-06", "end_date": "2026-08-06"},
            "top_level_type": "object",
            "item_count_observed": 1,
            "schema_compatibility": "compatible",
            "secrets_exposed": False,
        }

    monkeypatch.setattr(motive_api, "_vehicle_for_utilization_contract", fake_vehicle_for_contract)
    monkeypatch.setattr(motive_api, "_completed_vehicle_utilization_contract_date", lambda: date(2026, 8, 6))
    monkeypatch.setattr(motive_api, "run_vehicle_utilization_contract_verification", fake_contract_verify)

    result = motive_api.verify_motive_vehicle_utilization_contract(principal=_principal("org-a"), session=NoWriteSession())

    assert selected["organization_id"] == "org-a"
    assert selected["provider_vehicle_id"] == "provider-vehicle-secret"
    assert selected["request_date"] == date(2026, 8, 6)
    assert result["vehicle_id_redacted"] is True
    rendered = json.dumps(result, sort_keys=True)
    assert "provider-vehicle-secret" not in rendered
    assert "provider-vehicle-secret" not in caplog.text


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
    monkeypatch.setattr(motive_api, "_vehicle_for_utilization_contract", lambda session, organization_id: None)

    with pytest.raises(HTTPException) as exc_info:
        motive_api.verify_motive_vehicle_utilization_contract(principal=_principal("org-a"), session=NoWriteSession())

    assert exc_info.value.status_code == 404
    detail = exc_info.value.detail
    assert detail["error_code"] == "no_stored_vehicle"
    assert detail["secrets_exposed"] is False
    assert "provider_vehicle" not in json.dumps(detail)
