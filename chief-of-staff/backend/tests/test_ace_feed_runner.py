import os
import time

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./polaris-ace-feed-test.db")
os.environ.setdefault("POLARIS_ENV", "test")
os.environ.setdefault("POLARIS_LOCAL_AUTH_SECRET", "test-local-auth-secret-with-enough-length")
os.environ.setdefault("POLARIS_QBO_CLIENT_ID", "client-id")
os.environ.setdefault("POLARIS_QBO_CLIENT_SECRET", "client-secret")
os.environ.setdefault("POLARIS_QBO_REDIRECT_URI", "http://localhost:8000/api/v1/connectors/quickbooks/oauth/callback")
os.environ.setdefault("POLARIS_QBO_OAUTH_STATE_SECRET", "quickbooks-state-secret-with-enough-length")
os.environ.setdefault("POLARIS_QBO_TOKEN_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

from fastapi.testclient import TestClient

from app.ace.feed_runner import AceFeedConfigurationError, ace_feed_health, resolve_configured_organization, run_ace_daily_import
from app.database.database import Base, SessionLocal, engine
from app.identity.models import Identity, OrganizationMembership
from app.main import app
from app.models.ace import AceFeedRun, AceImportRun, AceInBondEvent, AceInBondMovement
from app.organizations.models import Organization, OrganizationStatus
from app.security.job_auth import JobAuthenticationError, sign_job_request, verify_job_signature
from app.security.providers import LocalTokenProvider
from test_ace_outlook_import import ACE_REPORT_SUBJECT, FakeAceOutlookConnector, _attachment, _message, _raw_row, _xlsx


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal.begin() as session:
        session.add(Organization(id="org-1", slug="mor", display_name="MOR"))
        session.add(Organization(id="org-2", slug="other", display_name="Other"))
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def _headers(organization_id="org-1", identity_id="identity-1"):
    with SessionLocal.begin() as session:
        session.add(Identity(id=identity_id, email=f"{identity_id}@example.test", display_name=identity_id))
        session.add(OrganizationMembership(id=f"member-{identity_id}", organization_id=organization_id, identity_id=identity_id, role="owner"))
    token = LocalTokenProvider().issue(identity_id)
    return {"Authorization": f"Bearer {token}", "X-Polaris-Organization": organization_id}


def _connector(message_id="message-1", *, content=None):
    content = content or _xlsx()
    return FakeAceOutlookConnector(
        messages=[_message(message_id)],
        attachments={message_id: [_attachment("attachment-1")]},
        content={(message_id, "attachment-1"): content},
    )


def test_configured_organization_resolves_by_active_slug_and_fails_closed(monkeypatch):
    with SessionLocal() as session:
        monkeypatch.setenv("POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG", "mor")
        assert resolve_configured_organization(session).id == "org-1"
        monkeypatch.delenv("POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG")
        with pytest.raises(AceFeedConfigurationError, match="missing_organization_configuration"):
            resolve_configured_organization(session)
        monkeypatch.setenv("POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG", "missing")
        with pytest.raises(AceFeedConfigurationError, match="organization_not_found"):
            resolve_configured_organization(session)


def test_automatic_run_invokes_existing_importer_and_records_safe_success():
    with SessionLocal() as session:
        result = run_ace_daily_import(session, "org-1", connector=_connector(), mode="automatic")

    assert result.status == "import_success"
    assert result.exit_code == 0
    assert result.records_read == 1
    assert result.records_inserted == 1
    assert result.exceptions_created == 1
    with SessionLocal() as session:
        feed = session.query(AceFeedRun).one()
        assert feed.mode == "automatic"
        assert feed.status == "import_success"
        assert feed.source_found is True
        assert feed.error_category is None
        assert session.query(AceImportRun).count() == 1
        assert session.query(AceInBondMovement).count() == 1
        assert session.query(AceInBondEvent).filter_by(event_type="exception_opened").count() == 1


def test_scheduled_second_run_is_idempotent_and_does_not_duplicate_events():
    with SessionLocal() as session:
        first = run_ace_daily_import(session, "org-1", connector=_connector(), mode="automatic")
        second = run_ace_daily_import(session, "org-1", connector=_connector(), mode="automatic")

    assert first.status == "import_success"
    assert second.status == "already_processed"
    assert second.exit_code == 0
    with SessionLocal() as session:
        assert session.query(AceFeedRun).count() == 2
        assert session.query(AceImportRun).count() == 1
        assert session.query(AceInBondMovement).count() == 1
        assert session.query(AceInBondEvent).filter_by(event_type="first_seen").count() == 1
        assert session.query(AceInBondEvent).filter_by(event_type="exception_opened").count() == 1


def test_manual_and_automatic_collision_replay_remains_idempotent(client):
    headers = _headers()
    connector = _connector()
    with SessionLocal() as session:
        automatic = run_ace_daily_import(session, "org-1", connector=connector, mode="automatic")
    assert automatic.status == "import_success"

    import app.api.ace as ace_api

    ace_api.OutlookConnector = lambda credential_store=None: _connector()
    try:
        response = client.post("/ace/import/outlook-latest", headers=headers)
    finally:
        from app.connectors.outlook import OutlookConnector

        ace_api.OutlookConnector = OutlookConnector

    assert response.status_code == 200
    assert response.json()["status"] == "already_processed"
    with SessionLocal() as session:
        assert session.query(AceFeedRun).count() == 2
        assert session.query(AceImportRun).count() == 1
        assert session.query(AceInBondMovement).count() == 1


def test_no_report_and_source_failure_are_recorded_without_movement_writes():
    no_report = FakeAceOutlookConnector(messages=[], attachments={}, content={})
    with SessionLocal() as session:
        result = run_ace_daily_import(session, "org-1", connector=no_report, mode="automatic")
    assert result.status == "no_source_found"
    assert result.exit_code == 0

    unavailable = FakeAceOutlookConnector(messages=[_message("bad", subject=ACE_REPORT_SUBJECT, has_attachments=False)], attachments={}, content={})
    with SessionLocal() as session:
        failed = run_ace_daily_import(session, "org-1", connector=unavailable, mode="automatic")
    assert failed.status == "source_contract_error"
    assert failed.exit_code == 1
    with SessionLocal() as session:
        assert session.query(AceFeedRun).count() == 2
        assert session.query(AceInBondMovement).count() == 0
        assert session.query(AceFeedRun).filter_by(status="source_contract_error").one().error_category == "source_contract_error"


def test_parser_failure_creates_no_movement_writes_and_preserves_manual_fields():
    with SessionLocal() as session:
        run_ace_daily_import(session, "org-1", connector=_connector(), mode="automatic")
        movement = session.query(AceInBondMovement).one()
        movement.authorization_status = "UNAUTHORIZED - NO MOR PERMISSION"
        movement.authorization_notes = "manual note"
        movement.evidence_reference = "manual evidence"
        movement.resolution_notes = "manual resolution"
        session.commit()

    bad_content = _xlsx(rows=[_raw_row(**{"Days Late": "abc"})])
    with SessionLocal() as session:
        failed = run_ace_daily_import(session, "org-1", connector=_connector("message-2", content=bad_content), mode="automatic")

    assert failed.status == "source_contract_error"
    with SessionLocal() as session:
        movement = session.query(AceInBondMovement).one()
        assert movement.authorization_status == "UNAUTHORIZED - NO MOR PERMISSION"
        assert movement.authorization_notes == "manual note"
        assert movement.evidence_reference == "manual evidence"
        assert movement.resolution_notes == "manual resolution"
        assert movement.penalty_indicator is None


def test_feed_health_is_organization_scoped_and_failed_run_does_not_replace_success():
    with SessionLocal() as session:
        run_ace_daily_import(session, "org-1", connector=_connector(), mode="automatic")
        first_health = ace_feed_health(session, "org-1")
        run_ace_daily_import(session, "org-1", connector=_connector("message-2", content=_xlsx(rows=[_raw_row(**{"Days Late": "abc"})])), mode="automatic")
        failed_health = ace_feed_health(session, "org-1")
        other_health = ace_feed_health(session, "org-2")

    assert first_health["status"] == "healthy"
    assert failed_health["status"] == "error"
    assert failed_health["latest_successful_import_at"] == first_health["latest_successful_import_at"]
    assert other_health["status"] == "unknown"
    assert "message" not in str(failed_health).lower()
    assert other_health["records_read"] == 0


def test_no_mutating_outlook_scope_or_daily_brief_success_noise():
    with SessionLocal() as session:
        run_ace_daily_import(session, "org-1", connector=_connector(), mode="automatic")
    from app.connectors.outlook import OutlookConnector

    assert OutlookConnector.discover(OutlookConnector()) == ("mailbox", "folders", "messages", "attachments", "delta", "attention")
    with SessionLocal() as session:
        feed_run = session.query(AceFeedRun).one()
        assert feed_run.status == "import_success"
        assert session.query(AceInBondMovement).count() == 1


def _scheduled_headers(secret="scheduled-secret", *, timestamp=None, path="/api/v1/internal/ace/daily-feed/run", body=b""):
    timestamp = str(int(time.time())) if timestamp is None else str(timestamp)
    return {
        "X-Polaris-Job-Timestamp": timestamp,
        "X-Polaris-Job-Signature": sign_job_request(method="POST", path=path, body=body, timestamp=timestamp, secret=secret),
    }


def test_job_hmac_authentication_rejects_missing_config_and_bad_headers(monkeypatch):
    monkeypatch.delenv("POLARIS_ACE_CRON_TRIGGER_SECRET", raising=False)
    with pytest.raises(JobAuthenticationError, match="machine authentication unavailable"):
        verify_job_signature(method="POST", path="/api/v1/internal/ace/daily-feed/run", body=b"", timestamp="1", signature="0" * 64, now=1)

    monkeypatch.setenv("POLARIS_ACE_CRON_TRIGGER_SECRET", "scheduled-secret")
    with pytest.raises(JobAuthenticationError):
        verify_job_signature(method="POST", path="/api/v1/internal/ace/daily-feed/run", body=b"", timestamp=None, signature="0" * 64, now=1)
    with pytest.raises(JobAuthenticationError):
        verify_job_signature(method="POST", path="/api/v1/internal/ace/daily-feed/run", body=b"", timestamp="not-a-time", signature="0" * 64, now=1)
    with pytest.raises(JobAuthenticationError):
        verify_job_signature(method="POST", path="/api/v1/internal/ace/daily-feed/run", body=b"", timestamp="1", signature=None, now=1)
    with pytest.raises(JobAuthenticationError):
        verify_job_signature(method="POST", path="/api/v1/internal/ace/daily-feed/run", body=b"", timestamp="1", signature="not-hex", now=1)
    with pytest.raises(JobAuthenticationError):
        verify_job_signature(method="POST", path="/api/v1/internal/ace/daily-feed/run", body=b"", timestamp="1", signature="0" * 64, now=1)


def test_job_hmac_authentication_rejects_stale_and_future_timestamps(monkeypatch):
    monkeypatch.setenv("POLARIS_ACE_CRON_TRIGGER_SECRET", "scheduled-secret")
    old_headers = _scheduled_headers(timestamp=100)
    with pytest.raises(JobAuthenticationError):
        verify_job_signature(
            method="POST",
            path="/api/v1/internal/ace/daily-feed/run",
            body=b"",
            timestamp=old_headers["X-Polaris-Job-Timestamp"],
            signature=old_headers["X-Polaris-Job-Signature"],
            now=401,
        )

    future_headers = _scheduled_headers(timestamp=701)
    with pytest.raises(JobAuthenticationError):
        verify_job_signature(
            method="POST",
            path="/api/v1/internal/ace/daily-feed/run",
            body=b"",
            timestamp=future_headers["X-Polaris-Job-Timestamp"],
            signature=future_headers["X-Polaris-Job-Signature"],
            now=400,
        )


def test_scheduled_trigger_resolves_configured_org_and_records_scheduled_mode(client, monkeypatch):
    monkeypatch.setenv("POLARIS_ACE_CRON_TRIGGER_SECRET", "scheduled-secret")
    monkeypatch.setenv("POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG", "mor")

    import app.api.internal_ace as internal_ace_api

    internal_ace_api.OutlookConnector = None
    original = internal_ace_api.run_ace_daily_import
    internal_ace_api.run_ace_daily_import = lambda db, organization_id, mode="automatic": run_ace_daily_import(
        db, organization_id, connector=_connector(), mode=mode
    )
    try:
        response = client.post("/api/v1/internal/ace/daily-feed/run", headers=_scheduled_headers())
    finally:
        internal_ace_api.run_ace_daily_import = original

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "status": "import_success",
        "source_found": True,
        "replayed": False,
        "records_read": 1,
        "records_inserted": 1,
        "records_updated": 0,
        "exceptions_created": 1,
        "secrets_exposed": False,
    }
    serialized = response.text.lower()
    assert "message-1" not in serialized
    assert "inbond" not in serialized
    assert "bol" not in serialized
    assert "scheduled-secret" not in serialized
    with SessionLocal() as session:
        feed = session.query(AceFeedRun).one()
        assert feed.mode == "scheduled"
        assert feed.organization_id == "org-1"


