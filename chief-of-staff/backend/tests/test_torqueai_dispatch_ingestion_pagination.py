from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.connectors import torqueai
from app.connectors.torqueai import TorqueAIConnector
from app.database.database import SessionLocal
from app.main import app
from app.models.torqueai import TorqueAIDispatch
from tests.auth_helpers import seed_principal

TOKEN = "tk_ingestion_pagination_secret"
BASE_URL = "https://morlogistics.kordovatek.com"
DATE = "2026-08-27"


def _configure(monkeypatch: pytest.MonkeyPatch, slug: str) -> None:
    monkeypatch.setenv(torqueai.TORQUEAI_API_TOKEN_ENV, TOKEN)
    monkeypatch.setenv(torqueai.TORQUEAI_BASE_URL_ENV, BASE_URL)
    monkeypatch.setenv(torqueai.TORQUEAI_ORGANIZATION_SLUG_ENV, slug)


def _install(monkeypatch: pytest.MonkeyPatch, handler) -> httpx.Client:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(TorqueAIConnector, "_http", lambda _self: client)
    return client


def _dispatch(number: int) -> dict:
    return {
        "loadNumber": number,
        "orderNumber": f"ORD-{number}",
        "status": "dispatched",
        "shipDate": DATE,
        "loadedMiles": 100,
    }


def _payload(data: list[dict], *, total: int, page: int) -> dict:
    return {
        "data": data,
        "totalCount": total,
        "page": page,
        "itemsPerPage": 100,
        "dateRange": {"from": DATE, "to": DATE},
    }


def _post(headers: dict[str, str]):
    return TestClient(app).post(
        "/api/v1/connectors/torqueai/dispatches/ingest",
        headers=headers,
        json={"from": DATE, "to": DATE},
    )


def test_successful_two_page_ingestion_is_sequential_and_stops_at_total(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, headers = seed_principal("owner")
    _configure(monkeypatch, organization["slug"])
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        calls.append(page)
        assert request.url.params["limit"] == "100"
        if page == 1:
            return httpx.Response(200, json=_payload([_dispatch(6000 + i) for i in range(100)], total=101, page=1))
        if page == 2:
            return httpx.Response(200, json=_payload([_dispatch(6100)], total=101, page=2))
        raise AssertionError("ingestion requested a page beyond the validated total")

    client = _install(monkeypatch, handler)
    try:
        response = _post(headers)
    finally:
        client.close()

    assert response.status_code == 200
    assert calls == [1, 2]
    body = response.json()
    assert body["pages_fetched"] == 2
    assert body["provider_total_count"] == 101
    assert body["rows_validated"] == 101
    assert body["rows_inserted"] == 101
    session = SessionLocal()
    try:
        assert session.query(TorqueAIDispatch).filter(TorqueAIDispatch.organization_id == organization["id"]).count() == 101
    finally:
        session.close()


def test_missing_provider_identity_causes_zero_dispatch_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, headers = seed_principal("owner")
    _configure(monkeypatch, organization["slug"])

    def handler(_request: httpx.Request) -> httpx.Response:
        bad = {"loadNumber": 7001, "status": "dispatched", "shipDate": DATE}
        return httpx.Response(200, json=_payload([bad], total=1, page=1))

    client = _install(monkeypatch, handler)
    try:
        response = _post(headers)
    finally:
        client.close()

    assert response.status_code == 502
    assert response.json()["detail"]["error_code"] == "provider_contract_error"
    session = SessionLocal()
    try:
        assert session.query(TorqueAIDispatch).filter(TorqueAIDispatch.organization_id == organization["id"]).count() == 0
    finally:
        session.close()


def test_rate_limit_is_not_retried_and_writes_no_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, headers = seed_principal("owner")
    _configure(monkeypatch, organization["slug"])
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, text=f"raw body {TOKEN} customer-secret")

    client = _install(monkeypatch, handler)
    try:
        response = _post(headers)
    finally:
        client.close()

    assert response.status_code == 502
    assert calls == 1
    assert response.json()["detail"]["error_code"] == "rate_limited"
    assert TOKEN not in response.text
    assert "customer-secret" not in response.text
    session = SessionLocal()
    try:
        assert session.query(TorqueAIDispatch).filter(TorqueAIDispatch.organization_id == organization["id"]).count() == 0
    finally:
        session.close()
