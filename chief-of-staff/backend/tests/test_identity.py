from uuid import uuid4

from fastapi.testclient import TestClient

from app.events import event_bus
from app.main import app
from tests.auth_helpers import seed_principal


client = TestClient(app)


def create_organization() -> tuple[dict, dict[str, str]]:
    organization, _, headers = seed_principal("owner")
    return organization, headers


def create_identity(headers: dict[str, str], email: str | None = None) -> dict:
    address = email or f"builder-{uuid4().hex[:10]}@example.test"
    response = client.post(
        "/api/v1/identities",
        headers=headers,
        json={"email": address, "display_name": "Polaris Builder"},
    )
    assert response.status_code == 201
    return response.json()


def test_identity_creation_normalizes_email_and_publishes_event():
    _, _, headers = seed_principal("owner")
    email = f"Builder-{uuid4().hex[:10]}@Example.Test"
    identity = create_identity(headers, email)

    assert identity["email"] == email.lower()
    assert identity["status"] == "active"

    event = event_bus.recent(limit=1)[0]
    assert event.event_type == "identity.identity.created.v1"
    assert event.subject.subject_id == identity["id"]
    assert event.payload["email"] == email.lower()


def test_duplicate_identity_email_is_rejected():
    _, _, headers = seed_principal("owner")
    email = f"duplicate-{uuid4().hex[:10]}@example.test"
    create_identity(headers, email)

    response = client.post(
        "/api/v1/identities",
        headers=headers,
        json={"email": email.upper(), "display_name": "Duplicate Builder"},
    )

    assert response.status_code == 409


def test_invalid_identity_email_is_rejected():
    _, _, headers = seed_principal("owner")
    response = client.post(
        "/api/v1/identities",
        headers=headers,
        json={"email": "not-an-email", "display_name": "Invalid Builder"},
    )

    assert response.status_code == 422


def test_membership_is_explicit_tenant_aware_and_unique():
    organization, headers = create_organization()
    identity = create_identity(headers)

    response = client.post(
        f"/api/v1/organizations/{organization['id']}/memberships",
        headers=headers,
        json={"identity_id": identity["id"], "role": "owner"},
    )

    assert response.status_code == 201
    membership = response.json()
    assert membership["organization_id"] == organization["id"]
    assert membership["identity_id"] == identity["id"]
    assert membership["role"] == "owner"

    event = event_bus.recent(limit=1)[0]
    assert event.event_type == "identity.membership.created.v1"
    assert event.organization_id == organization["id"]
    assert event.tenant_id == organization["id"]

    duplicate = client.post(
        f"/api/v1/organizations/{organization['id']}/memberships",
        headers=headers,
        json={"identity_id": identity["id"], "role": "member"},
    )
    assert duplicate.status_code == 409


def test_membership_rejects_unknown_references():
    organization, headers = create_organization()

    response = client.post(
        f"/api/v1/organizations/{organization['id']}/memberships",
        headers=headers,
        json={"identity_id": str(uuid4()), "role": "member"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "identity not found"


def test_memberships_can_be_listed_by_organization():
    organization, headers = create_organization()
    identity = create_identity(headers)
    client.post(
        f"/api/v1/organizations/{organization['id']}/memberships",
        headers=headers,
        json={"identity_id": identity["id"], "role": "viewer"},
    )

    response = client.get(
        f"/api/v1/organizations/{organization['id']}/memberships",
        headers=headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert any(item["role"] == "viewer" for item in response.json())
