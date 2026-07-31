from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.connectors.models import ConnectorStatus
from app.connectors.outlook import OutlookConnector, OutlookConnectorError
from app.connectors.outlook_oauth import READ_ONLY_SCOPE, OutlookOAuthError, OutlookOAuthService
from app.models.outlook import OutlookMessage
from app.services.outlook_sync import _safe_body, classify_message


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
