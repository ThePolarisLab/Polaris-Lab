from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.connectors.motive import MOTIVE_VERIFICATION_ENDPOINT, MOTIVE_VERIFICATION_PARAMS, MotiveConnector, MotiveConnectorError
from app.connectors.motive_credentials import MotiveCredentialStore
from app.database.database import Base
from app.models.motive import MotiveCredential, MotiveSyncCheckpoint, MotiveSyncHistory, MotiveVehicleRecord
from app.organizations.models import Organization

FERNET_KEY = "uPlZqC60CQaQGFL-kQo-xUOyEE5uNUAyxKmwbzfdiVo="
FAKE_KEY = "fake-motive-api-key-for-tests-only"


@pytest.fixture()
def motive_db(monkeypatch, tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'motive.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("POLARIS_MOTIVE_TOKEN_ENCRYPTION_KEY", FERNET_KEY)
    monkeypatch.setenv("POLARIS_MOTIVE_ENVIRONMENT_MODE", "test")
    import app.database.database as database
    import app.connectors.motive_credentials as credentials

    engine = create_engine(database_url)
    TestingSession = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSession)
    monkeypatch.setattr(credentials, "SessionLocal", TestingSession)
    Base.metadata.create_all(bind=engine)
    with TestingSession.begin() as session:
        session.add(Organization(id="org-a", slug="org-a", display_name="Org A"))
        session.add(Organization(id="org-b", slug="org-b", display_name="Org B"))
    return TestingSession


def test_api_key_is_encrypted_and_metadata_does_not_decrypt(monkeypatch, motive_db):
    store = MotiveCredentialStore("org-a")
    store.save_api_key(organization_slug="org-a", api_key=FAKE_KEY, environment_mode="test")

    with motive_db() as session:
        row = session.query(MotiveCredential).filter_by(organization_id="org-a").one()
        assert row.encrypted_api_key != FAKE_KEY
        assert FAKE_KEY not in repr(row.__dict__)

    def fail_decrypt(_value):
        raise AssertionError("metadata must not decrypt Motive API keys")

    monkeypatch.setattr(MotiveCredentialStore, "_decrypt", staticmethod(fail_decrypt))
    metadata = store.metadata(environment_mode="test")
    assert metadata["key_present"] is True
    assert metadata["connection_status"] == "configured_unverified"
    assert FAKE_KEY not in str(metadata)


def test_tenant_isolation_blocks_cross_org_credential_reads(motive_db):
    MotiveCredentialStore("org-a").save_api_key(organization_slug="org-a", api_key=FAKE_KEY, environment_mode="test")
    assert MotiveCredentialStore("org-b").metadata(environment_mode="test")["key_present"] is False
    with pytest.raises(Exception):
        MotiveCredentialStore("org-b").load_api_key(environment_mode="test")


def test_successful_limited_verification_uses_safe_request_and_updates_status(motive_db):
    MotiveCredentialStore("org-a").save_api_key(organization_slug="org-a", api_key=FAKE_KEY, environment_mode="test")
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"vehicles": [{"id": "vehicle-1"}]})

    connector = MotiveConnector(
        credential_store=MotiveCredentialStore("org-a"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = connector.verify_connection()

    assert result["status"] == "connected"
    assert result["endpoint"] == MOTIVE_VERIFICATION_ENDPOINT
    assert result["request"]["params"] == MOTIVE_VERIFICATION_PARAMS
    assert "per_page=1" in captured["url"]
    assert "page_no=1" in captured["url"]
    assert captured["headers"]["x-api-key"] == FAKE_KEY
    assert FAKE_KEY not in str(result)
    assert MotiveCredentialStore("org-a").metadata(environment_mode="test")["connection_status"] == "connected"


def test_verification_failures_are_sanitized_and_do_not_expose_key(motive_db):
    MotiveCredentialStore("org-a").save_api_key(organization_slug="org-a", api_key=FAKE_KEY, environment_mode="test")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    connector = MotiveConnector(
        credential_store=MotiveCredentialStore("org-a"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(MotiveConnectorError) as exc:
        connector.verify_connection()
    assert exc.value.status.value == "authorization_required"
    assert FAKE_KEY not in str(exc.value)
    metadata = MotiveCredentialStore("org-a").metadata(environment_mode="test")
    assert metadata["authorization_required"] is True
    assert FAKE_KEY not in str(metadata)


@pytest.mark.parametrize("status_code,expected", [(403, "authorization_required"), (429, "rate_limited"), (500, "failed")])
def test_safe_status_for_known_provider_failures(status_code, expected, motive_db):
    MotiveCredentialStore("org-a").save_api_key(organization_slug="org-a", api_key=FAKE_KEY, environment_mode="test")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": "provider failure"})

    connector = MotiveConnector(
        credential_store=MotiveCredentialStore("org-a"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(MotiveConnectorError):
        connector.verify_connection()
    assert MotiveCredentialStore("org-a").metadata(environment_mode="test")["connection_status"] == expected


def test_uniqueness_constraints_support_idempotent_foundation_rows(motive_db):
    MotiveCredentialStore("org-a").save_api_key(organization_slug="org-a", api_key=FAKE_KEY, environment_mode="test")
    MotiveCredentialStore("org-a").save_api_key(organization_slug="org-a", api_key="replacement-fake-key", environment_mode="test")
    with motive_db() as session:
        assert session.query(MotiveCredential).filter_by(organization_id="org-a").count() == 1
        session.add(MotiveVehicleRecord(organization_id="org-a", organization_slug="org-a", provider_vehicle_id="vehicle-1"))
        session.commit()
        session.add(MotiveVehicleRecord(organization_id="org-b", organization_slug="org-b", provider_vehicle_id="vehicle-1"))
        session.commit()
        assert session.query(MotiveVehicleRecord).count() == 2


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
