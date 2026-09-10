from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.connectors import torqueai
from app.connectors.torqueai import TorqueAIConnector
from app.connectors.torqueai_schema import dispatch_stop_job_values
from app.main import app
from app.security.job_auth import sign_job_request

TRIGGER_SECRET_ENV = "POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET"
TRIGGER_SECRET = "torqueai-stop-job-certification-test-secret"
TOKEN = "tk_stop_job_cert_test_secret"
BASE_URL = "https://morlogistics.kordovatek.com"
ORGANIZATION_SLUG = "mor-logistics"
DAY = "2026-09-09"
PATH = "/api/v1/internal/torqueai/stop-job-certification"


def _signed_headers(*, body: bytes = b"") -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        "X-Polaris-Job-Timestamp": timestamp,
        "X-Polaris-Job-Signature": sign_job_request(
            method="POST",
            path=PATH,
            body=body,
            timestamp=timestamp,
            secret=TRIGGER_SECRET,
        ),
    }


def _configure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TRIGGER_SECRET_ENV, TRIGGER_SECRET)
    monkeypatch.setenv(torqueai.TORQUEAI_API_TOKEN_ENV, TOKEN)
    monkeypatch.setenv(torqueai.TORQUEAI_BASE_URL_ENV, BASE_URL)
    monkeypatch.setenv(torqueai.TORQUEAI_ORGANIZATION_SLUG_ENV, ORGANIZATION_SLUG)


def _install(monkeypatch: pytest.MonkeyPatch, handler) -> httpx.Client:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(TorqueAIConnector, "_http", lambda _self: client)
    return client


def test_stop_job_value_observer_returns_only_distinct_safe_categories() -> None:
    records = (
        {"loadNumber": 1, "stops": [{"job": "Pickup", "city": "Winnipeg"}, {"job": "Delivery"}]},
        {"loadNumber": 2, "stops": [{"job": " Pickup "}, {"job": None}, {"city": "Laredo"}]},
    )

    assert dispatch_stop_job_values(records) == ("Delivery", "Pickup")


def test_stop_job_value_observer_fails_closed_for_free_text_or_wrong_type() -> None:
    with pytest.raises(ValueError, match="safe categorical"):
        dispatch_stop_job_values(({"stops": [{"job": "Pickup at Secret Customer, 123 Main Street"}]},))

    with pytest.raises(ValueError, match="not a string"):
        dispatch_stop_job_values(({"stops": [{"job": 1}]},))


def test_machine_stop_job_certification_returns_only_job_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch)
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
                "data": [
                    {
                        "loadNumber": 101,
                        "customerName": "Secret Customer",
                        "stops": [
                            {"job": "Pickup", "address": "Secret Winnipeg Address", "city": "Winnipeg"},
                            {"job": "Delivery", "address": "Secret Laredo Address", "city": "Laredo"},
                        ],
                    },
                    {"loadNumber": 102, "stops": [{"job": "Pickup"}]},
                ],
                "totalCount": 2,
                "page": 1,
                "itemsPerPage": 100,
                "dateRange": {"from": DAY, "to": DAY},
            },
        )

    client = _install(monkeypatch, handler)
    try:
        response = TestClient(app).post(f"{PATH}?date={DAY}", headers=_signed_headers())
    finally:
        client.close()

    assert response.status_code == 200
    assert calls == 1
    payload = response.json()
    assert payload["status"] == "certified_categorical_values_observed"
    assert payload["provider"] == "torqueai"
    assert payload["operation"] == "external_dispatch_stop_job_values"
    assert payload["certified_field"] == "stops[].job"
    assert payload["observed_job_values"] == ["Delivery", "Pickup"]
    assert payload["only_certified_field_values_returned"] is True
    assert payload["raw_dispatches_returned"] is False
    assert payload["secrets_exposed"] is False

    serialized = response.text
    for forbidden in (
        TOKEN,
        "Secret Customer",
        "Secret Winnipeg Address",
        "Secret Laredo Address",
        "Winnipeg",
        "Laredo",
        "loadNumber",
        "customerName",
        "address",
        "city",
    ):
        assert forbidden not in serialized


def test_machine_stop_job_certification_is_hmac_only_and_bodyless(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch)
    provider_calls = 0

    def forbidden_provider_call(*_args, **_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("provider must not be called")

    monkeypatch.setattr(TorqueAIConnector, "fetch_dispatches", forbidden_provider_call)
    client = TestClient(app)

    assert client.post(f"{PATH}?date={DAY}").status_code == 401

    body = b'{"include_locations":true}'
    rejected = client.post(f"{PATH}?date={DAY}", headers=_signed_headers(body=body), content=body)
    assert rejected.status_code == 400
    assert "include_locations" not in rejected.text
    assert provider_calls == 0


def test_machine_stop_job_certification_fails_closed_for_unsafe_category(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [{"loadNumber": 1, "stops": [{"job": "Pickup at Secret Customer, 123 Main Street"}]}],
                "totalCount": 1,
                "page": 1,
                "itemsPerPage": 100,
                "dateRange": {"from": DAY, "to": DAY},
            },
        )

    client = _install(monkeypatch, handler)
    try:
        response = TestClient(app).post(f"{PATH}?date={DAY}", headers=_signed_headers())
    finally:
        client.close()

    assert response.status_code == 502
    assert response.json()["detail"]["error_code"] == "unsafe_stop_job_category_shape"
    assert "Secret Customer" not in response.text
    assert "Main Street" not in response.text


def test_stop_job_certification_workflow_is_manual_narrow_and_secret_safe() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workflow = (repo_root / ".github" / "workflows" / "torqueai-stop-job-certification.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert PATH in workflow
    assert "/api/external/dispatches" not in workflow
    assert "POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET" in workflow
    assert "POLARIS_PRODUCTION_API_URL" in workflow
    assert "POLARIS_TORQUEAI_API_TOKEN" not in workflow
    assert "POLARIS_TORQUEAI_BASE_URL" not in workflow
    assert "POLARIS_TORQUEAI_ORGANIZATION_SLUG" not in workflow
    assert 'payload.get("certified_field") != "stops[].job"' in workflow
    assert 'payload.get("only_certified_field_values_returned") is not True' in workflow
    assert 'payload.get("raw_dispatches_returned") is not False' in workflow
    assert 'payload.get("secrets_exposed") is not False' in workflow
