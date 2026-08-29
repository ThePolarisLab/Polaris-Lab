from __future__ import annotations

from datetime import date, timedelta
import logging
from pathlib import Path

import httpx
import pytest

from app.connectors import torqueai
from app.connectors.torqueai import TorqueAIConnector, TorqueAIConnectorError, TorqueAIDispatchPage

TOKEN = "tk_test_secret_must_never_leak"
BASE_URL = "https://morlogistics.kordovatek.com"
ORG_SLUG = "mor-logistics"


@pytest.fixture(autouse=True)
def torqueai_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(torqueai.TORQUEAI_API_TOKEN_ENV, TOKEN)
    monkeypatch.setenv(torqueai.TORQUEAI_BASE_URL_ENV, BASE_URL)
    monkeypatch.setenv(torqueai.TORQUEAI_ORGANIZATION_SLUG_ENV, ORG_SLUG)


def _payload(*, request_from: str = "2026-08-27", request_to: str = "2026-08-27", page: int = 1, limit: int = 100):
    return {
        "data": [
            {
                "loadNumber": 1053,
                "status": "delivered",
                "customerName": "Synthetic Customer",
                "stops": [],
                "billing": {"currency": "cad", "total": 2450.0},
            }
        ],
        "totalCount": 1,
        "page": page,
        "itemsPerPage": limit,
        "dateRange": {"from": request_from, "to": request_to},
    }


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_dispatches_uses_exact_get_bearer_and_explicit_params() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "GET"
        assert request.url.scheme == "https"
        assert request.url.host == "morlogistics.kordovatek.com"
        assert request.url.path == torqueai.TORQUEAI_DISPATCH_PATH
        assert request.url.params == httpx.QueryParams(
            {"from": "2026-08-27", "to": "2026-08-27", "page": "1", "limit": "100"}
        )
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert request.headers["Accept"] == "application/json"
        return httpx.Response(200, json=_payload())

    result = TorqueAIConnector(organization_slug=ORG_SLUG, http_client=_client(handler)).fetch_dispatches(
        date_from=date(2026, 8, 27),
        date_to="2026-08-27",
        page=1,
        limit=100,
    )

    assert isinstance(result, TorqueAIDispatchPage)
    assert result.total_count == 1
    assert result.page == 1
    assert result.items_per_page == 100
    assert result.date_from == date(2026, 8, 27)
    assert result.date_to == date(2026, 8, 27)
    assert result.data[0]["loadNumber"] == 1053
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("date_from", "date_to", "page", "limit"),
    [
        (date(2026, 7, 28), date(2026, 8, 28), 1, 100),
        (date(2026, 8, 28), date(2026, 8, 27), 1, 100),
        (date(2026, 8, 27), date(2026, 8, 27), 0, 100),
        (date(2026, 8, 27), date(2026, 8, 27), True, 100),
        (date(2026, 8, 27), date(2026, 8, 27), 1, 0),
        (date(2026, 8, 27), date(2026, 8, 27), 1, 501),
        (date(2026, 8, 27), date(2026, 8, 27), 1, True),
    ],
)
def test_invalid_request_is_rejected_before_provider_access(date_from, date_to, page, limit) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not be called")

    connector = TorqueAIConnector(organization_slug=ORG_SLUG, http_client=_client(handler))
    with pytest.raises(TorqueAIConnectorError) as exc_info:
        connector.fetch_dispatches(date_from=date_from, date_to=date_to, page=page, limit=limit)

    assert exc_info.value.code == "invalid_request"
    assert calls == 0


def test_exact_31_day_range_is_allowed() -> None:
    request_from = date(2026, 7, 29)
    request_to = request_from + timedelta(days=30)

    def handler(_request: httpx.Request) -> httpx.Response:
        payload = _payload(request_from=request_from.isoformat(), request_to=request_to.isoformat())
        return httpx.Response(200, json=payload)

    result = TorqueAIConnector(organization_slug=ORG_SLUG, http_client=_client(handler)).fetch_dispatches(
        date_from=request_from, date_to=request_to
    )
    assert result.date_from == request_from
    assert result.date_to == request_to


@pytest.mark.parametrize(
    ("base_url", "expected_code"),
    [
        ("", "base_url_missing"),
        ("http://morlogistics.kordovatek.com", "invalid_base_url"),
        ("https://morlogistics.kordovatek.com/company", "invalid_base_url"),
        ("https://user:pass@morlogistics.kordovatek.com", "invalid_base_url"),
        ("https://morlogistics.kordovatek.com?next=evil", "invalid_base_url"),
    ],
)
def test_base_url_must_be_configured_https_origin(monkeypatch: pytest.MonkeyPatch, base_url: str, expected_code: str) -> None:
    monkeypatch.setenv(torqueai.TORQUEAI_BASE_URL_ENV, base_url)
    connector = TorqueAIConnector(organization_slug=ORG_SLUG)
    with pytest.raises(TorqueAIConnectorError) as exc_info:
        connector.fetch_dispatches(date_from="2026-08-27", date_to="2026-08-27")
    assert exc_info.value.code == expected_code


