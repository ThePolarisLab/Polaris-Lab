import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./polaris-production-auth-existing-org-test.db")
os.environ.setdefault("POLARIS_ENV", "test")
os.environ.setdefault("POLARIS_SESSION_SECRET", "test-session-secret-with-enough-length")
os.environ.setdefault("POLARIS_BOOTSTRAP_ADMIN_EMAIL", "admin@morlogistics.example")
os.environ.setdefault("POLARIS_BOOTSTRAP_SECRET", "bootstrap-secret-with-enough-length")

from fastapi.testclient import TestClient
import pytest

from app.auth.service import BOOTSTRAP_ORGANIZATION_ID
from app.database.database import Base, SessionLocal, engine
from app.main import app
from app.organizations.models import Organization

ADMIN_PASSWORD = "CorrectHorseBattery1"
BOOTSTRAP_SECRET = "bootstrap-secret-with-enough-length"


@pytest.fixture(autouse=True)
def reset_database(monkeypatch):
    monkeypatch.setenv("POLARIS_ENV", "test")
    monkeypatch.setenv("POLARIS_SESSION_SECRET", "test-session-secret-with-enough-length")
    monkeypatch.setenv("POLARIS_BOOTSTRAP_ADMIN_EMAIL", "admin@morlogistics.example")
    monkeypatch.setenv("POLARIS_BOOTSTRAP_SECRET", BOOTSTRAP_SECRET)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def _bootstrap(client):
    return client.post(
        "/api/v1/auth/bootstrap",
        json={"bootstrap_secret": BOOTSTRAP_SECRET, "password": ADMIN_PASSWORD},
    )


def test_bootstrap_repairs_existing_target_organization_with_missing_legal_name(client):
    with SessionLocal.begin() as session:
        session.add(
            Organization(
                id=BOOTSTRAP_ORGANIZATION_ID,
                slug="mor-logistics",
                display_name="MOR Logistics Manitoba Limited",
                legal_name=None,
                status="active",
            )
        )

    response = _bootstrap(client)
    assert response.status_code == 201

    with SessionLocal() as session:
        organization = session.get(Organization, BOOTSTRAP_ORGANIZATION_ID)
        assert organization.slug == "mor-logistics"
        assert organization.display_name == "MOR Logistics"
        assert organization.legal_name == "MOR LOGISTICS MANITOBA LIMITED"


def test_bootstrap_rejects_existing_target_organization_with_material_legal_name_mismatch(client):
    with SessionLocal.begin() as session:
        session.add(
            Organization(
                id=BOOTSTRAP_ORGANIZATION_ID,
                slug="mor-logistics",
                display_name="Different Company",
                legal_name="DIFFERENT COMPANY LIMITED",
                status="active",
            )
        )

    response = _bootstrap(client)
    assert response.status_code == 409
    assert response.json()["detail"] == "existing organization does not match bootstrap target"
