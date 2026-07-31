from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import outlook as outlook_api
from app.connectors.models import ConnectorStatus
from app.connectors.outlook import OutlookConnector, OutlookConnectorError
from app.connectors.outlook_oauth import READ_ONLY_SCOPE, OutlookOAuthError, OutlookOAuthService
from app.database.database import Base
from app.models.outlook import OutlookAttachment, OutlookFolder, OutlookFolderCheckpoint, OutlookMessage, OutlookSyncHistory
from app.organizations.models import Organization
from app.services import outlook_sync
from app.services.outlook_sync import OutlookSyncService, _safe_body, classify_message


def _message(subject: str, body: str = "", *, importance: str = "normal") -> OutlookMessage:
    return OutlookMessage(
        organization_id="org-a",
        organization_slug="tenant-a",
        provider_message_id="msg-1",
        subject=subject,
        sender={"address": "customer@example.com"},
        body_text=body,
        importance=importance,
        has_attachments=False,
        evidence={"connector": "outlook", "provider_message_id": "msg-1"},
        observed_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        synced_at=datetime.now(timezone.utc),
    )


class _FakeOutlookStore:
    def __init__(self) -> None:
        self.successes = 0
        self.failures: list[str] = []

    def record_sync_success(self) -> None:
        self.successes += 1

    def record_sync_failure(self, message: str, *, status: str) -> None:
        self.failures.append(f"{status}:{message}")


class _FakeOutlookConnector:
    def __init__(self) -> None:
        self.store = _FakeOutlookStore()
        self.delta_calls: list[str | None] = []
        self.initial_message_calls = 0

    @contextmanager
    def organization_sync_lock(self):
        yield

    def _store(self) -> _FakeOutlookStore:
        return self.store

    def authenticate(self) -> None:
        return None

    def mailbox_identity(self) -> dict[str, str]:
        return {"mailbox_address": "info@morlogistics.ca"}

    def list_folders(self) -> dict[str, list[dict[str, object]]]:
        return {
            "value": [
                {
                    "id": "folder-inbox",
                    "displayName": "Inbox",
                    "parentFolderId": None,
                    "childFolderCount": 0,
                    "totalItemCount": 0,
                    "unreadItemCount": 0,
                }
            ]
        }

    def list_child_folders(self, folder_id: str, *, url: str | None = None) -> dict[str, list[dict[str, object]]]:
        return {"value": []}

    def list_messages(self, folder_id: str, *, url: str | None = None, since_iso: str | None = None) -> dict[str, object]:
        self.initial_message_calls += 1
        return {"value": [], "@odata.deltaLink": "delta-after-initial"}

    def delta_messages(self, folder_id: str, *, delta_link: str | None = None) -> dict[str, object]:
        self.delta_calls.append(delta_link)
        return {"value": [], "@odata.deltaLink": "delta-after-incremental"}

    def list_attachments(self, message_id: str) -> dict[str, list[dict[str, object]]]:
        return {"value": []}


def test_outlook_initial_then_incremental_sync_persists_folders_once(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'outlook-sync.db').as_posix()}", connect_args={"check_same_thread": False})
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(outlook_sync, "SessionLocal", testing_session)

    with testing_session.begin() as session:
        session.add(
            Organization(
                id="org-mor-logistics-sync-test",
                slug="mor-logistics",
                display_name="MOR Logistics",
                legal_name="MOR LOGISTICS MANITOBA LIMITED",
            )
        )

    connector = _FakeOutlookConnector()
    service = OutlookSyncService(connector=connector, organization_id="org-mor-logistics-sync-test")

    initial = service.sync(mode="initial")
    incremental = service.sync(mode="incremental")

    assert initial.success is True
    assert incremental.success is True
    assert connector.store.successes == 2
    assert connector.store.failures == []
    assert connector.initial_message_calls == 1
    assert connector.delta_calls == ["delta-after-initial"]

    with testing_session() as session:
        folders = session.query(OutlookFolder).filter_by(organization_id="org-mor-logistics-sync-test").all()
        histories = session.query(OutlookSyncHistory).filter_by(organization_id="org-mor-logistics-sync-test").all()
        checkpoint = session.query(OutlookFolderCheckpoint).filter_by(
            organization_id="org-mor-logistics-sync-test",
            provider_folder_id="folder-inbox",
        ).one()

    assert len(folders) == 1
    assert folders[0].organization_slug == "mor-logistics"
    assert folders[0].provider_folder_id == "folder-inbox"
    assert folders[0].is_sync_enabled is True
    assert [history.status for history in histories] == ["success", "success"]
    assert {history.organization_slug for history in histories} == {"mor-logistics"}
    assert checkpoint.organization_slug == "mor-logistics"
    assert checkpoint.delta_link == "delta-after-incremental"


