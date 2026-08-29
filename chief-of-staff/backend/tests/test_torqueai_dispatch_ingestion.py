from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.connectors import torqueai
from app.connectors.torqueai import TorqueAIConnector
from app.database.database import SessionLocal
from app.main import app
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchSyncRun, TorqueAIDispatchSyncState
from tests.auth_helpers import seed_principal

TOKEN = "tk_ingestion_test_secret"
BASE_URL = "https://morlogistics.kordovatek.com"
DATE = "2026-08-27"


def _configure(monkeypatch: pytest.MonkeyPatch, organization_slug: str) -> None:
    monkeypatch.setenv(torqueai.TORQUEAI_API_TOKEN_ENV, TOKEN)
    monkeypatch.setenv(torqueai.TORQUEAI_BASE_URL_ENV, BASE_URL)
    monkeypatch.setenv(torqueai.TORQUEAI_ORGANIZATION_SLUG_ENV, organization_slug)


def _install_mock_http(monkeypatch: pytest.MonkeyPatch, handler) -> httpx.Client:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(TorqueAIConnector, "_http", lambda _self: client)
    return client


def _dispatch(load_number: int, order_number: str, *, status: str = "delivered") -> dict:
    return {
        "loadNumber": load_number,
        "orderNumber": order_number,
        "status": status,
        "orderDate": "2026-08-25",
        "shipDate": "2026-08-27",
        "deliveryDate": "2026-08-28",
        "customerName": "Sensitive Customer",
        "dispatcherName": "Sensitive Dispatcher",
        "driverName": "Sensitive Driver",
        "carrierName": "Sensitive Carrier",
        "truckNumber": "T-100",
        "trailerNumber": "R-200",
        "loadedMiles": 612.5,
        "currency": "CAD",
        "totalCharge": 9999.99,
        "stops": [{"address": "Sensitive Address"}],
        "billing": {"total": 9999.99},
    }


def _payload(data: list[dict], *, total: int | None = None, page: int = 1, request_from: str = DATE, request_to: str = DATE) -> dict:
    return {
        "data": data,
        "totalCount": len(data) if total is None else total,
        "page": page,
        "itemsPerPage": 100,
        "dateRange": {"from": request_from, "to": request_to},
    }


def _post(headers: dict[str, str], *, date_from: str = DATE, date_to: str = DATE):
    return TestClient(app).post(
        "/api/v1/connectors/torqueai/dispatches/ingest",
        headers=headers,
        json={"from": date_from, "to": date_to},
    )


