"""Application logging integration for the deployed Uvicorn runtime."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

OUTLOOK_TRACE_PHRASES = (
    "Outlook sync authenticated mailbox",
    "Outlook sync fetched message page",
    "Outlook sync message persistence decision",
    "Outlook attention filter decision",
)
MOTIVE_TRACE_PHRASE = "MOTIVE OAUTH CALLBACK"
MOTIVE_CALLBACK_PATH = "/api/v1/motive/oauth/callback"

_STANDARD_RECORD_KEYS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}

_SAFE_FIELD_PREFIXES = ("outlook_", "motive_oauth_")
_SAFE_FIELD_NAMES = {
    "access_token_encrypted",
    "access_token_received",
    "authentication_method",
    "authorization_required",
    "code_received",
    "connection_status",
    "credential_created",
    "credential_row_exists",
    "error_code",
    "exception_class",
    "expires_in",
    "expires_in_present",
    "failing_step",
    "http_status",
    "organization_id",
    "organization_matches",
    "organization_slug",
    "provider_error_received",
    "redirect_uri_present",
    "refresh_token_encrypted",
    "refresh_token_received",
    "response_keys",
    "rollback_executed",
    "state_received",
    "status_endpoint_reads_same_row",
    "step",
    "token_received",
    "token_type",
}
_SECRET_MARKERS = ("token", "secret", "authorization", "code", "state", "password")
_SECRET_FIELD_ALLOWLIST = {
    "access_token_encrypted",
    "access_token_received",
    "code_received",
    "refresh_token_encrypted",
    "refresh_token_received",
    "state_received",
    "token_received",
    "token_type",
}
_REDACTED_QUERY_PARAMS = {"access_token", "client_secret", "code", "refresh_token", "state"}


class OutlookDiagnosticFilter(logging.Filter):
    """Append safe connector diagnostics and redact OAuth callback access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        _redact_access_log_record(record)
        base_message = record.getMessage()
        if any(phrase in base_message for phrase in OUTLOOK_TRACE_PHRASES):
            _append_json_diagnostic_fields(record, base_message)
            return True
        if MOTIVE_TRACE_PHRASE in base_message:
            _append_logfmt_diagnostic_fields(record, base_message)
        return True


def configure_application_logging() -> None:
    """Make app logs visible in Uvicorn without hiding them from test capture."""
    uvicorn_logger = logging.getLogger("uvicorn.error")
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    root_logger = logging.getLogger()
    app_logger = logging.getLogger("app")
    diagnostic_filter = OutlookDiagnosticFilter()

    for handler in (*uvicorn_logger.handlers, *uvicorn_access_logger.handlers, *root_logger.handlers, *app_logger.handlers):
        _add_filter_once(handler, diagnostic_filter)

    for handler in uvicorn_logger.handlers:
        if handler not in app_logger.handlers:
            app_logger.addHandler(handler)
            _add_filter_once(handler, diagnostic_filter)

    for handler in uvicorn_access_logger.handlers:
        _add_filter_once(handler, diagnostic_filter)

    app_logger.setLevel(logging.INFO)
    app_logger.propagate = True
    uvicorn_access_logger.propagate = True


def _add_filter_once(handler: logging.Handler, diagnostic_filter: OutlookDiagnosticFilter) -> None:
    if not any(isinstance(existing, OutlookDiagnosticFilter) for existing in handler.filters):
        handler.addFilter(diagnostic_filter)


def _append_json_diagnostic_fields(record: logging.LogRecord, base_message: str) -> None:
    fields = _safe_extra_fields(record)
    if fields and "diagnostic_fields=" not in base_message:
        record.msg = f"{base_message} diagnostic_fields={json.dumps(fields, sort_keys=True, default=str)}"
        record.args = ()


def _append_logfmt_diagnostic_fields(record: logging.LogRecord, base_message: str) -> None:
    fields = _safe_extra_fields(record)
    if fields and " step=" not in base_message:
        rendered_fields = " ".join(f"{key}={_logfmt_value(value)}" for key, value in sorted(fields.items()))
        record.msg = f"{base_message} {rendered_fields}"
        record.args = ()


def _safe_extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _STANDARD_RECORD_KEYS:
            continue
        if not (key in _SAFE_FIELD_NAMES or key.startswith(_SAFE_FIELD_PREFIXES)):
            continue
        lowered = key.casefold()
        if key not in _SECRET_FIELD_ALLOWLIST and any(marker in lowered for marker in _SECRET_MARKERS):
            continue
        fields[key] = _coerce_safe_value(value)
    return fields


def _coerce_safe_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_coerce_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _coerce_safe_value(item) for key, item in value.items()}
    return str(value)


def _logfmt_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, dict)):
        return quote(json.dumps(value, sort_keys=True, default=str), safe="[]{}:,_-.\"")
    text = str(value)
    return quote(text, safe="[]{}:,_-./")


def _redact_access_log_record(record: logging.LogRecord) -> None:
    if record.name != "uvicorn.access" or not record.args:
        return
    if not isinstance(record.args, tuple):
        return
    redacted_args = tuple(_redact_motive_callback_target(arg) if isinstance(arg, str) else arg for arg in record.args)
    if redacted_args != record.args:
        record.args = redacted_args


def _redact_motive_callback_target(target: str) -> str:
    parsed = urlsplit(target)
    if parsed.path != MOTIVE_CALLBACK_PATH:
        return target
    if not parsed.query:
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", parsed.fragment))
    query_parts = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        safe_key = quote(key, safe="")
        if key in _REDACTED_QUERY_PARAMS:
            query_parts.append(f"{safe_key}=[REDACTED]")
        else:
            query_parts.append(f"{safe_key}={quote(value, safe='')}")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "&".join(query_parts), parsed.fragment))
