from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.connectors.motive import MOTIVE_OAUTH_SCOPES, MOTIVE_VERIFICATION_ENDPOINT, MotiveConnector, MotiveConnectorError, MotiveOAuthService
from app.connectors.motive_credentials import MotiveCredentialStore
from app.database.database import Base
from app.identity.models import Identity
from app.models.motive import MotiveCredential, MotiveOAuthState, MotiveSyncCheckpoint, MotiveSyncHistory, MotiveVehicleRecord
from app.organizations.models import Organization

FERNET_KEY = "uPlZqC60CQaQGFL-kQo-xUOyEE5uNUAyxKmwbzfdiVo="
FAKE_ACCESS_TOKEN = "fake-access-token-for-tests-only"
FAKE_REFRESH_TOKEN = "fake-refresh-token-for-tests-only"
CANONICAL_REDIRECT_URI = "https://polaris-executive-api.onrender.com/api/v1/motive/oauth/callback"
FRONTEND_URL = "https://polaris-executive.onrender.com"


@pytest.fixture()
def motive_db(monkeypatch, tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'motive.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("POLARIS_MOTIVE_TOKEN_ENCRYPTION_KEY", FERNET_KEY)
    monkeypatch.setenv("MOTIVE_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("MOTIVE_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setenv("MOTIVE_REDIRECT_URI", CANONICAL_REDIRECT_URI)
    monkeypatch.setenv("POLARIS_FRONTEND_URL", FRONTEND_URL)
    import app.database.database as database
    import app.connectors.motive as motive
    import app.connectors.motive_credentials as credentials

    engine = create_engine(database_url)
    TestingSession = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSession)
    monkeypatch.setattr(credentials, "SessionLocal", TestingSession)
    monkeypatch.setattr(motive, "SessionLocal", TestingSession)
    Base.metadata.create_all(bind=engine)
    with TestingSession.begin() as session:
        session.add(Organization(id="org-a", slug="org-a", display_name="Org A"))
        session.add(Organization(id="org-b", slug="org-b", display_name="Org B"))
        session.add(Identity(id="identity-a", email="a@example.com", display_name="User A"))
    return TestingSession


def _save_tokens(organization_id: str = "org-a", *, expires_at: datetime | None = None) -> None:
    MotiveCredentialStore(organization_id).save_tokens(
        organization_slug=organization_id,
        access_token=FAKE_ACCESS_TOKEN,
        refresh_token=FAKE_REFRESH_TOKEN,
        expires_at=expires_at or datetime.now(timezone.utc) + timedelta(hours=1),
        granted_scopes=" ".join(MOTIVE_OAUTH_SCOPES),
        token_type="Bearer",
    )


def _state_from_authorization_url(url: str) -> str:
    return parse_qs(urlparse(url).query)["state"][0]


def test_callback_route_is_exactly_oauth_callback():
    from app.api import motive as motive_api

    prefix = "/api/v1/motive"
    paths = {route.path for route in motive_api.router.routes}
    assert f"{prefix}/oauth/callback" in paths
    assert f"{prefix}/callback" not in paths


def test_authorization_url_creates_secure_state_and_approved_scopes(motive_db):
    result = MotiveOAuthService().create_authorization_url(
        organization_id="org-a",
        identity_id="identity-a",
        organization_slug="org-a",
    )
    parsed = urlparse(result["authorization_url"])
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "gomotive.com"
    assert parsed.path == "/oauth/authorize"
    assert params["client_id"] == ["fake-client-id"]
    assert params["redirect_uri"] == [CANONICAL_REDIRECT_URI]
    assert params["response_type"] == ["code"]
    assert params["scope"] == [" ".join(MOTIVE_OAUTH_SCOPES)]
    assert len(params["state"][0]) >= 32
    assert "fake-client-secret" not in result["authorization_url"]
    with motive_db() as session:
        row = session.query(MotiveOAuthState).filter_by(state=params["state"][0]).one()
        assert row.organization_id == "org-a"
        assert row.identity_id == "identity-a"
        assert row.redirect_uri == CANONICAL_REDIRECT_URI
        assert row.scopes == " ".join(MOTIVE_OAUTH_SCOPES)
        assert row.consumed_at is None


def test_token_exchange_uses_redirect_uri_stored_with_state(monkeypatch, motive_db):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"access_token": FAKE_ACCESS_TOKEN, "refresh_token": FAKE_REFRESH_TOKEN, "expires_in": 7200, "token_type": "Bearer"})

    service = MotiveOAuthService(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    state = _state_from_authorization_url(service.create_authorization_url(organization_id="org-a", identity_id="identity-a", organization_slug="org-a")["authorization_url"])
    monkeypatch.setenv("MOTIVE_REDIRECT_URI", "https://polaris-executive-api.onrender.com/api/v1/motive/oauth/callback/")
    service.complete_authorization(state=state, code="fake-auth-code")

    form = parse_qs(captured["body"])
    assert form["redirect_uri"] == [CANONICAL_REDIRECT_URI]
    assert form["redirect_uri"] != ["https://polaris-executive-api.onrender.com/api/v1/motive/oauth/callback/"]


def test_frontend_hash_redirects_for_callback_outcomes(monkeypatch):
    from app.api import motive as motive_api

    class FakeOAuthService:
        def complete_authorization(self, *, code: str, state: str):
            return {"connection_status": "configured_unverified"}

    monkeypatch.setenv("POLARIS_FRONTEND_URL", FRONTEND_URL)
    monkeypatch.setattr(motive_api, "MotiveOAuthService", lambda: FakeOAuthService())

    success = motive_api.motive_callback(code="fake-code", state="fake-state")
    denied = motive_api.motive_callback(error="access_denied")
    missing = motive_api.motive_callback()

    assert success.headers["location"] == f"{FRONTEND_URL}/#executive/connectors?motive=connected_unverified"
    assert denied.headers["location"] == f"{FRONTEND_URL}/#executive/connectors?motive=denied"
    assert missing.headers["location"] == f"{FRONTEND_URL}/#executive/connectors?motive=error"
    assert "/executive/connectors" not in success.headers["location"].replace("/#executive/connectors", "")


def test_missing_redirect_or_frontend_configuration_fails_safely(monkeypatch, motive_db):
    from app.api import motive as motive_api

    monkeypatch.delenv("MOTIVE_REDIRECT_URI", raising=False)
    with pytest.raises(MotiveConnectorError) as redirect_error:
        MotiveOAuthService().create_authorization_url(organization_id="org-a", identity_id="identity-a", organization_slug="org-a")
    assert redirect_error.value.code == "oauth_configuration_missing"
    assert "fake-client-secret" not in str(redirect_error.value)

    monkeypatch.setenv("MOTIVE_REDIRECT_URI", CANONICAL_REDIRECT_URI)
    monkeypatch.delenv("POLARIS_FRONTEND_URL", raising=False)
    with pytest.raises(MotiveConnectorError) as frontend_error:
        motive_api._frontend_return_url("error")
    assert frontend_error.value.code == "frontend_url_missing"


def test_state_expiry_replay_and_wrong_organization_are_rejected(motive_db):
    service = MotiveOAuthService(http_client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"access_token": "a", "refresh_token": "r", "expires_in": 7200, "token_type": "Bearer"}))))
    state = _state_from_authorization_url(service.create_authorization_url(organization_id="org-a", identity_id="identity-a", organization_slug="org-a")["authorization_url"])

    with pytest.raises(MotiveConnectorError) as wrong_org:
        service.complete_authorization(state=state, code="fake-code", expected_organization_id="org-b")
    assert wrong_org.value.code == "state_wrong_organization"

    service.complete_authorization(state=state, code="fake-code")
    with pytest.raises(MotiveConnectorError) as reused:
        service.complete_authorization(state=state, code="fake-code")
    assert reused.value.code == "state_reused"

    expired = _state_from_authorization_url(service.create_authorization_url(organization_id="org-a", identity_id="identity-a", organization_slug="org-a")["authorization_url"])
    with motive_db.begin() as session:
        row = session.query(MotiveOAuthState).filter_by(state=expired).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(MotiveConnectorError) as expired_error:
        service.complete_authorization(state=expired, code="fake-code")
    assert expired_error.value.code == "state_expired"


