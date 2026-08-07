from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.connectors.models import ConnectorStatus
from app.connectors.motive import MOTIVE_USERS_ENDPOINT, MOTIVE_USERS_PER_PAGE, MotiveConnector, MotiveConnectorError
from app.connectors.motive_contracts import MotiveDriver
from app.database.database import Base
from app.identity.models import Identity
from app.models.motive import MotiveDriverRecord, MotiveSyncCheckpoint, MotiveSyncHistory
from app.organizations.models import Organization
from app.security.models import AuthenticatedPrincipal, Permission

FAKE_API_KEY = "fake-motive-company-api-key-for-user-tests-only"


@pytest.fixture()
def motive_user_db(monkeypatch, tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'motive-users.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("MOTIVE_API_KEY", raising=False)
    import app.database.database as database
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


def _principal(organization_id: str = "org-a") -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        identity_id="identity-a",
        organization_id=organization_id,
        membership_id=f"membership-{organization_id}",
        role="admin",
        permissions=frozenset({Permission.CONNECTOR_WRITE}),
        provider="test",
        subject="test-subject",
    )


class _UserListConnector:
    def __init__(self, *, users=None, error: MotiveConnectorError | None = None) -> None:
        self._users = users or []
        self._error = error

    def list_users(self, *, organization_id: str, organization_slug: str):
        if self._error is not None:
            raise self._error
        return {"users": self._users, "pages_read": 1, "records_read": len(self._users), "pagination_total": len(self._users), "driver_classification_certified": False}


def _user(organization_id: str = "org-a", organization_slug: str = "org-a", provider_user_id: str = "user-1") -> MotiveDriver:
    return MotiveDriver(
        organization_id=organization_id,
        organization_slug=organization_slug,
        provider_driver_id=provider_user_id,
        source_endpoint=MOTIVE_USERS_ENDPOINT,
        name="Alex User",
        email="alex@example.com",
        status="active",
        metadata={"driver_classification": "unknown", "driver_classification_certified": False, "role": "uncertified-provider-role"},
    )


def test_user_list_uses_confirmed_endpoint_pagination_and_api_key(monkeypatch):
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        page_no = int(request.url.params["page_no"])
        assert request.url.params["per_page"] == str(MOTIVE_USERS_PER_PAGE)
        assert request.headers["x-api-key"] == FAKE_API_KEY
        if page_no == 1:
            return httpx.Response(200, json={"users": [{"user": {"id": "user-1", "first_name": "Alex", "last_name": "User", "email": "alex@example.com", "role": "field-value-not-classified", "status": "active", "updated_at": "2026-08-07T00:00:00Z"}}], "pagination": {"total": 2}})
        return httpx.Response(200, json={"users": [{"id": "user-2", "username": "sam"}], "pagination": {"total": 2}})

    connector = MotiveConnector(organization_id="org-a", http_client=httpx.Client(transport=httpx.MockTransport(handler)), jitter=lambda: 0)
    result = connector.list_users(organization_id="org-a", organization_slug="org-a")

    assert result["pages_read"] == 2
    assert result["records_read"] == 2
    assert result["driver_classification_certified"] is False
    assert len(calls) == 2
    assert str(calls[0].url) == "https://api.gomotive.com/v1/users?per_page=100&page_no=1"
    assert result["users"][0].provider_driver_id == "user-1"
    assert result["users"][0].name == "Alex User"
    assert result["users"][0].metadata["driver_classification"] == "unknown"
    assert result["users"][0].metadata["driver_classification_certified"] is False
    assert FAKE_API_KEY not in str(result)


def test_user_list_stops_on_empty_page(monkeypatch):
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"users": [], "pagination": {"total": 100}})

    connector = MotiveConnector(organization_id="org-a", http_client=httpx.Client(transport=httpx.MockTransport(handler)), jitter=lambda: 0)
    result = connector.list_users(organization_id="org-a", organization_slug="org-a")

    assert result["pages_read"] == 1
    assert result["records_read"] == 0
    assert len(calls) == 1


def test_user_list_max_page_guard_prevents_infinite_loop(monkeypatch):
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"users": [{"id": "user-1"}], "pagination": {"total": 500}})

    connector = MotiveConnector(organization_id="org-a", http_client=httpx.Client(transport=httpx.MockTransport(handler)), max_user_pages=1, jitter=lambda: 0)
    with pytest.raises(MotiveConnectorError) as exc:
        connector.list_users(organization_id="org-a", organization_slug="org-a")

    assert exc.value.code == "provider_contract_error"


