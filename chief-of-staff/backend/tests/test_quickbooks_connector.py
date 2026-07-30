import json
import threading

import httpx

from app.connectors.models import ConnectorStatus
from app.connectors.quickbooks import QuickBooksConnector, QuickBooksConnectorError


class FakeCredentialStore:
    def __init__(self):
        self.organization_id = "org-1"
        self.realm_id = "realm-id"
        self.refresh_token = "refresh-token"
        self.saved = []
        self.metadata_values = {
            "authorized": True,
            "verification_status": "unverified",
            "connector_health_status": "connected_unverified",
            "reauthorization_required": False,
        }
        self.refresh_failures = []
        self.sync_failures = []

    def load(self):
        return self.realm_id, self.refresh_token

    def load_credential(self):
        from app.connectors.quickbooks_credentials import StoredQuickBooksCredential

        return StoredQuickBooksCredential(
            organization_id=self.organization_id,
            realm_id=self.realm_id,
            refresh_token=self.refresh_token,
            scopes="com.intuit.quickbooks.accounting",
            verified_company_name=self.metadata_values.get("verified_company_name"),
            company_verified_at=None,
            verification_status=str(self.metadata_values.get("verification_status")),
            connector_health_status=str(self.metadata_values.get("connector_health_status")),
            reauthorization_required=bool(self.metadata_values.get("reauthorization_required")),
            last_error_summary=self.metadata_values.get("last_error_summary"),
            last_successful_sync_at=None,
            last_refresh_at=None,
            last_refresh_status=self.metadata_values.get("last_refresh_status"),
        )

    def save(self, **kwargs):
        self.saved.append(kwargs)
        self.realm_id = kwargs["realm_id"]
        self.refresh_token = kwargs["refresh_token"]

    def rotate_refresh_token(self, **kwargs):
        self.saved.append(kwargs)
        self.realm_id = kwargs["realm_id"]
        self.refresh_token = kwargs["refresh_token"]
        self.metadata_values["last_refresh_status"] = "success"

    def record_refresh_failure(self, message, *, reauthorization_required=False):
        self.refresh_failures.append(message)
        self.metadata_values["last_refresh_status"] = "failed"
        self.metadata_values["reauthorization_required"] = reauthorization_required

    def record_verification(self, *, status, company_name=None, error_summary=None):
        self.metadata_values["verification_status"] = status
        self.metadata_values["connector_health_status"] = status
        self.metadata_values["verified_company_name"] = company_name
        self.metadata_values["last_error_summary"] = error_summary

    def record_sync_success(self):
        self.metadata_values["last_successful_sync_at"] = "2026-07-30T12:00:00+00:00"

    def record_sync_failure(self, message, *, status="synchronization_failed"):
        self.sync_failures.append(message)
        self.metadata_values["connector_health_status"] = status
        self.metadata_values["last_error_summary"] = message

    def metadata(self):
        return dict(self.metadata_values, authorized=True)


