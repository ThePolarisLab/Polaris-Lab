import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./polaris-tenant-isolation-test.db")
os.environ.setdefault("POLARIS_ENV", "test")
os.environ.setdefault("POLARIS_LOCAL_AUTH_SECRET", "test-local-auth-secret-with-enough-length")
os.environ.setdefault("POLARIS_QBO_CLIENT_ID", "client-id")
os.environ.setdefault("POLARIS_QBO_CLIENT_SECRET", "client-secret")
os.environ.setdefault("POLARIS_QBO_REDIRECT_URI", "http://localhost:8000/api/v1/connectors/quickbooks/oauth/callback")
os.environ.setdefault("POLARIS_QBO_OAUTH_STATE_SECRET", "quickbooks-state-secret-with-enough-length")
os.environ.setdefault("POLARIS_QBO_TOKEN_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

from app.connectors.quickbooks_credentials import QuickBooksCredentialError, QuickBooksCredentialStore, QuickBooksOAuthState
from app.connectors.quickbooks_oauth import QuickBooksOAuthError, QuickBooksOAuthService, QuickBooksOAuthTokens
from app.database.database import Base, SessionLocal, engine
from app.identity.models import Identity, OrganizationMembership
from app.main import app
from app.models.memory import MemoryEntry
from app.models.team_note import TeamNote
from app.models.truck import Truck
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


def seed_principal(role: str, organization_id: str, identity_id: str) -> dict[str, str]:
    with SessionLocal.begin() as session:
        session.add(Organization(id=organization_id, slug=organization_id, display_name=organization_id))
        session.add(Identity(id=identity_id, email=f"{identity_id}@example.test", display_name=identity_id))
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


def seed_two_orgs() -> tuple[dict[str, str], dict[str, str]]:
    return (
        seed_principal("owner", "org-1", "identity-1"),
        seed_principal("owner", "org-2", "identity-2"),
    )


def test_cross_org_trucks_are_not_read(client):
    org1, org2 = seed_two_orgs()
    assert client.post("/trucks", headers=org1, json={"unit_number": "T-1", "make": "Freightliner", "model": "Cascadia", "year": 2024}).status_code == 200

    response = client.get("/trucks", headers=org2)

    assert response.status_code == 200
    assert response.json() == []


def test_cross_org_team_notes_are_not_read_or_updated(client):
    org1, org2 = seed_two_orgs()
    created = client.post("/team-notes", headers=org1, json={"author": "Ops", "title": "Org 1 note", "details": "private"})
    assert created.status_code == 201
    note_id = created.json()["id"]

    assert client.get("/team-notes", headers=org2).json() == []
    assert client.get(f"/team-notes/{note_id}", headers=org2).status_code == 404
    assert client.patch(f"/team-notes/{note_id}", headers=org2, json={"title": "stolen"}).status_code == 404


def test_cross_org_memory_and_dashboard_are_scoped(client):
    org1, org2 = seed_two_orgs()
    assert client.post("/memory", headers=org1, json={"category": "Finance", "title": "Org 1", "details": "private"}).status_code == 201
    assert client.post("/trucks", headers=org1, json={"unit_number": "T-2", "make": "Volvo", "model": "VNL", "year": 2023}).status_code == 200

    memories = client.get("/memory", headers=org2)
    dashboard = client.get("/dashboard/executive", headers=org2)

    assert memories.status_code == 200
    assert memories.json() == []
    assert dashboard.status_code == 200
    assert dashboard.json()["total_trucks"] == 0
    assert dashboard.json()["open_team_notes"] == 0


def test_cross_org_identity_and_organization_access_is_rejected(client):
    org1, org2 = seed_two_orgs()
    with SessionLocal.begin() as session:
        session.add(Identity(id="identity-shared", email="shared@example.test", display_name="Shared"))
        session.add(OrganizationMembership(organization_id="org-1", identity_id="identity-shared", role="viewer"))

    assert client.get("/api/v1/identities/identity-shared", headers=org1).status_code == 200
    assert client.get("/api/v1/identities/identity-shared", headers=org2).status_code == 404
    listed = client.get("/api/v1/organizations", headers=org2)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == ["org-2"]
    assert client.get("/api/v1/organizations/org-1", headers=org2).status_code == 403


def test_cross_org_quickbooks_credentials_are_rejected():
    seed_two_orgs()
    QuickBooksCredentialStore("org-1").save(realm_id="realm-1", refresh_token="refresh-1", scopes="scope")

    assert QuickBooksCredentialStore("org-1").load()[0] == "realm-1"
    with pytest.raises(QuickBooksCredentialError):
        QuickBooksCredentialStore("org-2").load()


def _oauth_tokens(_: str) -> QuickBooksOAuthTokens:
    return QuickBooksOAuthTokens(
        access_token="access-token",
        refresh_token="refresh-token",
        expires_in=3600,
        refresh_token_expires_in=None,
        scope="com.intuit.quickbooks.accounting",
    )


def make_oauth_state(service: QuickBooksOAuthService, organization_id: str = "org-1", identity_id: str = "identity-1") -> str:
    url = service.authorization_url(organization_id=organization_id, identity_id=identity_id)
    return parse_qs(urlparse(url).query)["state"][0]


def test_oauth_replay_malformed_expired_wrong_org_and_wrong_principal(monkeypatch):
    seed_two_orgs()
    service = QuickBooksOAuthService()
    monkeypatch.setattr(service, "_exchange_code", _oauth_tokens)

    malformed = "not-a-valid-state"
    with pytest.raises(QuickBooksOAuthError, match="invalid"):
        service.complete_authorization(code="code", realm_id="realm", state=malformed)

    expired = make_oauth_state(service)
    with SessionLocal.begin() as session:
        record = session.get(QuickBooksOAuthState, expired)
        record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(QuickBooksOAuthError, match="expired"):
        service.complete_authorization(code="code", realm_id="realm", state=expired)

    wrong_org = make_oauth_state(service, organization_id="org-1", identity_id="identity-1")
    with pytest.raises(QuickBooksOAuthError, match="organization"):
        service.complete_authorization(code="code", realm_id="realm", state=wrong_org, expected_organization_id="org-2")

    wrong_principal = make_oauth_state(service, organization_id="org-1", identity_id="identity-1")
    with pytest.raises(QuickBooksOAuthError, match="principal"):
        service.complete_authorization(code="code", realm_id="realm", state=wrong_principal, expected_identity_id="identity-2")

    replay = make_oauth_state(service)
    service.complete_authorization(code="code", realm_id="realm", state=replay)
    with pytest.raises(QuickBooksOAuthError, match="already been used"):
        service.complete_authorization(code="code", realm_id="realm", state=replay)


def test_oauth_state_consumption_is_race_safe(monkeypatch):
    seed_two_orgs()
    service = QuickBooksOAuthService()
    monkeypatch.setattr(service, "_exchange_code", _oauth_tokens)
    state = make_oauth_state(service)

    def consume_once():
        try:
            service.complete_authorization(code="code", realm_id="realm", state=state)
            return "ok"
        except QuickBooksOAuthError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: consume_once(), range(2)))

    assert results.count("ok") == 1
    assert any("already been used" in item or "could not be consumed" in item for item in results)