def test_user_list_fails_closed_on_missing_identity(monkeypatch):
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"users": [{"email": "missing-id@example.com"}], "pagination": {"total": 1}})

    connector = MotiveConnector(organization_id="org-a", http_client=httpx.Client(transport=httpx.MockTransport(handler)), jitter=lambda: 0)
    with pytest.raises(MotiveConnectorError) as exc:
        connector.list_users(organization_id="org-a", organization_slug="org-a")

    assert exc.value.code == "provider_contract_error"


def test_user_upsert_is_idempotent_and_org_scoped(motive_user_db):
    from app.api import motive as motive_api

    first = _user()
    same = _user()
    changed = _user()
    changed = MotiveDriver(**{**changed.__dict__, "email": "changed@example.com"})
    other_org = _user(organization_id="org-b", organization_slug="org-b")

    with motive_user_db() as session:
        assert motive_api._upsert_users(session, [first]) == {"records_inserted": 1, "records_updated": 0, "records_unchanged": 0, "records_upserted": 1}
        session.commit()
        assert motive_api._upsert_users(session, [same]) == {"records_inserted": 0, "records_updated": 0, "records_unchanged": 1, "records_upserted": 0}
        assert motive_api._upsert_users(session, [changed]) == {"records_inserted": 0, "records_updated": 1, "records_unchanged": 0, "records_upserted": 1}
        assert motive_api._upsert_users(session, [other_org])["records_inserted"] == 1
        session.commit()
        assert session.query(MotiveDriverRecord).filter_by(organization_id="org-a", provider_driver_id="user-1").one().email == "changed@example.com"
        assert session.query(MotiveDriverRecord).filter_by(provider_driver_id="user-1").count() == 2


def test_user_sync_success_records_counts_checkpoint_and_safe_status(motive_user_db, monkeypatch):
    from app.api import motive as motive_api

    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    monkeypatch.setattr(motive_api, "_connector", lambda _organization_id: _UserListConnector(users=[_user()]))
    with motive_user_db() as session:
        response = motive_api.sync_motive_users(_principal(), session)
        history = session.query(MotiveSyncHistory).filter_by(mode="user_sync", organization_id="org-a").one()
        checkpoint = session.query(MotiveSyncCheckpoint).filter_by(organization_id="org-a", provider_resource="users").one()
        stored_user = session.query(MotiveDriverRecord).filter_by(organization_id="org-a", provider_driver_id="user-1").one()
        status = motive_api._latest_motive_status(session, "org-a")

    assert response["status"] == "success"
    assert response["resource"] == "users"
    assert response["records_upserted"] == 1
    assert response["driver_classification_certified"] is False
    assert response["production_certified"] is False
    assert history.status == "success"
    assert history.provider_resource == "users"
    assert checkpoint.checkpoint_status == "success"
    assert stored_user.source_endpoint == MOTIVE_USERS_ENDPOINT
    assert stored_user.provider_payload_metadata["driver_classification"] == "unknown"
    assert status["user_records_stored"] == 1
    assert status["driver_classification_certified"] is False
    assert "driver_records_stored" not in status


def test_user_sync_upsert_database_exception_records_sanitized_failure(motive_user_db, monkeypatch):
    from app.api import motive as motive_api

    monkeypatch.setattr(motive_api, "_connector", lambda _organization_id: _UserListConnector(users=[_user()]))

    def fail_upsert(_session, _users):
        raise SQLAlchemyError("SELECT password FROM db WHERE x-api-key='raw-secret'")

    monkeypatch.setattr(motive_api, "_upsert_users", fail_upsert)
    with motive_user_db() as session:
        session.add(MotiveSyncCheckpoint(organization_id="org-a", organization_slug="org-a", provider_resource="users", page_number=4, last_successful_position={"page_number": 4}, checkpoint_status="success"))
        session.commit()
        with pytest.raises(HTTPException) as exc:
            motive_api.sync_motive_users(_principal(), session)
        history = session.query(MotiveSyncHistory).filter_by(mode="user_sync", organization_id="org-a").one()
        checkpoint = session.query(MotiveSyncCheckpoint).filter_by(organization_id="org-a", provider_resource="users").one()

    assert exc.value.status_code == 500
    assert exc.value.detail == {"status": "failed", "resource": "users", "error_code": "database_persistence_error", "message": "Motive user sync failed during database persistence."}
    assert "raw-secret" not in str(exc.value.detail)
    assert "x-api-key" not in str(exc.value.detail).lower()
    assert history.status == "failed"
    assert history.error_code == "database_persistence_error"
    assert history.records_written == 0
    assert history.checkpoint_after == history.checkpoint_before
    assert checkpoint.page_number == 4
    assert checkpoint.last_successful_position == {"page_number": 4}


