from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.api import outlook as outlook_api
from app.core.logging import OutlookDiagnosticFilter
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


def test_outlook_trace_messages_emit_safe_fields_at_info_level(caplog) -> None:
    logger = logging.getLogger("app.services.outlook_sync")
    diagnostic_filter = OutlookDiagnosticFilter()
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addFilter(diagnostic_filter)
    caplog.set_level(logging.INFO, logger="app.services.outlook_sync")
    try:
        logger.info(
            "Outlook sync fetched message page",
            extra={
                "organization_id": "org-mor-logistics",
                "outlook_sync_run_id": "outlook-run-1",
                "outlook_messages_fetched": 1,
                "outlook_message_subjects": [
                    {
                        "provider_message_id": "graph-message-101",
                        "subject": "Outlook Test 01",
                        "has_attachments": False,
                    }
                ],
                "outlook_refresh_token": "must-not-log",
                "authorization": "must-not-log",
            },
        )
    finally:
        logger.removeFilter(diagnostic_filter)
        logger.setLevel(previous_level)

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "Outlook sync fetched message page" in rendered
    assert "diagnostic_fields=" in rendered
    assert '"organization_id": "org-mor-logistics"' in rendered
    assert '"outlook_messages_fetched": 1' in rendered
    assert "Outlook Test 01" in rendered
    assert "must-not-log" not in rendered


def test_all_outlook_trace_phrases_are_render_searchable(caplog) -> None:
    logger = logging.getLogger("app.api.outlook")
    diagnostic_filter = OutlookDiagnosticFilter()
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addFilter(diagnostic_filter)
    caplog.set_level(logging.INFO, logger="app.api.outlook")
    try:
        for phrase in (
            "Outlook sync authenticated mailbox",
            "Outlook sync fetched message page",
            "Outlook sync message persistence decision",
            "Outlook attention filter decision",
        ):
            logger.info(
                phrase,
                extra={
                    "organization_id": "org-mor-logistics",
                    "outlook_provider_message_id": "graph-message-101",
                    "outlook_message_subject": "Outlook Test 01",
                },
            )
    finally:
        logger.removeFilter(diagnostic_filter)
        logger.setLevel(previous_level)

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    for phrase in (
        "Outlook sync authenticated mailbox",
        "Outlook sync fetched message page",
        "Outlook sync message persistence decision",
        "Outlook attention filter decision",
    ):
        assert phrase in rendered
    assert rendered.count("diagnostic_fields=") == 4