def test_scheduled_trigger_accepts_no_tenant_selector_and_ignores_request_body(client, monkeypatch):
    monkeypatch.setenv("POLARIS_ACE_CRON_TRIGGER_SECRET", "scheduled-secret")
    monkeypatch.setenv("POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG", "mor")
    body = b'{"organization_id":"org-2","organization_slug":"other"}'

    import app.api.internal_ace as internal_ace_api

    observed = {}
    original = internal_ace_api.run_ace_daily_import

    def fake_runner(db, organization_id, mode="automatic"):
        observed["organization_id"] = organization_id
        return run_ace_daily_import(db, organization_id, connector=_connector(), mode=mode)

    internal_ace_api.run_ace_daily_import = fake_runner
    try:
        response = client.post(
            "/api/v1/internal/ace/daily-feed/run",
            headers=_scheduled_headers(body=body),
            content=body,
        )
    finally:
        internal_ace_api.run_ace_daily_import = original

    assert response.status_code == 200
    assert observed["organization_id"] == "org-1"
    with SessionLocal() as session:
        assert session.query(AceInBondMovement).filter_by(organization_id="org-2").count() == 0


def test_scheduled_trigger_fails_closed_for_missing_unknown_and_inactive_org(client, monkeypatch):
    monkeypatch.setenv("POLARIS_ACE_CRON_TRIGGER_SECRET", "scheduled-secret")
    monkeypatch.delenv("POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG", raising=False)
    assert client.post("/api/v1/internal/ace/daily-feed/run", headers=_scheduled_headers()).status_code == 503

    monkeypatch.setenv("POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG", "missing")
    assert client.post("/api/v1/internal/ace/daily-feed/run", headers=_scheduled_headers()).status_code == 503

    with SessionLocal.begin() as session:
        session.query(Organization).filter_by(id="org-1").one().status = OrganizationStatus.SUSPENDED.value
    monkeypatch.setenv("POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG", "mor")
    assert client.post("/api/v1/internal/ace/daily-feed/run", headers=_scheduled_headers()).status_code == 503


