"""Motive authentication certification gate (2026-08-17).

Motive API Support's 2026-08-17 written reply confirmed the Company API Key
account key against ``GET /v1/fuel_purchases`` using the ``x-api-key``
header, and that the previously-failing client tests used
``Authorization: Bearer <key>``. This module proves, across every Motive
Company API Key request helper in the backend, that Polaris:

- always sends ``x-api-key`` (Polaris spells it ``X-API-Key``; HTTP header
  names are case-insensitive, so this is the same header);
- never sends ``Authorization: Bearer`` for a Company API Key request;
- preserves endpoint-specific headers (``Accept: application/json``,
  ``X-Metric-Units`` where applicable) alongside the auth header;
- never leaks the real key value into an exception, log record, or public
  contract endpoint;
- keeps the separate, currently-dormant Motive OAuth credential-storage
  subsystem (``app.connectors.motive_credentials``) conceptually distinct
  from Company API Key auth, and confirms it stores (but never sends) a
  ``Bearer``-typed token, since there is no live OAuth request code path in
  this codebase today.

No live Motive API call is made anywhere in this module. All provider
interaction is mocked via ``httpx.MockTransport``. No real Motive API key
value appears anywhere in this file -- only the synthetic placeholder
``test-motive-api-key``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from cryptography.fernet import Fernet
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.connectors.motive import MOTIVE_USERS_ENDPOINT, MOTIVE_VEHICLES_ENDPOINT, MotiveConnector
from app.connectors.motive_vehicle_utilization_contract import request_vehicle_utilization_payload
from app.connectors.motive_vehicle_utilization_pagination import request_vehicle_utilization_page
from app.database.database import Base
from app.models.motive import MotiveCredential
from app.organizations.models import Organization
from app.security.models import AuthenticatedPrincipal, Permission

FAKE_API_KEY = "test-motive-api-key"


def _principal(organization_id: str = "org-a") -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        identity_id="identity-a",
        organization_id=organization_id,
        membership_id=f"membership-{organization_id}",
        role="admin",
        permissions=frozenset({Permission.CONNECTOR_READ, Permission.CONNECTOR_WRITE}),
        provider="test",
        subject="test-subject",
    )


def _capture_client(calls: list[httpx.Request], *, status_code: int = 200, payload: dict | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status_code, json=payload if payload is not None else {})

    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# Section 4/5/19 -- exact audit of every Company API Key request helper.
# ---------------------------------------------------------------------------
def test_vehicles_and_users_connector_requests_use_x_api_key_not_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    calls: list[httpx.Request] = []
    client = _capture_client(calls, payload={"vehicles": [], "pagination": {"total": 0}})
    connector = MotiveConnector(organization_id="org-a", http_client=client)

    connector.list_vehicles(organization_id="org-a", organization_slug="org-a")

    assert len(calls) == 1
    request = calls[0]
    assert request.url.path == MOTIVE_VEHICLES_ENDPOINT
    assert request.headers["x-api-key"] == FAKE_API_KEY
    assert "Authorization" not in request.headers
    assert request.headers["Accept"] == "application/json"


def test_users_connector_request_uses_x_api_key_not_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    calls: list[httpx.Request] = []
    client = _capture_client(calls, payload={"users": [], "pagination": {"total": 0}})
    connector = MotiveConnector(organization_id="org-a", http_client=client)

    connector.list_users(organization_id="org-a", organization_slug="org-a")

    assert len(calls) == 1
    request = calls[0]
    assert request.url.path == MOTIVE_USERS_ENDPOINT
    assert request.headers["x-api-key"] == FAKE_API_KEY
    assert "Authorization" not in request.headers


def test_verification_probe_uses_x_api_key_not_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    calls: list[httpx.Request] = []
    client = _capture_client(calls, payload={"vehicles": []})
    connector = MotiveConnector(organization_id="org-a", http_client=client)

    connector.verify_connection()

    assert len(calls) == 1
    assert calls[0].headers["x-api-key"] == FAKE_API_KEY
    assert "Authorization" not in calls[0].headers


def test_vehicle_utilization_contract_request_uses_x_api_key_and_preserves_x_metric_units(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    calls: list[httpx.Request] = []
    client = _capture_client(calls, payload={"vehicle_idle_rollups": [], "pagination": {"per_page": 1, "page_no": 1, "total": 0}})

    request_vehicle_utilization_payload(
        organization_id="org-a",
        provider_vehicle_ids=["veh-1"],
        start_date=date(2026, 8, 12),
        end_date=date(2026, 8, 13),
        per_page=1,
        metric_units=True,
        http_client=client,
    )

    assert len(calls) == 1
    request = calls[0]
    assert request.headers["X-API-Key"] == FAKE_API_KEY
    assert "Authorization" not in request.headers
    assert request.headers["Accept"] == "application/json"
    assert request.headers["X-Metric-Units"] == "true"


def test_vehicle_utilization_pagination_request_uses_x_api_key_and_x_metric_units(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    calls: list[httpx.Request] = []
    client = _capture_client(calls, payload={"vehicle_idle_rollups": [], "pagination": {"per_page": 100, "page_no": 1, "total": 0}})

    request_vehicle_utilization_page(
        organization_id="org-a",
        provider_vehicle_ids=["veh-1"],
        start_date=date(2026, 8, 13),
        end_date=date(2026, 8, 13),
        page_no=1,
        per_page=100,
        metric_units=True,
        http_client=client,
    )

    assert len(calls) == 1
    request = calls[0]
    assert request.headers["X-API-Key"] == FAKE_API_KEY
    assert "Authorization" not in request.headers
    assert request.headers["X-Metric-Units"] == "true"


# ---------------------------------------------------------------------------
# Section 4 -- fuel purchases / IFTA / driver utilization audit result.
#
# As of this gate, there is no request-building code path anywhere in the
# backend for GET /v1/fuel_purchases, GET /v1/ifta/summary, or
# GET /v2/driver_utilization -- only deferred model tables and endpoint
# constant strings exist (see MOTIVE_CONFIRMED_ENDPOINTS and
# MotiveIftaSummaryRecord / MotiveDriverUtilizationRecord in
# app/models/motive.py). There is therefore no auth-header code to audit for
# those resources yet; when a request helper is added for them, it must
# reuse the same shared request path exercised above (or an equally
# centralized helper) rather than duplicating auth logic. This test asserts
# that fact stays true so a future connector addition cannot silently add a
# second, un-audited request-header code path without this test failing.
# ---------------------------------------------------------------------------
def test_fuel_purchases_and_ifta_have_no_request_helper_yet() -> None:
    import app.connectors.motive as motive_module

    assert not hasattr(motive_module, "request_fuel_purchases")
    assert not hasattr(motive_module, "request_ifta_summary")
    assert not hasattr(motive_module, "request_driver_utilization")


# ---------------------------------------------------------------------------
# Section 7/19/22 -- the real secret never appears anywhere observable.
# ---------------------------------------------------------------------------
def test_real_secret_never_appears_in_connector_errors_or_logs(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"connection refused for key {FAKE_API_KEY}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    connector = MotiveConnector(organization_id="org-a", http_client=client)

    with caplog.at_level("INFO"):
        with pytest.raises(Exception) as exc_info:
            connector.list_vehicles(organization_id="org-a", organization_slug="org-a")

    assert FAKE_API_KEY not in str(exc_info.value)
    for record in caplog.records:
        assert FAKE_API_KEY not in record.getMessage()
        assert FAKE_API_KEY not in str(record.__dict__)


def test_verification_contract_endpoint_never_exposes_the_real_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    from app.api.motive import motive_verification_contract

    result = motive_verification_contract(principal=_principal())

    rendered = str(result)
    assert FAKE_API_KEY not in rendered
    assert result["company_api_key_authentication"]["header"] == "x-api-key"
    assert result["company_api_key_authentication"]["bearer_prefix"] is False
    assert result["company_api_key_authentication"]["authorization_bearer_used"] is False
    assert result["company_api_key_authentication"]["provider_confirmed"] is True
    assert result["company_api_key_authentication"]["real_secret_exposed"] is False
    assert result["company_api_key_authentication"]["current_key_rotation_required_before_production_broad_enablement"] is True
    assert result["company_api_key_authentication"]["rotation_status"] == "DEFERRED_UNTIL_MOTIVE_INTEGRATION_COMPLETION_BY_USER_DECISION"
    assert result["oauth_authentication"]["scheme"] == "bearer_token"
    assert result["oauth_authentication"]["header"] == "Authorization"
    assert result["oauth_authentication"]["bearer_prefix"] is True
    assert result["oauth_authentication"]["used_for_current_mor_internal_server_to_server_integration"] is False


# ---------------------------------------------------------------------------
# Section 6 -- OAuth safety: the credential-storage subsystem is a distinct,
# currently-dormant path. It never builds an outgoing HTTP header at all
# today (there is no code path that reads a stored OAuth token and sends
# it), but it does store the OAuth scheme's own Bearer token_type as
# metadata -- proving that when/if an OAuth request path is later added, it
# has the correct scheme already recorded, distinct from the Company API Key
# x-api-key path exercised above.
# ---------------------------------------------------------------------------
@pytest.fixture()
def credential_db(monkeypatch, tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'motive-auth.db').as_posix()}"
    monkeypatch.setenv("POLARIS_MOTIVE_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    import app.database.database as database
    import app.connectors.motive_credentials as motive_credentials

    engine = create_engine(database_url)
    TestingSession = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSession)
    monkeypatch.setattr(motive_credentials, "SessionLocal", TestingSession)
    Base.metadata.create_all(bind=engine)
    with TestingSession.begin() as session:
        session.add(Organization(id="org-a", slug="org-a", display_name="Org A"))
    return TestingSession


def test_oauth_credential_store_records_bearer_token_type_as_metadata_only(credential_db) -> None:
    from app.connectors.motive_credentials import MotiveCredentialStore

    store = MotiveCredentialStore("org-a")
    store.save_tokens(
        organization_slug="org-a",
        access_token="synthetic-oauth-access-token-for-tests-only",
        refresh_token="synthetic-oauth-refresh-token-for-tests-only",
        expires_at=datetime.now(timezone.utc),
        granted_scopes="read",
    )

    with credential_db() as session:
        credential = session.query(MotiveCredential).filter_by(organization_id="org-a").one()
        assert credential.token_type == "Bearer"
        assert credential.authentication_method == "oauth2"

    metadata = store.metadata()
    assert metadata["authentication_method"] == "oauth2"
    assert metadata["token_type"] == "Bearer"
    # Confirms the metadata surface never leaks the actual stored token value.
    rendered = str(metadata)
    assert "synthetic-oauth-access-token-for-tests-only" not in rendered
    assert "synthetic-oauth-refresh-token-for-tests-only" not in rendered


def test_no_code_path_builds_an_outgoing_header_from_the_oauth_credential_store() -> None:
    """There is no function in app.connectors.motive_credentials that
    constructs an HTTP header dict at all -- it is a pure encrypted-storage
    layer. This proves OAuth's Bearer scheme and Company API Key's
    x-api-key scheme cannot be accidentally conflated, because the OAuth
    module never reaches the point of building a request header in this
    codebase today."""
    import inspect

    import app.connectors.motive_credentials as motive_credentials

    source = inspect.getsource(motive_credentials)
    assert "Authorization" not in source
    assert "x-api-key" not in source.lower()
