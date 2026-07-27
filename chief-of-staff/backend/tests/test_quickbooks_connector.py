import json
from io import BytesIO

from app.connectors.models import ConnectorStatus
from app.connectors.quickbooks import QuickBooksConnector


class FakeResponse:
    def __init__(self, payload):
        self._body = BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body.read()


def configure(monkeypatch):
    monkeypatch.setenv("POLARIS_QBO_CLIENT_ID", "client-id")
    monkeypatch.setenv("POLARIS_QBO_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("POLARIS_QBO_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("POLARIS_QBO_REALM_ID", "realm-id")


def test_health_is_configuration_error_without_secrets(monkeypatch):
    for name in (
        "POLARIS_QBO_CLIENT_ID",
        "POLARIS_QBO_CLIENT_SECRET",
        "POLARIS_QBO_REFRESH_TOKEN",
        "POLARIS_QBO_REALM_ID",
    ):
        monkeypatch.delenv(name, raising=False)

    health = QuickBooksConnector().health()

    assert health.name == "quickbooks"
    assert health.status == ConnectorStatus.CONFIGURATION_ERROR
    assert "POLARIS_QBO_CLIENT_ID" in health.message


def test_health_verifies_expected_company_without_exposing_secrets(monkeypatch):
    configure(monkeypatch)
    responses = iter(
        [
            FakeResponse({"access_token": "access-token", "expires_in": 3600}),
            FakeResponse(
                {"CompanyInfo": {"CompanyName": "MOR LOGISTICS MANITOBA LIMITED"}}
            ),
        ]
    )
    connector = QuickBooksConnector(opener=lambda *_args, **_kwargs: next(responses))

    health = connector.health()

    assert health.status == ConnectorStatus.HEALTHY
    assert health.details["company_name"] == "MOR LOGISTICS MANITOBA LIMITED"
    assert health.details["read_only"] is True
    assert health.details["secrets_exposed"] is False
    assert "access-token" not in health.model_dump_json()
    assert "refresh-token" not in health.model_dump_json()


def test_sync_reads_company_and_records_last_sync(monkeypatch):
    configure(monkeypatch)
    responses = iter(
        [
            FakeResponse({"access_token": "access-token", "expires_in": 3600}),
            FakeResponse(
                {"CompanyInfo": {"CompanyName": "MOR LOGISTICS MANITOBA LIMITED"}}
            ),
        ]
    )
    connector = QuickBooksConnector(opener=lambda *_args, **_kwargs: next(responses))

    result = connector.sync()

    assert result.success is True
    assert result.records_read == 1
    assert result.records_written == 0
    assert result.errors == []


def test_company_mismatch_is_rejected(monkeypatch):
    configure(monkeypatch)
    responses = iter(
        [
            FakeResponse({"access_token": "access-token", "expires_in": 3600}),
            FakeResponse({"CompanyInfo": {"CompanyName": "WRONG COMPANY"}}),
        ]
    )
    connector = QuickBooksConnector(opener=lambda *_args, **_kwargs: next(responses))

    health = connector.health()

    assert health.status == ConnectorStatus.AUTHENTICATION_ERROR
    assert health.details["expected_company"] == "MOR LOGISTICS MANITOBA LIMITED"