def test_scheduled_trigger_rejects_bad_authentication(client, monkeypatch):
    monkeypatch.setenv("POLARIS_ACE_CRON_TRIGGER_SECRET", "scheduled-secret")
    monkeypatch.setenv("POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG", "mor")

    assert client.post("/api/v1/internal/ace/daily-feed/run").status_code == 401
    assert client.post(
        "/api/v1/internal/ace/daily-feed/run",
        headers={"X-Polaris-Job-Timestamp": str(int(time.time())), "X-Polaris-Job-Signature": "0" * 64},
    ).status_code == 401


def test_scheduled_trigger_no_report_replay_and_source_failure_are_safe(client, monkeypatch):
    monkeypatch.setenv("POLARIS_ACE_CRON_TRIGGER_SECRET", "scheduled-secret")
    monkeypatch.setenv("POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG", "mor")

    import app.api.internal_ace as internal_ace_api

    original = internal_ace_api.run_ace_daily_import
    internal_ace_api.run_ace_daily_import = lambda db, organization_id, mode="automatic": run_ace_daily_import(
        db, organization_id, connector=FakeAceOutlookConnector(messages=[], attachments={}, content={}), mode=mode
    )
    try:
        no_report = client.post("/api/v1/internal/ace/daily-feed/run", headers=_scheduled_headers())
    finally:
        internal_ace_api.run_ace_daily_import = original
    assert no_report.status_code == 200
    assert no_report.json()["status"] == "no_source_found"

    internal_ace_api.run_ace_daily_import = lambda db, organization_id, mode="automatic": run_ace_daily_import(
        db,
        organization_id,
        connector=FakeAceOutlookConnector(messages=[_message("bad", subject=ACE_REPORT_SUBJECT, has_attachments=False)], attachments={}, content={}),
        mode=mode,
    )
    try:
        failed = client.post("/api/v1/internal/ace/daily-feed/run", headers=_scheduled_headers())
    finally:
        internal_ace_api.run_ace_daily_import = original
    assert failed.status_code == 502
    assert failed.json()["status"] == "source_contract_error"
    assert "bad" not in failed.text


