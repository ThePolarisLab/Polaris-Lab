"""Application logging integration for the deployed Uvicorn runtime."""

from __future__ import annotations

import json
import logging
from typing import Any

OUTLOOK_TRACE_PHRASES = (
    "Outlook sync authenticated mailbox",
    "Outlook sync fetched message page",
    "Outlook sync message persistence decision",
    "Outlook attention filter decision",
)

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

_SAFE_FIELD_PREFIXES = ("outlook_",)
_SAFE_FIELD_NAMES = {"organization_id"}
_SECRET_MARKERS = ("token", "secret", "authorization", "code", "state", "password")


class OutlookDiagnosticFilter(logging.Filter):
    """Append safe Outlook trace fields to messages Render can search."""

    def filter(self, record: logging.LogRecord) -> bool:
        base_message = record.getMessage()
        if not any(phrase in base_message for phrase in OUTLOOK_TRACE_PHRASES):
            return True
        fields = _safe_extra_fields(record)
        if fields and "diagnostic_fields=" not in base_message:
            record.msg = f"{base_message} diagnostic_fields={json.dumps(fields, sort_keys=True, default=str)}"
            record.args = ()
        return True


def configure_application_logging() -> None:
    """Route app loggers through Uvicorn's configured visible handlers."""
    uvicorn_logger = logging.getLogger("uvicorn.error")
    root_logger = logging.getLogger()
    target_handlers = uvicorn_logger.handlers or root_logger.handlers
    diagnostic_filter = OutlookDiagnosticFilter()
    for handler in target_handlers:
        if not any(isinstance(existing, OutlookDiagnosticFilter) for existing in handler.filters):
            handler.addFilter(diagnostic_filter)

    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False
    app_logger.handlers = list(target_handlers)


def _safe_extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _STANDARD_RECORD_KEYS:
            continue
        if not (key in _SAFE_FIELD_NAMES or key.startswith(_SAFE_FIELD_PREFIXES)):
            continue
        lowered = key.casefold()
        if any(marker in lowered for marker in _SECRET_MARKERS):
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
