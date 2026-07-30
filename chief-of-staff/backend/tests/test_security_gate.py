import os
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("DATABASE_URL", "sqlite:///./polaris-security-test.db")
os.environ.setdefault("POLARIS_ENV", "test")
os.environ.setdefault("POLARIS_LOCAL_AUTH_SECRET", "test-local-auth-secret-with-enough-length")
os.environ.setdefault("POLARIS_QBO_CLIENT_ID", "client-id")
os.environ.setdefault("POLARIS_QBO_CLIENT_SECRET", "client-secret")
os.environ.setdefault("POLARIS_QBO_REDIRECT_URI", "http://localhost:8000/api/v1/connectors/quickbooks/oauth/callback")
os.environ.setdefault("POLARIS_QBO_OAUTH_STATE_SECRET", "quickbooks-state-secret-with-enough-length")
os.environ.setdefault("POLARIS_QBO_TOKEN_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

import pytest
from fastapi.testclient import TestClient

from app.connectors.quickbooks_oauth import QuickBooksOAuthError, QuickBooksOAuthService, QuickBooksOAuthTokens
from app.database.database import Base, SessionLocal, engine
from app.identity.models import Identity, OrganizationMembership
from app.main import app
from app.organizations.models import Organization
from app.security.providers import LocalTokenProvider


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def seed_identity(role="owner", organization_id="org-1", identity_id="identity-1"):
    with SessionLocal.begin() as session:
        session.add(Organization(id=organization_id, slug=organization_id, display_name=organization_id))
        session.add(Identity(id=identity_id, email=f"{identity_id}@example.com", display_name=identity_id))
        session.add(
            OrganizationMembership(
                id=f"membership-{organization_id}-{identity_id}",
                organization_id=organization_id,
                identity_id=identity_id,
                role=role,
            )
        )
    token = LocalTokenProvider().issue(identity_id)
    return {"Authorization": f"Bearer {token}", "X-Polaris-Organization": organization_id}


def test_missing_token_returns_401(client):
    response = client.get("/company")
    assert response.status_code == 401


def test_invalid_token_returns_401(client):
    response = client.get("/company", headers={"Authorization": "Bearer invalid", "X-Polaris-Organization": "org-1"})
    assert response.status_code == 401


def test_missing_organization_context_is_rejected(client):
    seed_identity()
    token = LocalTokenProvider().issue("identity-1")
    response = client.get("/company", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 400


def test_unauthorized_permission_returns_403(client):
    headers = seed_identity(role="viewer")
    response = client.post("/api/v1/connectors/github/sync", headers=headers)
    assert response.status_code == 403


def test_cross_organization_access_is_rejected(client):
    headers = seed_identity(role="owner", organization_id="org-1")
    with SessionLocal.begin() as session:
        session.add(Organization(id="org-2", slug="org-2", display_name="Org 2"))
    response = client.get("/api/v1/organizations/org-2/memberships", headers=headers)
    assert response.status_code == 403


def test_authorized_access_succeeds(client):
    headers = seed_identity(role="owner")
    response = client.get("/company", headers=headers)
    assert response.status_code == 200
    assert response.json()["company_name"] == "MOR Logistics Manitoba Limited"


def test_connector_disconnect_requires_manage_permission(client):
    headers = seed_identity(role="viewer")
    response = client.delete("/api/v1/connectors/quickbooks/oauth/connection", headers=headers)
    assert response.status_code == 403


def test_quickbooks_oauth_state_is_single_use_and_org_bound(monkeypatch):
    service = QuickBooksOAuthService()
    url = service.authorization_url(organization_id="org-1", identity_id="identity-1")
    state = parse_qs(urlparse(url).query)["state"][0]

    monkeypatch.setattr(
        service,
        "_exchange_code",
        lambda code: QuickBooksOAuthTokens(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_in=3600,
            refresh_token_expires_in=None,
            scope="com.intuit.quickbooks.accounting",
        ),
    )

    context = service.complete_authorization(code="code", realm_id="realm-1", state=state)
    assert context.organization_id == "org-1"
    assert context.identity_id == "identity-1"

    with pytest.raises(QuickBooksOAuthError, match="already been used"):
        service.complete_authorization(code="code-2", realm_id="realm-2", state=state)
