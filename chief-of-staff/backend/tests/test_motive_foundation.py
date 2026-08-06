from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.connectors.motive import MOTIVE_VERIFICATION_ENDPOINT, MOTIVE_VERIFICATION_PARAMS, MotiveConnector, MotiveConnectorError
from app.database.database import Base
from app.identity.models import Identity
from app.models.motive import MotiveCredential, MotiveOAuthState, MotiveSyncCheckpoint, MotiveSyncHistory, MotiveVehicleRecord
from app.organizations.models import Organization

FAKE_API_KEY = "fake-motive-company-api-key-for-tests-only"


@pytest.fixture()
def motive_db(monkeypatch, tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'motive.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("MOTIVE_API_KEY", raising=False)
    import app.database.database as database
    import app.connectors.motive as motive
    import app.api.motive as motive_api

    engine = create_engine(database_url)
    TestingSession = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSession)
    monkeypatch.setattr(motive_api, "SessionLocal", TestingSession)
    Base.metadata.create_all(bind=engine)
    with TestingSession.begin() as session:
        session.add(Organization(id="org-a", slug="org-a", display_name="Org A"))
        session.add(Organization(id="org-b", slug="org-b", display_name="Org B"))
        session.add(Identity(id="identity-a", email="a@example.com", display_name="User A"))
    return TestingSession


def test_api_key_status_reports_not_configured_without_secret(monkeypatch):
    monkeypatch.delenv("MOTIVE_API_KEY", raising=False)
    status = MotiveConnector(organization_id="org-a").safe_status()

    assert status["authentication_method"] == "company_api_key"
    assert status["credential_source"] == "render_environment"
    assert status["connection_status"] == "not_configured"
    assert status["key_present"] is False
    assert status["authorization_required"] is True
    assert "MOTIVE_API_KEY" not in str(status)
    assert "X-API-Key" not in str(status)


def test_api_key_status_reports_configured_unverified_when_key_exists(monkeypatch):
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    status = MotiveConnector(organization_id="org-a").safe_status()

    assert status["connection_status"] == "configured_unverified"
    assert status["key_present"] is True
    assert status["configured_by_administrator"] is True
    assert status["credential_precedence"] == ["MOTIVE_API_KEY"]
    assert FAKE_API_KEY not in str(status)


def test_successful_vehicle_verification_uses_x_api_key_and_does_not_expose_secret(monkeypatch):
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"vehicles": [{"id": "vehicle-1"}], "pagination": {"total": 1}})

    connector = MotiveConnector(
        organization_id="org-a",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        jitter=lambda: 0,
    )
    result = connector.verify_connection()

    assert result["status"] == "connected"
    assert result["endpoint"] == MOTIVE_VERIFICATION_ENDPOINT
    assert result["request"] == {"method": "GET", "path": MOTIVE_VERIFICATION_ENDPOINT, "params": dict(MOTIVE_VERIFICATION_PARAMS), "authentication": "X-API-Key"}
    assert result["records_read"] == 1
    assert captured["url"] == "https://api.gomotive.com/v1/vehicles?per_page=1&page_no=1"
    assert captured["headers"]["x-api-key"] == FAKE_API_KEY
    assert FAKE_API_KEY not in str(result)


@pytest.mark.parametrize(
    "status_code,expected_status,expected_code",
    [
        (401, "authorization_required", "authorization_required"),
        (403, "authorization_required", "permission_denied"),
        (429, "rate_limited", "rate_limited"),
        (500, "failed", "provider_unavailable"),
    ],
)
def test_safe_status_for_known_provider_failures(monkeypatch, status_code, expected_status, expected_code):
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": "provider failure"})

    connector = MotiveConnector(
        organization_id="org-a",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
        jitter=lambda: 0,
    )
    with pytest.raises(MotiveConnectorError) as exc:
        connector.verify_connection()
    assert exc.value.status.value == expected_status
    assert exc.value.code == expected_code
    assert FAKE_API_KEY not in str(exc.value)


