from uuid import uuid4

from fastapi.testclient import TestClient

from app.events import event_bus
from app.main import app


client = TestClient(app)


def create_organization() -> dict:
    suffix = uuid4().hex[:10]
    response = client.post(
        "/api/v1/organizations",
        json={"slug": f"identity-test-{suffix}", "display_name": "Identity Test"},
    )
    assert response.status_code == 201
    return response.json()


def create_identity(email: str | None = None) -> dict:
    address = email or f"builder-{uuid4().hex[:10]}@example.test"
    response = client.post(
        "/api/v1/identities",
        json={"email": address, "display_name": "Polaris Builder"},
    )
    assert response.status_code == 201
    return response.json()


def test_identity_creation_normalizes_email_and_publishes_event():
    email = f"Builder-{uuid4().hex[:10]}@Example.Test"
    identity = create_identity(email)

    assert identity["email"] == email.lower()
    assert identity["status"] == "active"

    event = event_bus.recent(limit=1)[0]
    assert event.event_type == "identity.identity.created.v1"
    assert event.subject.subject_id == identity["id"]
    assert event.payload["email"] == email.lower()


def test_duplicate_identity_email_is_rejected():
    email = f"duplicate-{uuid4().hex[:10]}@example.test"
    create_identity(email)

    response = client.post(
        "/api/v1/identities",
        json={"email": email.upper(), "display_name": "Duplicate Builder"},
    )

    assert response.status_code == 409


def test_invalid_identity_email_is_rejected():
    response = client.post(
        "/api/v1/identities",
        json={"email": "not-an-email", "display_name": "Invalid Builder"},
    )

    assert response.status_code == 422


def test_membership_is_explicit_tenant_aware_and_unique():
    organization = create_organization()
    identity = create_identity()

    response = client.post(
        f"/api/v1/organizations/{organization['id']}/memberships",
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
        json={"identity_id": identity["id"], "role": "member"},
    )
    assert duplicate.status_code == 409


def test_membership_rejects_unknown_references():
    organization = create_organization()

    response = client.post(
        f"/api/v1/organizations/{organization['id']}/memberships",
        json={"identity_id": str(uuid4()), "role": "member"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "identity not found"


def test_memberships_can_be_listed_by_organization():
    organization = create_organization()
    identity = create_identity()
    client.post(
        f"/api/v1/organizations/{organization['id']}/memberships",
        json={"identity_id": identity["id"], "role": "viewer"},
    )

    response = client.get(
        f"/api/v1/organizations/{organization['id']}/memberships"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["role"] == "viewer"
