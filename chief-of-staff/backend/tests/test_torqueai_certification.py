from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.connectors import torqueai
from app.connectors.torqueai import TorqueAIConnector
from app.main import app
from tests.auth_helpers import seed_principal

TOKEN = "tk_certification_test_secret"
BASE_URL = "https://morlogistics.kordovatek.com"
CERTIFICATION_DATE = "2026-08-27"


def _configure(monkeypatch: pytest.MonkeyPatch, organization_slug: str) -> None:
    monkeypatch.setenv(torqueai.TORQUEAI_API_TOKEN_ENV, TOKEN)
    monkeypatch.setenv(torqueai.TORQUEAI_BASE_URL_ENV, BASE_URL)
    monkeypatch.setenv(torqueai.TORQUEAI_ORGANIZATION_SLUG_ENV, organization_slug)


def _install_mock_http(monkeypatch: pytest.MonkeyPatch, handler) -> httpx.Client:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(TorqueAIConnector, "_http", lambda _self: client)
    return client


def test_certification_route_makes_one_bounded_get_and_returns_metadata_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization, _identity, headers = seed_principal("viewer")
    _configure(monkeypatch, organization["slug"])
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "GET"
        assert request.url.scheme == "https"
        assert request.url.host == "morlogistics.kordovatek.com"
        assert request.url.path == torqueai.TORQUEAI_DISPATCH_PATH
        assert request.url.params == httpx.QueryParams(
            {
                "from": CERTIFICATION_DATE,
                "to": CERTIFICATION_DATE,
                "page": "1",
                "limit": "100",
            }
        )
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "loadNumber": 1053,
                        "customerName": "Secret Customer Value",
                        "driverName": "Secret Driver Value",
                        "stops": [{"address": "Secret Address Value"}],
                        "billing": {"total": 9999.99},
                    }
                ],
                "totalCount": 137,
                "page": 1,
                "itemsPerPage": 100,
                "dateRange": {"from": CERTIFICATION_DATE, "to": CERTIFICATION_DATE},
            },
        )

    client = _install_mock_http(monkeypatch, handler)
    try:
        response = TestClient(app).get(
            f"/api/v1/connectors/torqueai/certification?date={CERTIFICATION_DATE}",
            headers=headers,
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert len(calls) == 1
    body = response.json()
    assert body == {
        "status": "certified_response_observed",
        "provider": "torqueai",
        "operation": "external_dispatch_page",
        "http_status": 200,
        "request": {
            "from": CERTIFICATION_DATE,
            "to": CERTIFICATION_DATE,
            "page": 1,
            "limit": 100,
        },
        "total_count": 137,
        "page": 1,
        "items_per_page": 100,
        "rows_returned": 1,
        "pagination_required": True,
        "sample_record_field_types": {
            "billing": "object",
            "customerName": "string",
            "driverName": "string",
            "loadNumber": "number",
            "stops": "array",
        },
        "response_contract_valid": True,
        "tenant_scope_validated": True,
        "raw_dispatches_returned": False,
        "secrets_exposed": False,
    }
    serialized = response.text
    assert TOKEN not in serialized
    assert "Secret Customer Value" not in serialized
    assert "Secret Driver Value" not in serialized
    assert "Secret Address Value" not in serialized
    assert "9999.99" not in serialized


def test_certification_route_fails_closed_for_other_tenant_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _organization, _identity, headers = seed_principal("viewer")
    _configure(monkeypatch, "different-tenant")
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("TorqueAI must not be called for a tenant scope mismatch")

    client = _install_mock_http(monkeypatch, handler)
    try:
        response = TestClient(app).get(
            f"/api/v1/connectors/torqueai/certification?date={CERTIFICATION_DATE}",
            headers=headers,
        )
    finally:
        client.close()

    assert response.status_code == 403
    assert calls == 0
    assert response.json()["detail"] == {
        "status": "failed",
        "provider": "torqueai",
        "error_code": "organization_scope_mismatch",
        "provider_http_status": None,
        "retryable": False,
        "secrets_exposed": False,
    }


def test_certification_route_surfaces_rate_limit_once_without_raw_provider_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization, _identity, headers = seed_principal("viewer")
    _configure(monkeypatch, organization["slug"])
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, text=f"raw provider body {TOKEN} Secret Customer Value")

    client = _install_mock_http(monkeypatch, handler)
    try:
        response = TestClient(app).get(
            f"/api/v1/connectors/torqueai/certification?date={CERTIFICATION_DATE}",
            headers=headers,
        )
    finally:
        client.close()

    assert response.status_code == 502
    assert calls == 1
    assert response.json()["detail"] == {
        "status": "failed",
        "provider": "torqueai",
        "error_code": "rate_limited",
        "provider_http_status": 429,
        "retryable": False,
        "secrets_exposed": False,
    }
    assert TOKEN not in response.text
    assert "Secret Customer Value" not in response.text