def configure(monkeypatch):
    monkeypatch.setenv("POLARIS_ENV", "test")
    monkeypatch.setenv("POLARIS_QBO_CLIENT_ID", "client-id")
    monkeypatch.setenv("POLARIS_QBO_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("POLARIS_QBO_TOKEN_ENCRYPTION_KEY", "configured-for-test")
    monkeypatch.setenv("POLARIS_QBO_RETRY_BASE_SECONDS", "0")


def json_response(payload, status_code=200):
    return httpx.Response(status_code, json=payload)


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://quickbooks.api.intuit.com")


def test_health_is_configuration_error_without_secrets(monkeypatch):
    for name in (
        "POLARIS_QBO_CLIENT_ID",
        "POLARIS_QBO_CLIENT_SECRET",
        "POLARIS_QBO_TOKEN_ENCRYPTION_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    health = QuickBooksConnector(credential_store=FakeCredentialStore()).health()

    assert health.name == "quickbooks"
    assert health.status == ConnectorStatus.NOT_CONFIGURED
    assert "POLARIS_QBO_CLIENT_ID" in health.message


def test_health_verifies_normalized_company_without_exposing_secrets(monkeypatch):
    configure(monkeypatch)
    store = FakeCredentialStore()
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if "tokens/bearer" in str(request.url):
            return json_response({"access_token": "access-token", "refresh_token": "rotated-refresh-token", "expires_in": 3600})
        return json_response({"CompanyInfo": {"CompanyName": "  mor   logistics manitoba limited  "}})

    connector = QuickBooksConnector(http_client=client_for(handler), credential_store=store)

    health = connector.health()

    assert health.status == ConnectorStatus.HEALTHY
    assert health.details["verified_company_name"] == "mor   logistics manitoba limited"
    assert health.details["read_only"] is True
    assert health.details["secrets_exposed"] is False
    assert "access-token" not in health.model_dump_json()
    assert "refresh-token" not in health.model_dump_json()
    assert store.refresh_token == "rotated-refresh-token"


def test_company_mismatch_is_rejected(monkeypatch):
    configure(monkeypatch)

    def handler(request):
        if "tokens/bearer" in str(request.url):
            return json_response({"access_token": "access-token", "expires_in": 3600})
        return json_response({"CompanyInfo": {"CompanyName": "WRONG COMPANY"}})

    connector = QuickBooksConnector(http_client=client_for(handler), credential_store=FakeCredentialStore())

    health = connector.health()

    assert health.status == ConnectorStatus.COMPANY_MISMATCH
    assert health.details["expected_company_name"] == "MOR LOGISTICS MANITOBA LIMITED"


def test_list_resource_paginates_and_preserves_decimal_strings(monkeypatch):
    configure(monkeypatch)

    def handler(request):
        url = str(request.url)
        if "tokens/bearer" in url:
            return json_response({"access_token": "access-token", "expires_in": 3600})
        normalized_url = url.lower()
        assert "maxresults+2" in normalized_url or "maxresults%202" in normalized_url
        return json_response({"QueryResponse": {"Invoice": [{"Id": "1", "TotalAmt": 10.25}, {"Id": "2", "TotalAmt": "20.50"}]}})

    connector = QuickBooksConnector(http_client=client_for(handler), credential_store=FakeCredentialStore())

    records, next_cursor = connector.list_resource_page("invoices", limit=2)

    assert records[0]["TotalAmt"] == "10.25"
    assert records[1]["TotalAmt"] == "20.50"
    assert next_cursor == 3


def test_all_required_reports_are_supported(monkeypatch):
    configure(monkeypatch)
    requested = []

    def handler(request):
        url = str(request.url)
        if "tokens/bearer" in url:
            return json_response({"access_token": "access-token", "expires_in": 3600})
        requested.append(url)
        return json_response({"Header": {"ReportName": "ok"}, "Rows": {"Row": []}})

    connector = QuickBooksConnector(http_client=client_for(handler), credential_store=FakeCredentialStore())

    for report in ("profit_loss", "balance_sheet", "cash_flow", "aged_receivables", "aged_payables"):
        assert connector.report(report)["Header"]["ReportName"] == "ok"

    assert any("ProfitAndLoss" in url for url in requested)
    assert any("AgedReceivables" in url for url in requested)
    assert any("AgedPayables" in url for url in requested)


def test_malformed_refresh_does_not_overwrite_valid_refresh_token(monkeypatch):
    configure(monkeypatch)
    store = FakeCredentialStore()

    def handler(request):
        return json_response({"refresh_token": "incomplete-token"})

    connector = QuickBooksConnector(http_client=client_for(handler), credential_store=store)

    with pytest_raises(QuickBooksConnectorError):
        connector.company_info()

    assert store.refresh_token == "refresh-token"
    assert store.saved == []
    assert store.metadata_values["last_refresh_status"] == "failed"


def test_revoked_refresh_sets_reauthorization_required(monkeypatch):
    configure(monkeypatch)
    store = FakeCredentialStore()

    def handler(request):
        return json_response({"error": "invalid_grant"}, 400)

    connector = QuickBooksConnector(http_client=client_for(handler), credential_store=store)

    with pytest_raises(QuickBooksConnectorError):
        connector.company_info()

    assert store.metadata_values["reauthorization_required"] is True


def test_rate_limit_retries_without_secret_leakage(monkeypatch):
    configure(monkeypatch)
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if "tokens/bearer" in str(request.url):
            return json_response({"access_token": "secret-access-token", "expires_in": 3600})
        if calls == 2:
            return json_response({"fault": "limited"}, 429)
        return json_response({"QueryResponse": {"Customer": []}})

    connector = QuickBooksConnector(http_client=client_for(handler), credential_store=FakeCredentialStore(), sleep=lambda _delay: None)

    assert connector.list_resource("customers") == []
    assert "secret-access-token" not in json.dumps(connector.safe_status(include_resources=True))


def test_concurrent_sync_lock_rejects_duplicate_org(monkeypatch):
    configure(monkeypatch)
    connector = QuickBooksConnector(http_client=client_for(lambda _request: json_response({})), credential_store=FakeCredentialStore())
    entered = threading.Event()
    release = threading.Event()
    errors = []

    def hold_lock():
        with connector.organization_sync_lock():
            entered.set()
            release.wait(timeout=2)

    thread = threading.Thread(target=hold_lock)
    thread.start()
    entered.wait(timeout=2)
    try:
        with pytest_raises(QuickBooksConnectorError) as exc:
            with connector.organization_sync_lock():
                pass
        errors.append(str(exc.value))
    finally:
        release.set()
        thread.join(timeout=2)

    assert "already running" in errors[0]


class pytest_raises:
    def __init__(self, error_type):
        self.error_type = error_type
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, _tb):
        if exc is None:
            raise AssertionError(f"Expected {self.error_type.__name__}")
        if not isinstance(exc, self.error_type):
            return False
        self.value = exc
        return True
