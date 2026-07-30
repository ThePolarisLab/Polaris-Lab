from uuid import uuid4

from fastapi.testclient import TestClient

from app.database.database import SessionLocal
from app.events import event_bus
from app.main import app
from app.organizations.models import Organization
from tests.auth_helpers import seed_principal


def test_platform_admin_can_create_list_and_get_organization():
    client = TestClient(app)
    _, _, platform_headers = seed_principal("platform_admin")
    slug = f"polaris-test-{uuid4().hex[:8]}"

    response = client.post(
        "/api/v1/organizations",
        headers=platform_headers,
        json={"slug": slug, "display_name": "Polaris Test Organization", "legal_name": "Polaris Test Organization Inc."},
    )

    assert response.status_code == 201
    organization = response.json()
    assert organization["slug"] == slug
    assert organization["status"] == "active"

    fetched = client.get(f"/api/v1/organizations/{organization['id']}", headers=platform_headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == organization["id"]

    listed = client.get("/api/v1/organizations", headers=platform_headers)
    assert listed.status_code == 200
    assert any(item["id"] == organization["id"] for item in listed.json())

    created_event = next(event for event in event_bus.recent(limit=50) if event.subject is not None and event.subject.subject_id == organization["id"])
    assert created_event.event_type == "organization.organization.created.v1"
    assert created_event.organization_id == organization["id"]
    assert created_event.tenant_id == organization["id"]


def test_organization_admin_cannot_create_or_list_other_organizations():
    client = TestClient(app)
    org, _, headers = seed_principal("owner")
    with SessionLocal.begin() as session:
        session.add(Organization(id="other-org", slug="other-org", display_name="Other Org"))

    create = client.post("/api/v1/organizations", headers=headers, json={"slug": "blocked-org", "display_name": "Blocked"})
    listed = client.get("/api/v1/organizations", headers=headers)
    other = client.get("/api/v1/organizations/other-org", headers=headers)

    assert create.status_code == 403
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [org["id"]]
    assert other.status_code == 403


def test_duplicate_slug_is_rejected():
    client = TestClient(app)
    _, _, headers = seed_principal("platform_admin")
    slug = f"duplicate-{uuid4().hex[:8]}"
    payload = {"slug": slug, "display_name": "Duplicate Test"}

    assert client.post("/api/v1/organizations", headers=headers, json=payload).status_code == 201
    duplicate = client.post("/api/v1/organizations", headers=headers, json=payload)

    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]


def test_invalid_slug_and_unknown_organization_are_rejected():
    client = TestClient(app)
    _, _, headers = seed_principal("platform_admin")

    invalid = client.post("/api/v1/organizations", headers=headers, json={"slug": "Not Valid!", "display_name": "Invalid"})
    missing = client.get("/api/v1/organizations/does-not-exist", headers=headers)

    assert invalid.status_code == 422
    assert missing.status_code == 404