def test_outlook_folder_creation_uses_single_organization_slug_source():
    values = {
        "organization_slug": "mor-logistics",
        "display_name": "Inbox",
        "parent_folder_id": None,
        "well_known_name": "inbox",
        "child_folder_count": 0,
        "total_item_count": 1,
        "unread_item_count": 0,
        "is_sync_enabled": True,
        "synced_at": datetime.now(timezone.utc),
    }

    row = OutlookFolder(
        organization_id="org-mor-logistics",
        provider_folder_id="folder-inbox",
        **values,
    )

    assert row.organization_id == "org-mor-logistics"
    assert row.organization_slug == "mor-logistics"
    assert row.provider_folder_id == "folder-inbox"


def test_outlook_attachment_creation_uses_single_organization_slug_source():
    values = {
        "organization_slug": "mor-logistics",
        "filename": "pod.pdf",
        "mime_type": "application/pdf",
        "size": 1234,
        "is_inline": False,
        "content_id": None,
        "attachment_type": "#microsoft.graph.fileAttachment",
        "synced_at": datetime.now(timezone.utc),
    }

    row = OutlookAttachment(
        organization_id="org-mor-logistics",
        message_id=42,
        provider_attachment_id="attachment-1",
        **values,
    )

    assert row.organization_id == "org-mor-logistics"
    assert row.organization_slug == "mor-logistics"
    assert row.provider_attachment_id == "attachment-1"


