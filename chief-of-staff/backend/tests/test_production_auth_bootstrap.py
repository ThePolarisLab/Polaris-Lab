import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./polaris-production-auth-test.db")
os.environ.setdefault("POLARIS_ENV", "test")
os.environ.setdefault("POLARIS_SESSION_SECRET", "test-session-secret-with-enough-length")
os.environ.setdefault("POLARIS_BOOTSTRAP_ADMIN_EMAIL", "admin@morlogistics.example")
os.environ.setdefault("POLARIS_BOOTSTRAP_SECRET", "bootstrap-secret-with-enough-length")

import bcrypt
import pytest
from fastapi.testclient import TestClient

from app.auth.models import ProductionAuthBootstrapState, ProductionAuthSession, ProductionLoginAttempt, ProductionPasswordCredential
from app.auth.service import BOOTSTRAP_IDENTITY_ID, BOOTSTRAP_ORGANIZATION_ID
from app.database.database import Base, SessionLocal, engine
from app.identity.models import Identity, MembershipStatus, OrganizationMembership
from app.main import app
from app.organizations.models import Organization

ADMIN_EMAIL = "admin@morlogistics.example"
BOOTSTRAP_SECRET = "bootstrap-secret-with-enough-length"
ADMIN_PASSWORD = "CorrectHorseBattery1"


@pytest.fixture(autouse=True)
def reset_database(monkeypatch):
    monkeypatch.setenv("POLARIS_ENV", "test")
    monkeypatch.setenv("POLARIS_SESSION_SECRET", "test-session-secret-with-enough-length")
    monkeypatch.setenv("POLARIS_BOOTSTRAP_ADMIN_EMAIL", ADMIN_EMAIL)
    monkeypatch.setenv("POLARIS_BOOTSTRAP_SECRET", BOOTSTRAP_SECRET)
    monkeypatch.setenv("POLARIS_ACCESS_TOKEN_TTL_SECONDS", "900")
    monkeypatch.setenv("POLARIS_REFRESH_TOKEN_TTL_SECONDS", "3600")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def bootstrap(client):
    return client.post(
        "/api/v1/auth/bootstrap",
        json={"bootstrap_secret": BOOTSTRAP_SECRET, "password": ADMIN_PASSWORD},
    )


def login(client, password=ADMIN_PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": password})


def auth_headers(token_response):
    payload = token_response.json()
    return {"Authorization": f"Bearer {payload['access_token']}", "X-Polaris-Organization": payload["organization_id"]}


def test_first_bootstrap_succeeds_and_hashes_password(client):
    response = bootstrap(client)
    assert response.status_code == 201
    assert response.json()["organization_id"] == BOOTSTRAP_ORGANIZATION_ID
    assert response.json()["identity_id"] == BOOTSTRAP_IDENTITY_ID

    with SessionLocal() as session:
        organization = session.get(Organization, BOOTSTRAP_ORGANIZATION_ID)
        identity = session.get(Identity, BOOTSTRAP_IDENTITY_ID)
        credential = session.get(ProductionPasswordCredential, BOOTSTRAP_IDENTITY_ID)
        state = session.get(ProductionAuthBootstrapState, "first-admin")
        membership = session.query(OrganizationMembership).filter_by(
            organization_id=BOOTSTRAP_ORGANIZATION_ID,
            identity_id=BOOTSTRAP_IDENTITY_ID,
        ).one()

    assert organization.slug == "mor-logistics"
    assert organization.legal_name == "MOR LOGISTICS MANITOBA LIMITED"
    assert identity.email == ADMIN_EMAIL
    assert membership.role == "owner"
    assert state.completed is True
    assert credential.password_hash != ADMIN_PASSWORD
    assert bcrypt.checkpw(ADMIN_PASSWORD.encode(), credential.password_hash.encode())


def test_second_bootstrap_is_rejected(client):
    assert bootstrap(client).status_code == 201
    response = bootstrap(client)
    assert response.status_code == 409


def test_wrong_bootstrap_secret_rejected_without_leak(client):
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"bootstrap_secret": "wrong-secret-with-enough-length", "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 409
    assert "wrong-secret" not in response.text
    assert BOOTSTRAP_SECRET not in response.text


def test_missing_bootstrap_config_rejected(client, monkeypatch):
    monkeypatch.delenv("POLARIS_BOOTSTRAP_SECRET", raising=False)
    response = bootstrap(client)
    assert response.status_code == 503
    assert "secret" not in response.text.lower()


def test_valid_login_and_me(client):
    assert bootstrap(client).status_code == 201
    response = login(client)
    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"]
    assert payload["refresh_token"]
    assert payload["organization_id"] == BOOTSTRAP_ORGANIZATION_ID

    me = client.get("/api/v1/auth/me", headers=auth_headers(response))
    assert me.status_code == 200
    assert me.json()["identity_id"] == BOOTSTRAP_IDENTITY_ID
    assert "connector.write" in me.json()["permissions"]
    assert "financial.write" in me.json()["permissions"]


def test_invalid_password_rejected(client):
    assert bootstrap(client).status_code == 201
    response = login(client, password="not-the-password")
    assert response.status_code == 401


def test_inactive_identity_rejected(client):
    assert bootstrap(client).status_code == 201
    with SessionLocal.begin() as session:
        session.get(Identity, BOOTSTRAP_IDENTITY_ID).status = "disabled"
    response = login(client)
    assert response.status_code == 401


def test_inactive_membership_rejected(client):
    assert bootstrap(client).status_code == 201
    with SessionLocal.begin() as session:
        membership = session.query(OrganizationMembership).filter_by(identity_id=BOOTSTRAP_IDENTITY_ID).one()
        membership.status = MembershipStatus.REVOKED.value
    response = login(client)
    assert response.status_code == 403


def test_cross_organization_access_rejected(client):
    assert bootstrap(client).status_code == 201
    login_response = login(client)
    with SessionLocal.begin() as session:
        session.add(Organization(id="org-other", slug="org-other", display_name="Other Org"))
    response = client.get("/api/v1/organizations/org-other", headers=auth_headers(login_response))
    assert response.status_code == 403


def test_logout_revokes_session(client):
    assert bootstrap(client).status_code == 201
    login_response = login(client)
    headers = auth_headers(login_response)
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_refresh_rotates_and_reuse_is_rejected(client):
    assert bootstrap(client).status_code == 201
    login_response = login(client)
    refresh_token = login_response.json()["refresh_token"]

    first_refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert first_refresh.status_code == 200
    assert first_refresh.json()["refresh_token"] != refresh_token

    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert replay.status_code == 401


def test_login_rate_limiting(client):
    assert bootstrap(client).status_code == 201
    for _ in range(5):
        assert login(client, password="bad-password").status_code == 401
    response = login(client, password="bad-password")
    assert response.status_code == 429
    with SessionLocal() as session:
        assert session.query(ProductionLoginAttempt).count() >= 6


def test_session_expiry_rejected(client, monkeypatch):
    monkeypatch.setenv("POLARIS_ACCESS_TOKEN_TTL_SECONDS", "1")
    assert bootstrap(client).status_code == 201
    login_response = login(client)
    with SessionLocal.begin() as session:
        auth_session = session.query(ProductionAuthSession).one()
        auth_session.access_expires_at = auth_session.created_at
    assert client.get("/api/v1/auth/me", headers=auth_headers(login_response)).status_code == 401