def test_organization_scope_mismatch_fails_before_provider_access() -> None:
    connector = TorqueAIConnector(organization_slug="other-tenant")
    with pytest.raises(TorqueAIConnectorError) as exc_info:
        connector.fetch_dispatches(date_from="2026-08-27", date_to="2026-08-27")
    assert exc_info.value.code == "organization_scope_mismatch"


def test_missing_token_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(torqueai.TORQUEAI_API_TOKEN_ENV)
    connector = TorqueAIConnector(organization_slug=ORG_SLUG)
    with pytest.raises(TorqueAIConnectorError) as exc_info:
        connector.fetch_dispatches(date_from="2026-08-27", date_to="2026-08-27")
    assert exc_info.value.code == "token_missing"
    assert TOKEN not in str(exc_info.value)


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "provider_bad_request"),
        (401, "authorization_required"),
        (403, "permission_denied"),
        (405, "method_not_allowed"),
        (429, "rate_limited"),
        (500, "provider_unavailable"),
        (503, "provider_unexpected_status"),
    ],
)
def test_provider_statuses_are_sanitized_and_never_retried(status: int, code: str) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, text=f"provider raw body contains {TOKEN}")

    connector = TorqueAIConnector(organization_slug=ORG_SLUG, http_client=_client(handler))
    with pytest.raises(TorqueAIConnectorError) as exc_info:
        connector.fetch_dispatches(date_from="2026-08-27", date_to="2026-08-27")

    assert exc_info.value.code == code
    assert exc_info.value.http_status == status
    assert exc_info.value.retryable is False
    assert TOKEN not in str(exc_info.value)
    assert calls == 1


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: [],
        lambda p: {**p, "data": {}},
        lambda p: {**p, "data": ["not-an-object"]},
        lambda p: {**p, "totalCount": -1},
        lambda p: {**p, "totalCount": True},
        lambda p: {**p, "page": 2},
        lambda p: {**p, "itemsPerPage": 0},
        lambda p: {**p, "itemsPerPage": 101},
        lambda p: {**p, "dateRange": None},
        lambda p: {**p, "dateRange": {"from": "2026-08-26", "to": "2026-08-27"}},
        lambda p: {**p, "totalCount": 0},
    ],
)
def test_malformed_envelopes_fail_closed(mutate) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mutate(_payload()))

    connector = TorqueAIConnector(organization_slug=ORG_SLUG, http_client=_client(handler))
    with pytest.raises(TorqueAIConnectorError) as exc_info:
        connector.fetch_dispatches(date_from="2026-08-27", date_to="2026-08-27")
    assert exc_info.value.code == "provider_contract_error"
    assert TOKEN not in str(exc_info.value)


def test_pagination_contract_accepts_valid_second_page() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        payload = {
            "data": [{"loadNumber": number} for number in range(101, 138)],
            "totalCount": 137,
            "page": 2,
            "itemsPerPage": 100,
            "dateRange": {"from": "2026-08-27", "to": "2026-08-27"},
        }
        return httpx.Response(200, json=payload)

    result = TorqueAIConnector(organization_slug=ORG_SLUG, http_client=_client(handler)).fetch_dispatches(
        date_from="2026-08-27", date_to="2026-08-27", page=2, limit=100
    )
    assert result.total_count == 137
    assert len(result.data) == 37


def test_secret_never_appears_in_connector_logs(caplog: pytest.LogCaptureFixture) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text=TOKEN)

    caplog.set_level(logging.INFO)
    connector = TorqueAIConnector(organization_slug=ORG_SLUG, http_client=_client(handler))
    with pytest.raises(TorqueAIConnectorError):
        connector.fetch_dispatches(date_from="2026-08-27", date_to="2026-08-27")

    assert TOKEN not in caplog.text
    assert "Authorization" not in caplog.text


def test_connector_surface_has_no_database_write_dependency() -> None:
    source = Path(torqueai.__file__).read_text(encoding="utf-8")
    assert "sqlalchemy" not in source.lower()
    assert ".commit(" not in source
    assert ".add(" not in source


def test_frontend_does_not_contain_torqueai_secret_name() -> None:
    frontend = Path(__file__).resolve().parents[2] / "frontend"
    for path in frontend.rglob("*"):
        if path.is_file() and path.suffix in {".js", ".jsx", ".ts", ".tsx", ".html"}:
            assert torqueai.TORQUEAI_API_TOKEN_ENV not in path.read_text(encoding="utf-8", errors="ignore")
