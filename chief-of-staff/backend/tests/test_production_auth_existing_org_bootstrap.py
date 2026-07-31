import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./polaris-production-auth-existing-org-test.db")
os.environ.setdefault("POLARIS_ENV", "test")
os.environ.setdefault("POLARIS_SESSION_SECRET", "test-session-secret-with-enough-length")
os.environ.setdefault("POLARIS_BOOTSTRAP_ADMIN_EMAIL", "admin@morlogistics.example")
os.environ.setdefault("POLARIS_BOOTSTRAP_SECRET", "bootstrap-secret-with-enough-length")

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event

from app.auth.models import ProductionAuthBootstrapState, ProductionPasswordCredential
from app.auth.service import BOOTSTRAP_IDENTITY_ID, BOOTSTRAP_ORGANIZATION_ID
from app.database.database import Base, SessionLocal, engine
from app.identity.models import Identity, OrganizationMembership
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


def test_bootstrap_flushes_identity_before_password_credential(client):
    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        if "INSERT INTO identities" in statement or "INSERT INTO production_password_credentials" in statement:
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        response = _bootstrap(client)
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    assert response.status_code == 201
    identity_insert_index = next(index for index, statement in enumerate(statements) if "INSERT INTO identities" in statement)
    credential_insert_index = next(
        index for index, statement in enumerate(statements) if "INSERT INTO production_password_credentials" in statement
    )
    assert identity_insert_index < credential_insert_index

    with SessionLocal() as session:
        assert session.get(Identity, BOOTSTRAP_IDENTITY_ID) is not None
        assert session.get(ProductionPasswordCredential, BOOTSTRAP_IDENTITY_ID) is not None


def test_bootstrap_inserts_identity_before_completion_marker(client):
    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        if "INSERT INTO identities" in statement or "INSERT INTO production_auth_bootstrap_state" in statement:
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        response = _bootstrap(client)
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    assert response.status_code == 201
    identity_insert_index = next(index for index, statement in enumerate(statements) if "INSERT INTO identities" in statement)
    marker_insert_index = next(index for index, statement in enumerate(statements) if "INSERT INTO production_auth_bootstrap_state" in statement)
    assert identity_insert_index < marker_insert_index

    with SessionLocal() as session:
        assert session.get(Identity, BOOTSTRAP_IDENTITY_ID) is not None
        assert session.get(Organization, BOOTSTRAP_ORGANIZATION_ID) is not None
        assert session.get(ProductionAuthBootstrapState, "first-admin") is not None
        assert session.query(OrganizationMembership).filter_by(
            organization_id=BOOTSTRAP_ORGANIZATION_ID,
            identity_id=BOOTSTRAP_IDENTITY_ID,
        ).one()


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