def test_tokens_are_encrypted_and_metadata_does_not_decrypt(monkeypatch, motive_db):
    _save_tokens()
    with motive_db() as session:
        row = session.query(MotiveCredential).filter_by(organization_id="org-a").one()
        assert row.encrypted_access_token != FAKE_ACCESS_TOKEN
        assert row.encrypted_refresh_token != FAKE_REFRESH_TOKEN
        assert FAKE_ACCESS_TOKEN not in repr(row.__dict__)
        assert FAKE_REFRESH_TOKEN not in repr(row.__dict__)

    def fail_decrypt(_value):
        raise AssertionError("metadata must not decrypt Motive OAuth tokens")

    monkeypatch.setattr(MotiveCredentialStore, "_decrypt", staticmethod(fail_decrypt))
    metadata = MotiveCredentialStore("org-a").metadata()
    assert metadata["token_present"] is True
    assert metadata["connection_status"] == "configured_unverified"
    assert FAKE_ACCESS_TOKEN not in str(metadata)
    assert FAKE_REFRESH_TOKEN not in str(metadata)


def test_tenant_isolation_blocks_cross_org_credential_reads(motive_db):
    _save_tokens("org-a")
    assert MotiveCredentialStore("org-b").metadata()["token_present"] is False
    with pytest.raises(Exception):
        MotiveCredentialStore("org-b").load_tokens()


