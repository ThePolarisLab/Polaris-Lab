from fastapi.testclient import TestClient
import pytest

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


client = TestClient(app)


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


def test_root_exposes_only_public_status():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_reports_only_public_readiness():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_public_runtime_routes_do_not_expose_metadata():
    for path in ("/", "/health"):
        response = client.get(path)
        serialized = response.text.lower()
        assert "service" not in serialized
        assert "version" not in serialized
        assert "environment" not in serialized
        assert "organization" not in serialized
        assert "database" not in serialized
        assert "capabilities" not in serialized


def test_builder_system_health_requires_authentication():
    response = client.get("/api/v1/system/health")

    assert response.status_code == 401


def test_builder_system_health_exposes_timestamped_readiness_when_authenticated():
    headers = seed_identity()
    response = client.get("/api/v1/system/health", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["checks"] == {
        "api": "ready",
        "database": "connected",
    }
    assert payload["checked_at"]


def test_builder_system_info_requires_authentication():
    response = client.get("/api/v1/system/info")

    assert response.status_code == 401


def test_builder_system_info_exposes_non_secret_runtime_metadata_when_authenticated():
    headers = seed_identity()
    response = client.get("/api/v1/system/info", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "Polaris Chief of Staff API"
    assert payload["environment"]
    assert payload["organization"]
    assert payload["started_at"]
    assert payload["uptime_seconds"] >= 0
    assert payload["git_commit"]


def test_builder_system_version_requires_authentication():
    response = client.get("/api/v1/system/version")

    assert response.status_code == 401


def test_builder_system_version_exposes_build_identity_when_authenticated():
    headers = seed_identity()
    response = client.get("/api/v1/system/version", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"]
    assert payload["git_commit"]
