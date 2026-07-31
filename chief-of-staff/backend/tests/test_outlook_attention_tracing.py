from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.api import outlook as outlook_api
from app.models.outlook import OutlookMessage


def test_attention_filter_reason_reports_recent_test_message() -> None:
    row = OutlookMessage(
        id=101,
        organization_id="org-mor-logistics",
        organization_slug="mor-logistics",
        provider_message_id="graph-message-101",
        subject="Outlook Test 01",
        sender={"address": "sender@example.com"},
        conversation_id="conversation-101",
        received_at=datetime.now(timezone.utc),
        is_draft=False,
        importance="normal",
        evidence={"connector": "outlook", "provider_message_id": "graph-message-101"},
        observed_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        synced_at=datetime.now(timezone.utc),
    )

    reason = outlook_api._attention_filter_reason(
        None,
        "org-mor-logistics",
        "info@morlogistics.ca",
        datetime.now(timezone.utc) - timedelta(hours=24),
        row,
    )

    assert reason == "too_recent_for_followup_threshold"