def test_attachment_metadata_request_uses_base_attachment_select(monkeypatch):
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = request.headers
        return httpx.Response(200, json={"value": []}, request=request)

    connector = OutlookConnector(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    connector.authenticate = lambda: None
    connector._access_token = "safe-access-token"

    assert connector.list_attachments("message 1") == {"value": []}

    parsed = urlparse(str(captured["url"]))
    query = parse_qs(parsed.query)
    selected = set(query["$select"][0].split(","))

    assert parsed.scheme == "https"
    assert parsed.netloc == "graph.microsoft.com"
    assert parsed.path == "/v1.0/me/messages/message%201/attachments"
    assert query["$top"] == ["100"]
    assert selected == {"id", "name", "contentType", "size", "isInline", "lastModifiedDateTime"}
    assert "contentId" not in selected
    headers = captured["headers"]
    assert headers["Authorization"] == "Bearer safe-access-token"
    assert headers["Accept"] == "application/json"
    assert headers["client-request-id"].startswith("outlook-")
    assert headers["X-Polaris-Correlation"] == headers["client-request-id"]


def test_attachment_metadata_graph_error_payload_is_logged(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": "Request_UnsupportedQuery",
                    "message": "Could not find a property named 'contentId' on type 'microsoft.graph.attachment'.",
                    "innerError": {"request-id": "graph-request-123"},
                }
            },
            request=request,
        )

    connector = OutlookConnector(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    connector.authenticate = lambda: None
    connector._access_token = "safe-access-token"

    with caplog.at_level(logging.WARNING, logger="app.connectors.outlook"):
        with pytest.raises(OutlookConnectorError) as exc:
            connector.list_attachments("message-1")

    message = str(exc.value)
    assert exc.value.status == ConnectorStatus.DEGRADED
    assert "Request_UnsupportedQuery" in message
    assert "contentId" in message
    assert "graph-request-123" in message
    assert "safe-access-token" not in message
    assert "Request_UnsupportedQuery" in caplog.text
    assert "graph-request-123" in caplog.text
    assert "safe-access-token" not in caplog.text


def test_default_outlook_scope_is_read_only():
    scopes = set(READ_ONLY_SCOPE.split())

    assert "https://graph.microsoft.com/Mail.Read" in scopes
    assert not any("Mail.ReadWrite" in scope or "Mail.Send" in scope for scope in scopes)


def test_outlook_configuration_rejects_write_scopes(monkeypatch):
    monkeypatch.setenv("POLARIS_OUTLOOK_CLIENT_ID", "client-id")
    monkeypatch.setenv("POLARIS_OUTLOOK_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("POLARIS_OUTLOOK_REDIRECT_URI", "https://example.test/api/v1/outlook/callback")
    monkeypatch.setenv("POLARIS_OUTLOOK_OAUTH_STATE_SECRET", "x" * 40)
    monkeypatch.setenv("POLARIS_OUTLOOK_TOKEN_ENCRYPTION_KEY", "credential-key-placeholder")
    monkeypatch.setenv("POLARIS_OUTLOOK_SCOPES", "openid offline_access https://graph.microsoft.com/Mail.ReadWrite")

    with pytest.raises(OutlookConnectorError) as exc:
        OutlookConnector().validate_configuration()

    assert exc.value.status == ConnectorStatus.CONFIGURATION_ERROR
    assert "read-only" in str(exc.value)


def test_outlook_oauth_configuration_rejects_write_scopes(monkeypatch):
    monkeypatch.setenv("POLARIS_OUTLOOK_CLIENT_ID", "client-id")
    monkeypatch.setenv("POLARIS_OUTLOOK_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("POLARIS_OUTLOOK_REDIRECT_URI", "https://example.test/api/v1/outlook/callback")
    monkeypatch.setenv("POLARIS_OUTLOOK_OAUTH_STATE_SECRET", "x" * 40)
    monkeypatch.setenv("POLARIS_OUTLOOK_TOKEN_ENCRYPTION_KEY", "credential-key-placeholder")
    monkeypatch.setenv("POLARIS_OUTLOOK_SCOPES", "openid offline_access https://graph.microsoft.com/Mail.Send")

    with pytest.raises(OutlookOAuthError):
        OutlookOAuthService._validate_configuration()


def test_outlook_rejects_non_graph_continuation_url_before_authentication():
    connector = OutlookConnector()

    def fail_authenticate():
        raise AssertionError("authenticate must not run for unsafe provider URLs")

    connector.authenticate = fail_authenticate

    with pytest.raises(OutlookConnectorError) as exc:
        connector._request_absolute_json("GET", "https://attacker.example/messages", operation="message delta")

    assert exc.value.status == ConnectorStatus.DEGRADED
    assert "unsafe provider continuation URL" in str(exc.value)


def test_outlook_accepts_configured_graph_continuation_path():
    connector = OutlookConnector()
    url = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$skiptoken=abc"

    assert connector._validated_graph_url(url, "message delta") == url


def test_attention_mailbox_lookup_uses_metadata_without_decrypting(monkeypatch):
    class FakeStore:
        def __init__(self, organization_id: str) -> None:
            self.organization_id = organization_id

        def metadata(self) -> dict[str, object]:
            return {"mailbox_address": "Executive@Example.COM"}

        def load_credential(self):
            raise AssertionError("attention reads must not decrypt refresh-token credentials")

    monkeypatch.setattr(outlook_api, "OutlookCredentialStore", FakeStore)

    assert outlook_api._mailbox_address("org-a") == "executive@example.com"


def test_deterministic_classification_allows_multiple_categories():
    classifications = classify_message(_message("Invoice claim for damaged delivery", "payment is overdue after POD dispute"))
    categories = {item["category"] for item in classifications}

    assert {"Invoice", "Payment", "Collections", "POD", "Claim"}.issubset(categories)
    assert all(item["reason"] and item["rule"] for item in classifications)


def test_deterministic_classification_preserves_unclassified_fallback():
    classifications = classify_message(_message("Tuesday note", "see you then"))

    assert classifications == [
        {
            "category": "unclassified",
            "confidence": "low",
            "reason": "No deterministic rule matched",
            "rule": "unclassified_fallback",
        }
    ]


def test_source_high_importance_creates_attention_classification():
    classifications = classify_message(_message("FYI", "neutral text", importance="high"))

    assert any(item["category"] == "High Importance" and item["confidence"] == "high" for item in classifications)


def test_body_is_sanitized_and_bounded(monkeypatch):
    monkeypatch.setenv("POLARIS_OUTLOOK_MAX_BODY_BYTES", "16")

    body, truncated = _safe_body("<p>Hello&nbsp;<b>dispatch</b> team with a long body</p>")

    assert "<" not in body
    assert "dispatch" in body
    assert len(body.encode("utf-8")) <= 16
    assert truncated is True


def test_safe_connector_error_redacts_token_material():
    error = OutlookConnectorError("failed with access_token=abc refresh_token=def Authorization: Bearer secret-token")

    assert "abc" not in str(error)
    assert "def" not in str(error)
    assert "secret-token" not in str(error)
    assert "[REDACTED]" in str(error)
