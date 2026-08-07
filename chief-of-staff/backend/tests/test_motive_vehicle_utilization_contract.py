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
from app.connectors.motive_vehicle_utilization_contract import verify_vehicle_utilization_contract
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
    monkeypatch.setenv("MOTIVE_API_KEY", "fake-motive-key")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, json={"error": "rate limited"}, headers={"Retry-After": "3"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(MotiveConnectorError) as exc_info:
        verify_vehicle_utilization_contract(
            organization_id="org-a",
            provider_vehicle_id="provider-vehicle-secret",
            request_date=date(2026, 8, 6),
            http_client=client,
        )

    assert len(calls) == 1
    assert exc_info.value.code == "rate_limited"
    assert exc_info.value.retryable is False
    assert exc_info.value.retry_after == 3.0


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