def test_callback_exchange_stores_oauth_tokens_without_secret_leakage(motive_db):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"access_token": FAKE_ACCESS_TOKEN, "refresh_token": FAKE_REFRESH_TOKEN, "expires_in": 7200, "token_type": "Bearer", "scope": " ".join(MOTIVE_OAUTH_SCOPES)})

    service = MotiveOAuthService(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result_url = service.create_authorization_url(organization_id="org-a", identity_id="identity-a", organization_slug="org-a")["authorization_url"]
    state = _state_from_authorization_url(result_url)
    result = service.complete_authorization(state=state, code="fake-auth-code")

    assert result["connection_status"] == "configured_unverified"
    assert "fake-client-secret" in captured["body"]
    assert FAKE_ACCESS_TOKEN not in str(result)
    assert FAKE_REFRESH_TOKEN not in str(result)
    assert "fake-auth-code" not in str(result)
    assert state not in str(result)
    assert MotiveCredentialStore("org-a").metadata()["authentication_method"] == "oauth2"


def test_refresh_rotation_and_invalid_grant_handling(motive_db):
    _save_tokens(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"access_token": "rotated-access", "refresh_token": "rotated-refresh", "expires_in": 7200, "token_type": "Bearer"})

    service = MotiveOAuthService(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert service.access_token_for_request("org-a") == "rotated-access"
    assert MotiveCredentialStore("org-a").load_tokens().refresh_token == "rotated-refresh"

    _save_tokens(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    invalid = MotiveOAuthService(http_client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(400, json={"error": "invalid_grant"}))))
    with pytest.raises(MotiveConnectorError) as exc:
        invalid.access_token_for_request("org-a")
    assert exc.value.code == "invalid_grant"
    metadata = MotiveCredentialStore("org-a").metadata()
    assert metadata["connection_status"] == "authorization_required"
    assert metadata["authorization_required"] is True


def test_successful_limited_verification_uses_bearer_request_and_updates_status(motive_db):
    _save_tokens()
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"company": {"id": "company-1", "name": "Mor Logistics"}})

    connector = MotiveConnector(
        credential_store=MotiveCredentialStore("org-a"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = connector.verify_connection()

    assert result["status"] == "connected"
    assert result["endpoint"] == MOTIVE_VERIFICATION_ENDPOINT
    assert result["request"] == {"method": "GET", "path": MOTIVE_VERIFICATION_ENDPOINT, "params": {}}
    assert captured["url"] == "https://api.gomotive.com/v1/companies"
    assert captured["headers"]["authorization"] == f"Bearer {FAKE_ACCESS_TOKEN}"
    assert FAKE_ACCESS_TOKEN not in str(result)
    metadata = MotiveCredentialStore("org-a").metadata()
    assert metadata["connection_status"] == "connected"
    assert metadata["provider_company_id"] == "company-1"


@pytest.mark.parametrize("status_code,expected", [(401, "authorization_required"), (403, "authorization_required"), (429, "rate_limited"), (500, "failed")])
def test_safe_status_for_known_provider_failures(status_code, expected, motive_db):
    _save_tokens()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": "provider failure"})

    connector = MotiveConnector(
        credential_store=MotiveCredentialStore("org-a"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(MotiveConnectorError):
        connector.verify_connection()
    assert MotiveCredentialStore("org-a").metadata()["connection_status"] == expected


def test_uniqueness_constraints_support_idempotent_foundation_rows(motive_db):
    _save_tokens()
    _save_tokens()
    with motive_db() as session:
        assert session.query(MotiveCredential).filter_by(organization_id="org-a").count() == 1
        session.add(MotiveVehicleRecord(organization_id="org-a", organization_slug="org-a", provider_vehicle_id="vehicle-1"))
        session.commit()
        session.add(MotiveVehicleRecord(organization_id="org-b", organization_slug="org-b", provider_vehicle_id="vehicle-1"))
        session.commit()
        session.add(MotiveVehicleRecord(organization_id="org-a", organization_slug="org-a", provider_vehicle_id="vehicle-1"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_checkpoint_preserves_previous_position_on_failure_or_rate_limit(motive_db):
    with motive_db.begin() as session:
        checkpoint = MotiveSyncCheckpoint(
            organization_id="org-a",
            organization_slug="org-a",
            provider_resource="vehicles",
            page_number=7,
            last_successful_position={"page_number": 7},
            checkpoint_status="success",
            last_successful_sync_at=datetime.now(timezone.utc),
        )
        session.add(checkpoint)
        session.add(
            MotiveSyncHistory(
                organization_id="org-a",
                organization_slug="org-a",
                provider_resource="vehicles",
                mode="verification",
                status="rate_limited",
                run_id="rate-limited-run",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                checkpoint_before={"page_number": 7},
                checkpoint_after={"page_number": 7},
            )
        )
    with motive_db() as session:
        row = session.query(MotiveSyncCheckpoint).filter_by(organization_id="org-a", provider_resource="vehicles").one()
        assert row.page_number == 7
        assert row.last_successful_position == {"page_number": 7}


def test_provider_specific_types_do_not_escape_internal_contracts():
    from app.connectors import motive_contracts

    exported = {name for name in dir(motive_contracts) if name.startswith("Motive")}
    assert "MotiveVehicle" in exported
    assert "MotiveIftaSummary" in exported
    assert not any(name.endswith("Response") or name.endswith("Payload") for name in exported)
