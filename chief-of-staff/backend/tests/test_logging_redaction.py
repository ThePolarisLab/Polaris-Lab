from __future__ import annotations

import io
import logging

from app.core.logging import OutlookDiagnosticFilter, configure_application_logging


def test_uvicorn_access_log_redacts_motive_callback_query_values() -> None:
    diagnostic_filter = OutlookDiagnosticFilter()
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        (
            "127.0.0.1:12345",
            "GET",
            "/api/v1/motive/oauth/callback?code=fake-auth-code&state=fake-oauth-state&client_secret=fake-client-secret&foo=bar",
            "1.1",
            303,
        ),
        None,
    )

    assert diagnostic_filter.filter(record) is True
    rendered = record.getMessage()

    assert "/api/v1/motive/oauth/callback" in rendered
    assert "code=[REDACTED]" in rendered
    assert "state=[REDACTED]" in rendered
    assert "client_secret=[REDACTED]" in rendered
    assert "foo=bar" in rendered
    assert "fake-auth-code" not in rendered
    assert "fake-oauth-state" not in rendered
    assert "fake-client-secret" not in rendered


def test_uvicorn_access_log_does_not_rewrite_non_motive_targets() -> None:
    diagnostic_filter = OutlookDiagnosticFilter()
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:12345", "GET", "/api/v1/quickbooks/callback?code=fake-auth-code&state=fake-oauth-state", "1.1", 303),
        None,
    )

    assert diagnostic_filter.filter(record) is True
    rendered = record.getMessage()

    assert "/api/v1/quickbooks/callback?code=fake-auth-code&state=fake-oauth-state" in rendered


def test_repeated_logging_configuration_does_not_duplicate_handlers_or_messages() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    uvicorn_logger = logging.getLogger("uvicorn.error")
    app_logger = logging.getLogger("app")
    previous_level = app_logger.level
    previous_propagate = app_logger.propagate
    uvicorn_logger.addHandler(handler)
    try:
        configure_application_logging()
        configure_application_logging()

        assert app_logger.handlers.count(handler) == 1
        assert sum(isinstance(item, OutlookDiagnosticFilter) for item in handler.filters) == 1

        app_logger.info(
            "MOTIVE OAUTH CALLBACK",
            extra={
                "motive_oauth_step": "CALLBACK START",
                "code_received": True,
                "state_received": True,
            },
        )
    finally:
        if handler in uvicorn_logger.handlers:
            uvicorn_logger.removeHandler(handler)
        if handler in app_logger.handlers:
            app_logger.removeHandler(handler)
        app_logger.setLevel(previous_level)
        app_logger.propagate = previous_propagate

    rendered = stream.getvalue()
    assert rendered.count("MOTIVE OAUTH CALLBACK") == 1
    assert "step=CALLBACK_START" in rendered
    assert "code_received=true" in rendered
    assert "state_received=true" in rendered


def test_outlook_trace_logging_still_renders_diagnostic_fields(caplog) -> None:
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
                "outlook_messages_fetched": 1,
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
    assert '"outlook_messages_fetched": 1' in rendered
    assert "must-not-log" not in rendered