def test_duplicate_scheduled_and_manual_replay_do_not_duplicate_movements_or_events(client, monkeypatch):
    monkeypatch.setenv("POLARIS_ACE_CRON_TRIGGER_SECRET", "scheduled-secret")
    monkeypatch.setenv("POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG", "mor")

    import app.api.ace as ace_api
    import app.api.internal_ace as internal_ace_api

    original_scheduled = internal_ace_api.run_ace_daily_import
    internal_ace_api.run_ace_daily_import = lambda db, organization_id, mode="automatic": run_ace_daily_import(
        db, organization_id, connector=_connector(), mode=mode
    )
    try:
        first = client.post("/api/v1/internal/ace/daily-feed/run", headers=_scheduled_headers())
        second = client.post("/api/v1/internal/ace/daily-feed/run", headers=_scheduled_headers())
    finally:
        internal_ace_api.run_ace_daily_import = original_scheduled
    assert first.json()["status"] == "import_success"
    assert second.json()["status"] == "already_processed"

    headers = _headers()
    original_manual = ace_api.OutlookConnector
    ace_api.OutlookConnector = lambda credential_store=None: _connector()
    try:
        manual = client.post("/ace/import/outlook-latest", headers=headers)
    finally:
        ace_api.OutlookConnector = original_manual

    assert manual.status_code == 200
    assert manual.json()["status"] == "already_processed"
    with SessionLocal() as session:
        assert session.query(AceImportRun).count() == 1
        assert session.query(AceInBondMovement).count() == 1
        assert session.query(AceInBondEvent).filter_by(event_type="first_seen").count() == 1
        assert session.query(AceInBondEvent).filter_by(event_type="exception_opened").count() == 1