def test_user_sync_final_commit_exception_records_sanitized_failure(motive_user_db, monkeypatch):
    from app.api import motive as motive_api

    monkeypatch.setattr(motive_api, "_connector", lambda _organization_id: _UserListConnector(users=[_user()]))
    with motive_user_db() as session:
        session.add(MotiveSyncCheckpoint(organization_id="org-a", organization_slug="org-a", provider_resource="users", page_number=6, last_successful_position={"page_number": 6}, checkpoint_status="success"))
        session.commit()
        original_commit = session.commit
        calls = {"count": 0}

        def flaky_commit():
            calls["count"] += 1
            if calls["count"] == 2:
                raise SQLAlchemyError("INSERT failed with db-url and secret header")
            return original_commit()

        monkeypatch.setattr(session, "commit", flaky_commit)
        with pytest.raises(HTTPException) as exc:
            motive_api.sync_motive_users(_principal(), session)
        history = session.query(MotiveSyncHistory).filter_by(mode="user_sync", organization_id="org-a").one()
        checkpoint = session.query(MotiveSyncCheckpoint).filter_by(organization_id="org-a", provider_resource="users").one()
        user_count = session.query(MotiveDriverRecord).filter_by(organization_id="org-a").count()

    assert exc.value.status_code == 500
    assert exc.value.detail["error_code"] == "database_persistence_error"
    assert "db-url" not in str(exc.value.detail)
    assert "secret" not in str(exc.value.detail).lower()
    assert history.status == "failed"
    assert history.records_written == 0
    assert history.checkpoint_after == history.checkpoint_before
    assert checkpoint.page_number == 6
    assert checkpoint.last_successful_position == {"page_number": 6}
    assert user_count == 0


def test_user_sync_motive_connector_error_preserves_checkpoint(motive_user_db, monkeypatch):
    from app.api import motive as motive_api

    connector_error = MotiveConnectorError("Motive rate limited user sync", status=ConnectorStatus.RATE_LIMITED, code="rate_limited", retryable=True, http_status=429)
    monkeypatch.setattr(motive_api, "_connector", lambda _organization_id: _UserListConnector(error=connector_error))
    with motive_user_db() as session:
        session.add(MotiveSyncCheckpoint(organization_id="org-a", organization_slug="org-a", provider_resource="users", page_number=3, last_successful_position={"page_number": 3}, checkpoint_status="success"))
        session.commit()
        with pytest.raises(HTTPException) as exc:
            motive_api.sync_motive_users(_principal(), session)
        history = session.query(MotiveSyncHistory).filter_by(mode="user_sync", organization_id="org-a").one()
        checkpoint = session.query(MotiveSyncCheckpoint).filter_by(organization_id="org-a", provider_resource="users").one()

    assert exc.value.status_code == 429
    assert exc.value.detail["error_code"] == "rate_limited"
    assert history.status == "rate_limited"
    assert history.resource_counts == {"users": 0}
    assert history.checkpoint_after == history.checkpoint_before
    assert checkpoint.page_number == 3


def test_user_retry_policy_and_secret_safety(monkeypatch):
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("POLARIS_MOTIVE_MAX_ATTEMPTS", "2")
    sleeps = []
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "1"}, json={"error": "limited"})
        return httpx.Response(200, json={"users": [], "pagination": {"total": 0}})

    connector = MotiveConnector(organization_id="org-a", http_client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=sleeps.append, jitter=lambda: 0)
    result = connector.list_users(organization_id="org-a", organization_slug="org-a")

    assert result["records_read"] == 0
    assert sleeps == [1.0]
    assert len(calls) == 2
    assert FAKE_API_KEY not in str(result)


def test_user_401_and_403_do_not_retry(monkeypatch):
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    for status_code in (401, 403):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(status_code, json={"error": "denied"})

        connector = MotiveConnector(organization_id="org-a", http_client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _seconds: calls.append("sleep"), jitter=lambda: 0)
        with pytest.raises(MotiveConnectorError):
            connector.list_users(organization_id="org-a", organization_slug="org-a")
        assert len([call for call in calls if isinstance(call, httpx.Request)]) == 1
        assert "sleep" not in calls