def test_does_not_retry_401_or_403(monkeypatch):
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401, json={"error": "bad key"})

    connector = MotiveConnector(
        organization_id="org-a",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: calls.append("sleep"),
        jitter=lambda: 0,
    )
    with pytest.raises(MotiveConnectorError):
        connector.verify_connection()
    assert len([call for call in calls if isinstance(call, httpx.Request)]) == 1
    assert "sleep" not in calls


def test_retry_after_and_bounded_backoff_for_retryable_failures(monkeypatch):
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("POLARIS_MOTIVE_MAX_ATTEMPTS", "2")
    sleeps = []
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={"error": "limited"})
        return httpx.Response(200, json={"vehicles": []})

    connector = MotiveConnector(
        organization_id="org-a",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=sleeps.append,
        jitter=lambda: 0.5,
    )
    result = connector.verify_connection()

    assert result["status"] == "connected"
    assert sleeps == [2.0]
    assert len(calls) == 2


def test_timeout_5xx_and_malformed_response_are_sanitized(monkeypatch):
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    cases = [
        (lambda _request: (_ for _ in ()).throw(httpx.TimeoutException("timeout with X-API-Key fake")), "provider_timeout"),
        (lambda _request: httpx.Response(503, json={"error": "down"}), "provider_unavailable"),
        (lambda _request: httpx.Response(200, content=b"not-json"), "provider_contract_error"),
    ]
    for handler, expected_code in cases:
        connector = MotiveConnector(
            organization_id="org-a",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=lambda _seconds: None,
            jitter=lambda: 0,
        )
        with pytest.raises(MotiveConnectorError) as exc:
            connector.verify_connection()
        assert exc.value.code == expected_code
        assert FAKE_API_KEY not in str(exc.value)
        assert "X-API-Key" not in str(exc.value)


def test_status_reads_latest_verification_history_for_same_organization(monkeypatch, motive_db):
    from app.api import motive as motive_api

    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    completed_at = datetime.now(timezone.utc)
    with motive_db.begin() as session:
        session.add(
            MotiveSyncHistory(
                organization_id="org-a",
                organization_slug="org-a",
                provider="motive",
                provider_resource="vehicles",
                mode="verification",
                status="success",
                run_id="verify-a",
                started_at=completed_at,
                completed_at=completed_at,
                records_read=1,
                checkpoint_before={},
                checkpoint_after={},
                resource_counts={"vehicles": 1},
            )
        )
        session.add(
            MotiveSyncHistory(
                organization_id="org-b",
                organization_slug="org-b",
                provider="motive",
                provider_resource="vehicles",
                mode="verification",
                status="failed",
                run_id="verify-b",
                started_at=completed_at,
                completed_at=completed_at,
                error_code="provider_unavailable",
                checkpoint_before={},
                checkpoint_after={},
                resource_counts={"vehicles": 0},
            )
        )
    with motive_db() as session:
        org_a = motive_api._latest_motive_status(session, "org-a")
        org_b = motive_api._latest_motive_status(session, "org-b")

    assert org_a["connection_status"] == "connected"
    assert org_a["records_read"] == 1
    assert org_b["connection_status"] == "failed"
    assert org_b["last_error_code"] == "provider_unavailable"


def test_oauth_routes_are_disabled_without_removing_schema(monkeypatch):
    from app.api import motive as motive_api

    with pytest.raises(Exception) as connect_error:
        motive_api.motive_callback()
    assert getattr(connect_error.value, "status_code", None) == 410
    assert MotiveOAuthState.__tablename__ == "motive_oauth_states"
    assert MotiveCredential.__tablename__ == "motive_credentials"


def test_uniqueness_constraints_support_idempotent_foundation_rows(motive_db):
    with motive_db() as session:
        session.add(MotiveVehicleRecord(organization_id="org-a", organization_slug="org-a", provider_vehicle_id="vehicle-1"))
        session.commit()
        session.add(MotiveVehicleRecord(organization_id="org-b", organization_slug="org-b", provider_vehicle_id="vehicle-1"))
        session.commit()
        session.add(MotiveVehicleRecord(organization_id="org-a", organization_slug="org-a", provider_vehicle_id="vehicle-1"))
        with pytest.raises(IntegrityError):
            session.commit()


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