def test_manual_ingestion_persists_only_approved_fields_and_returns_metadata_only(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, headers = seed_principal("owner")
    _configure(monkeypatch, organization["slug"])
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "GET"
        assert request.url.path == torqueai.TORQUEAI_DISPATCH_PATH
        assert request.url.params == httpx.QueryParams({"from": DATE, "to": DATE, "page": "1", "limit": "100"})
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        return httpx.Response(200, json=_payload([_dispatch(1053, "ORD-1053")]))

    client = _install_mock_http(monkeypatch, handler)
    try:
        response = _post(headers)
    finally:
        client.close()

    assert response.status_code == 200
    assert len(calls) == 1
    assert response.json() == {
        "status": "success",
        "provider": "torqueai",
        "request": {"from": DATE, "to": DATE},
        "pages_fetched": 1,
        "provider_total_count": 1,
        "rows_validated": 1,
        "rows_inserted": 1,
        "rows_updated": 0,
        "rows_unchanged": 0,
        "tenant_scope_validated": True,
        "raw_dispatches_returned": False,
        "secrets_exposed": False,
    }
    assert TOKEN not in response.text
    assert "Sensitive Customer" not in response.text
    assert "Sensitive Driver" not in response.text
    assert "Sensitive Address" not in response.text
    assert "9999.99" not in response.text

    session = SessionLocal()
    try:
        row = session.query(TorqueAIDispatch).filter(TorqueAIDispatch.organization_id == organization["id"]).one()
        assert row.provider_load_number == "1053"
        assert row.provider_order_number == "ORD-1053"
        assert row.status == "delivered"
        assert row.customer_name == "Sensitive Customer"
        assert row.driver_name == "Sensitive Driver"
        assert str(row.loaded_miles) == "612.5000"
        assert len(row.source_fingerprint) == 64
        run = session.query(TorqueAIDispatchSyncRun).filter(TorqueAIDispatchSyncRun.organization_id == organization["id"]).one()
        assert run.status == "success"
        assert run.rows_inserted == 1
        state = session.query(TorqueAIDispatchSyncState).filter(TorqueAIDispatchSyncState.organization_id == organization["id"]).one()
        assert state.last_successful_window_start.isoformat() == DATE
        assert state.last_successful_window_end.isoformat() == DATE
    finally:
        session.close()

    columns = set(TorqueAIDispatch.__table__.columns.keys())
    assert "billing" not in columns
    assert "total_charge" not in columns
    assert "totalCharge" not in columns
    assert "stops" not in columns
    assert "currency" not in columns


def test_viewer_cannot_ingest_and_provider_is_not_called(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, headers = seed_principal("viewer")
    _configure(monkeypatch, organization["slug"])
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not be called")

    client = _install_mock_http(monkeypatch, handler)
    try:
        response = _post(headers)
    finally:
        client.close()
    assert response.status_code == 403
    assert calls == 0


def test_tenant_mismatch_fails_before_provider_access(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, headers = seed_principal("owner")
    _configure(monkeypatch, "different-tenant")
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not be called")

    client = _install_mock_http(monkeypatch, handler)
    try:
        response = _post(headers)
    finally:
        client.close()
    assert response.status_code == 403
    assert calls == 0
    assert response.json()["detail"]["error_code"] == "organization_scope_mismatch"
    session = SessionLocal()
    try:
        assert session.query(TorqueAIDispatch).filter(TorqueAIDispatch.organization_id == organization["id"]).count() == 0
    finally:
        session.close()


def test_window_over_seven_days_fails_before_provider_access(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, headers = seed_principal("owner")
    _configure(monkeypatch, organization["slug"])
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not be called")

    client = _install_mock_http(monkeypatch, handler)
    try:
        response = _post(headers, date_from="2026-08-20", date_to="2026-08-27")
    finally:
        client.close()
    assert response.status_code == 422
    assert calls == 0
    assert response.json()["detail"]["error_code"] == "invalid_request"


def test_bound_exceeded_stops_after_page_one_and_writes_no_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, headers = seed_principal("owner")
    _configure(monkeypatch, organization["slug"])
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.params["page"] == "1"
        data = [_dispatch(2000 + index, f"ORD-{2000 + index}") for index in range(100)]
        return httpx.Response(200, json=_payload(data, total=1001))

    client = _install_mock_http(monkeypatch, handler)
    try:
        response = _post(headers)
    finally:
        client.close()
    assert response.status_code == 422
    assert response.json()["detail"]["error_code"] == "ingestion_bound_exceeded"
    assert calls == 1
    session = SessionLocal()
    try:
        assert session.query(TorqueAIDispatch).filter(TorqueAIDispatch.organization_id == organization["id"]).count() == 0
    finally:
        session.close()


def test_malformed_second_page_causes_zero_dispatch_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, headers = seed_principal("owner")
    _configure(monkeypatch, organization["slug"])
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        calls.append(page)
        if page == 1:
            data = [_dispatch(3000 + index, f"ORD-{3000 + index}") for index in range(100)]
            return httpx.Response(200, json=_payload(data, total=101, page=1))
        return httpx.Response(200, json=_payload([_dispatch(3100, "ORD-3100")], total=101, page=2, request_from="2026-08-26"))

    client = _install_mock_http(monkeypatch, handler)
    try:
        response = _post(headers)
    finally:
        client.close()
    assert response.status_code == 502
    assert response.json()["detail"]["error_code"] == "provider_contract_error"
    assert calls == [1, 2]
    session = SessionLocal()
    try:
        assert session.query(TorqueAIDispatch).filter(TorqueAIDispatch.organization_id == organization["id"]).count() == 0
    finally:
        session.close()


def test_duplicate_identity_fails_closed_before_dispatch_write(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, headers = seed_principal("owner")
    _configure(monkeypatch, organization["slug"])

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_payload([_dispatch(4001, "ORD-4001"), _dispatch(4001, "ORD-4001")], total=2))

    client = _install_mock_http(monkeypatch, handler)
    try:
        response = _post(headers)
    finally:
        client.close()
    assert response.status_code == 502
    assert response.json()["detail"]["error_code"] == "provider_duplicate_identity"
    session = SessionLocal()
    try:
        assert session.query(TorqueAIDispatch).filter(TorqueAIDispatch.organization_id == organization["id"]).count() == 0
    finally:
        session.close()


def test_repeated_ingestion_is_idempotent_and_changed_record_preserves_first_observed(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, headers = seed_principal("owner")
    _configure(monkeypatch, organization["slug"])
    current_status = {"value": "dispatched"}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_payload([_dispatch(5001, "ORD-5001", status=current_status["value"])]))

    client = _install_mock_http(monkeypatch, handler)
    try:
        first = _post(headers)
        second = _post(headers)
        session = SessionLocal()
        try:
            row = session.query(TorqueAIDispatch).filter(TorqueAIDispatch.organization_id == organization["id"]).one()
            first_observed = row.first_observed_at
            initial_fingerprint = row.source_fingerprint
        finally:
            session.close()
        current_status["value"] = "delivered"
        third = _post(headers)
    finally:
        client.close()

    assert first.status_code == 200 and first.json()["rows_inserted"] == 1
    assert second.status_code == 200 and second.json()["rows_unchanged"] == 1
    assert third.status_code == 200 and third.json()["rows_updated"] == 1
    session = SessionLocal()
    try:
        row = session.query(TorqueAIDispatch).filter(TorqueAIDispatch.organization_id == organization["id"]).one()
        assert row.first_observed_at == first_observed
        assert row.status == "delivered"
        assert row.source_fingerprint != initial_fingerprint
        assert session.query(TorqueAIDispatch).filter(TorqueAIDispatch.organization_id == organization["id"]).count() == 1
        runs = session.query(TorqueAIDispatchSyncRun).filter(TorqueAIDispatchSyncRun.organization_id == organization["id"]).all()
        assert len(runs) == 3
        assert all(run.status == "success" for run in runs)
    finally:
        session.close()
