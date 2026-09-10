from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.connectors import torqueai
from app.connectors.torqueai import TorqueAIConnector
from app.main import app
from tests.auth_helpers import seed_principal

TOKEN = "tk_schema_cert_test_secret"
BASE_URL = "https://morlogistics.kordovatek.com"
DAY = "2026-09-10"


def _configure(monkeypatch: pytest.MonkeyPatch, organization_slug: str) -> None:
    monkeypatch.setenv(torqueai.TORQUEAI_API_TOKEN_ENV, TOKEN)
    monkeypatch.setenv(torqueai.TORQUEAI_BASE_URL_ENV, BASE_URL)
    monkeypatch.setenv(torqueai.TORQUEAI_ORGANIZATION_SLUG_ENV, organization_slug)


def _install(monkeypatch: pytest.MonkeyPatch, handler) -> httpx.Client:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(TorqueAIConnector, "_http", lambda _self: client)
    return client


def test_schema_certification_returns_nested_paths_and_never_values(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, headers = seed_principal("viewer")
    _configure(monkeypatch, organization["slug"])
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.method == "GET"
        assert request.url.path == torqueai.TORQUEAI_DISPATCH_PATH
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        return httpx.Response(
            200,
            json={
                "data": [{
                    "loadNumber": 1,
                    "customerName": "Secret Customer",
                    "stops": [
                        {"address": "Secret A", "city": "Winnipeg", "window": {"from": "08:00", "to": "10:00"}},
                        {"address": "Secret B", "province": "MB"},
                    ],
                    "billing": {"total": 9999.99},
                }],
                "totalCount": 1,
                "page": 1,
                "itemsPerPage": 100,
                "dateRange": {"from": DAY, "to": DAY},
            },
        )

    client = _install(monkeypatch, handler)
    try:
        response = TestClient(app).get(
            f"/api/v1/connectors/torqueai/schema-certification?date={DAY}",
            headers=headers,
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert calls == 1
    body = response.json()
    assert body["status"] == "certified_schema_observed"
    assert body["observed_schema_paths"]["stops"] == "array"
    assert body["observed_schema_paths"]["stops[]"] == "object"
    assert body["observed_schema_paths"]["stops[].address"] == "string"
    assert body["observed_schema_paths"]["stops[].city"] == "string"
    assert body["observed_schema_paths"]["stops[].province"] == "string"
    assert body["observed_schema_paths"]["stops[].window.from"] == "string"
    assert body["observed_schema_paths"]["billing.total"] == "number"
    assert body["schema_values_returned"] is False
    assert body["raw_dispatches_returned"] is False
    assert body["tenant_scope_validated"] is True
    assert body["secrets_exposed"] is False

    serialized = response.text
    for value in (TOKEN, "Secret Customer", "Secret A", "Secret B", "Winnipeg", "MB", "08:00", "10:00", "9999.99"):
        assert value not in serialized


def test_schema_certification_fails_closed_on_tenant_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    _organization, _identity, headers = seed_principal("viewer")
    _configure(monkeypatch, "different-tenant")
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not be called")

    client = _install(monkeypatch, handler)
    try:
        response = TestClient(app).get(
            f"/api/v1/connectors/torqueai/schema-certification?date={DAY}",
            headers=headers,
        )
    finally:
        client.close()

    assert response.status_code == 403
    assert calls == 0
    assert response.json()["detail"]["error_code"] == "organization_scope_mismatch"
