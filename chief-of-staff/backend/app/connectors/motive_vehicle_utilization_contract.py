"""Verification-only Motive vehicle utilization contract inspection.

This module performs one bounded read-only request and returns only sanitized
schema metadata. It must not persist utilization data or expose provider values.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Sequence
from datetime import date
from typing import Any

import httpx

from app.connectors.models import ConnectorStatus
from app.connectors.motive import MOTIVE_API_BASE_URL, MotiveConnectorError, _api_key, _retry_after_seconds, _timeout_seconds

logger = logging.getLogger(__name__)

MOTIVE_VEHICLE_UTILIZATION_ENDPOINT = "/v1/vehicle_utilization"
MOTIVE_VEHICLE_UTILIZATION_CONTRACT_PARAMS = {"per_page": 1, "page_no": 1}
MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES = 3
MOTIVE_VEHICLE_UTILIZATION_METRICS = ("utilization", "idle_time", "idle_fuel", "driving_time", "driving_fuel")
MOTIVE_VEHICLE_UTILIZATION_PERIOD_KEYS = {
    "date",
    "end",
    "end_date",
    "end_time",
    "end_timestamp",
    "period_end",
    "period_start",
    "reporting_end",
    "reporting_period_end",
    "reporting_period_start",
    "reporting_start",
    "start",
    "start_date",
    "start_time",
    "start_timestamp",
    "timestamp",
}
MOTIVE_VEHICLE_UTILIZATION_REQUEST_WINDOW_TIME_ZONE = "America/Winnipeg"
"""Polaris-local calendar for choosing the temporary verification request window.

This is not asserted to equal Motive's company-configured rollup timezone.
Motive documents vehicle-utilization rollups as computed in the company's
configured rollup timezone and not controlled by X-Time-Zone.
"""
PROVIDER_400_GENERIC_MESSAGE = "Provider rejected request parameters or required context."
PROVIDER_400_MESSAGE_BY_CATEGORY = {
    "missing_user_context": "Provider requires additional authorized user context.",
    "missing_date_parameter": "Provider requires date parameters for this request.",
    "invalid_date_parameter": "Provider rejected the supplied date parameters.",
    "missing_vehicle_parameter": "Provider requires vehicle context for this request.",
    "invalid_vehicle_parameter": "Provider rejected the supplied vehicle parameter.",
    "invalid_pagination_parameter": "Provider rejected the supplied pagination parameters.",
    "permission_context_required": "Provider requires additional authorization context.",
    "invalid_request_parameters": "Provider rejected request parameters.",
    "unknown_provider_rejection": PROVIDER_400_GENERIC_MESSAGE,
}
PROVIDER_400_SEMANTIC_FIELDS = (
    "mentions_header",
    "mentions_parameter",
    "mentions_user_context",
    "mentions_vehicle_context",
    "mentions_date_context",
    "mentions_permission_context",
    "mentions_required_or_missing",
    "mentions_invalid_or_rejected",
)
_PROVIDER_ERROR_MESSAGE_KEYS = {"error", "error_message", "errormessage", "message", "detail", "description"}
_SCHEMA_COMPATIBLE = "compatible"
_SCHEMA_INSUFFICIENT_IDENTITY = "insufficient_identity"
_SCHEMA_INCOMPLETE_PROVIDER_SCHEMA = "incomplete_provider_schema"
_SECRET_KEY_MARKERS = ("token", "secret", "authorization", "api_key", "x-api-key", "credential")
_SENSITIVE_MESSAGE_MARKERS = _SECRET_KEY_MARKERS + (
    "bearer",
    "header",
    "headers",
    "vehicle_ids",
    "vehicle_id",
    "start_date",
    "end_date",
    "x-user-id",
    "x-time-zone",
    "x-metric-units",
    "vin",
    "plate",
    "license",
    "email",
)
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)
_LONG_NUMBER_RE = re.compile(r"\b\d{6,}\b")
_TOKENISH_RE = re.compile(r"\b[A-Za-z0-9_-]{24,}\b")
_VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.IGNORECASE)
_SHORT_CODE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def verify_vehicle_utilization_contract(
    *,
    organization_id: str,
    provider_vehicle_ids: Sequence[str],
    start_date: date,
    end_date: date,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Make exactly one read-only provider call and summarize the response schema."""
    selected_provider_vehicle_ids = [provider_vehicle_id for provider_vehicle_id in provider_vehicle_ids if provider_vehicle_id]
    try:
        payload, http_status = request_vehicle_utilization_payload(
            organization_id=organization_id,
            provider_vehicle_ids=selected_provider_vehicle_ids,
            start_date=start_date,
            end_date=end_date,
            per_page=MOTIVE_VEHICLE_UTILIZATION_CONTRACT_PARAMS["per_page"],
            http_client=http_client,
        )
    except MotiveConnectorError as exc:
        logger.info(
            "MOTIVE VEHICLE UTILIZATION CONTRACT VERIFY",
            extra={
                "motive_operation": "vehicle_utilization_contract_verify",
                "organization_id": organization_id,
                "http_status": exc.http_status,
                "response_type": None,
                "item_count": 0,
                "schema_compatibility": exc.code,
            },
        )
        raise
    summary = _summarize_contract_payload(payload)
    logger.info(
        "MOTIVE VEHICLE UTILIZATION CONTRACT VERIFY",
        extra={
            "motive_operation": "vehicle_utilization_contract_verify",
            "organization_id": organization_id,
            "http_status": http_status,
            "response_type": summary["top_level_type"],
            "item_count": summary["item_count_observed"],
            "schema_compatibility": summary["schema_compatibility"],
        },
    )
    return {
        "status": "success",
        "endpoint": MOTIVE_VEHICLE_UTILIZATION_ENDPOINT,
        "provider_vehicle_selected": True,
        "provider_vehicle_selected_count": len(selected_provider_vehicle_ids),
        "vehicle_id_redacted": True,
        "request_period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        "request_shape": {
            "method": "GET",
            "path": MOTIVE_VEHICLE_UTILIZATION_ENDPOINT,
            "params": {"vehicle_ids[]": "[REDACTED]", "start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "per_page": 1, "page_no": 1},
            "headers": {"Accept": "application/json", "X-Metric-Units": _metric_units_header(), "X-API-Key": "[REDACTED]"},
            "max_provider_attempts": 1,
        },
        **summary,
        "secrets_exposed": False,
    }


def request_vehicle_utilization_payload(
    *,
    organization_id: str,
    provider_vehicle_ids: Sequence[str],
    start_date: date,
    end_date: date,
    per_page: int,
    http_client: httpx.Client | None = None,
) -> tuple[Any, int]:
    """Perform one no-retry vehicle-utilization provider request and return decoded JSON internally."""
    selected_provider_vehicle_ids = [provider_vehicle_id for provider_vehicle_id in provider_vehicle_ids if provider_vehicle_id]
    if not selected_provider_vehicle_ids:
        raise MotiveConnectorError("Motive vehicle utilization request requires a stored vehicle id", status=ConnectorStatus.FAILED, code="provider_contract_error")
    if len(selected_provider_vehicle_ids) > MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES:
        raise MotiveConnectorError("Motive vehicle utilization request is limited to three stored vehicle ids", status=ConnectorStatus.FAILED, code="provider_contract_error")
    if per_page < 1 or per_page > MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES:
        raise MotiveConnectorError("Motive vehicle utilization request per_page is limited to the selected vehicle bound", status=ConnectorStatus.FAILED, code="provider_contract_error")
    params: list[tuple[str, str]] = [("vehicle_ids[]", provider_vehicle_id) for provider_vehicle_id in selected_provider_vehicle_ids]
    params.extend(
        [
            ("start_date", start_date.isoformat()),
            ("end_date", end_date.isoformat()),
            ("per_page", str(per_page)),
            ("page_no", str(MOTIVE_VEHICLE_UTILIZATION_CONTRACT_PARAMS["page_no"])),
        ]
    )
    headers = {"Accept": "application/json", "X-API-Key": _api_key()}
    metric_units = _metric_units_header()
    if metric_units:
        headers["X-Metric-Units"] = metric_units
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=_timeout_seconds())
    try:
        response = client.get(f"{_base_url()}{MOTIVE_VEHICLE_UTILIZATION_ENDPOINT}", params=params, headers=headers)
        payload = _contract_json_response(response)
        logger.info(
            "MOTIVE VEHICLE UTILIZATION REQUEST",
            extra={
                "motive_operation": "vehicle_utilization_provider_request",
                "organization_id": organization_id,
                "http_status": response.status_code,
                "selected_vehicle_count": len(selected_provider_vehicle_ids),
                "page_no": MOTIVE_VEHICLE_UTILIZATION_CONTRACT_PARAMS["page_no"],
                "per_page": per_page,
            },
        )
        return payload, response.status_code
    except httpx.TimeoutException as exc:
        raise MotiveConnectorError("Motive vehicle utilization request timed out", status=ConnectorStatus.FAILED, retryable=False, code="provider_timeout") from exc
    except httpx.HTTPError as exc:
        raise MotiveConnectorError("Motive vehicle utilization request failed due to a network error", status=ConnectorStatus.FAILED, retryable=False, code="network_failure") from exc
    finally:
        if owns_client:
            client.close()


def _metric_units_header() -> str | None:
    return os.getenv("POLARIS_MOTIVE_X_METRIC_UNITS")


def _contract_json_response(response: httpx.Response) -> Any:
    retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
    if response.status_code == 400:
        exc = MotiveConnectorError("Motive vehicle utilization contract request failed with HTTP 400", status=ConnectorStatus.FAILED, retryable=False, code="http_400", http_status=400)
        exc.provider_diagnostics = _provider_400_diagnostics(response)  # type: ignore[attr-defined]
        raise exc
    if response.status_code == 429:
        raise MotiveConnectorError("Motive vehicle utilization contract request was rate limited", status=ConnectorStatus.RATE_LIMITED, retryable=False, code="rate_limited", http_status=429, retry_after=retry_after)
    if response.status_code in {401, 403}:
        raise MotiveConnectorError(
            f"Motive vehicle utilization contract authorization failed with HTTP {response.status_code}",
            status=ConnectorStatus.AUTHORIZATION_REQUIRED,
            retryable=False,
            code="permission_denied" if response.status_code == 403 else "authorization_required",
            http_status=response.status_code,
        )
    if response.status_code in {500, 502, 503, 504}:
        raise MotiveConnectorError("Motive vehicle utilization contract provider unavailable", status=ConnectorStatus.FAILED, retryable=False, code="provider_unavailable", http_status=response.status_code)
    if response.status_code >= 400:
        raise MotiveConnectorError(f"Motive vehicle utilization contract request failed with HTTP {response.status_code}", status=ConnectorStatus.FAILED, retryable=False, code=f"http_{response.status_code}", http_status=response.status_code)
    if not response.content:
        raise MotiveConnectorError("Motive vehicle utilization contract returned an empty response", status=ConnectorStatus.FAILED, retryable=False, code="provider_contract_error", http_status=response.status_code)
    try:
        decoded = response.json()
    except ValueError as exc:
        raise MotiveConnectorError("Motive vehicle utilization contract returned invalid JSON", status=ConnectorStatus.FAILED, retryable=False, code="provider_contract_error", http_status=response.status_code) from exc
    if not isinstance(decoded, (dict, list)):
        raise MotiveConnectorError("Motive vehicle utilization contract returned an unexpected response shape", status=ConnectorStatus.FAILED, retryable=False, code="provider_contract_error", http_status=response.status_code)
    return decoded


def _provider_400_diagnostics(response: httpx.Response) -> dict[str, Any]:
    payload = _safe_json_payload(response)
    if not isinstance(payload, (dict, list)):
        return _generic_provider_400_diagnostics()
    keys = _safe_error_paths(payload)
    message_candidates = _message_candidates(payload)
    category = _message_category(message_candidates, keys)
    diagnostics: dict[str, Any] = {
        "provider_error_keys": keys,
        "provider_error_message_category": category,
        "provider_error_message": PROVIDER_400_MESSAGE_BY_CATEGORY[category],
        "provider_error_semantics": _provider_error_semantics(message_candidates, keys),
    }
    code = _provider_error_code(payload)
    if code is not None:
        diagnostics["provider_error_code"] = code
    return diagnostics


def _generic_provider_400_diagnostics() -> dict[str, Any]:
    return {
        "provider_error_keys": [],
        "provider_error_message_category": "unknown_provider_rejection",
        "provider_error_message": PROVIDER_400_GENERIC_MESSAGE,
        "provider_error_semantics": _empty_provider_error_semantics(),
    }


def _safe_json_payload(response: httpx.Response) -> Any:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _safe_error_paths(value: Any, *, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            if not _safe_schema_key(key_text):
                continue
            path = f"{prefix}.{key_text}" if prefix else key_text
            paths.append(path)
            if isinstance(nested, dict):
                paths.extend(_safe_error_paths(nested, prefix=path))
            elif isinstance(nested, list) and nested and isinstance(nested[0], dict):
                paths.extend(_safe_error_paths(nested[0], prefix=f"{path}[]"))
    elif isinstance(value, list) and value and isinstance(value[0], dict):
        paths.extend(_safe_error_paths(value[0], prefix=prefix))
    return sorted(set(paths))[:20]


def _message_candidates(value: Any, *, from_message_key: bool = False) -> list[str]:
    candidates: list[str] = []
    if isinstance(value, str):
        if from_message_key:
            candidates.append(" ".join(value.split()))
        return candidates
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            if lowered in _PROVIDER_ERROR_MESSAGE_KEYS:
                candidates.extend(_message_candidates(nested, from_message_key=True))
            elif isinstance(nested, (dict, list)):
                candidates.extend(_message_candidates(nested))
    elif isinstance(value, list):
        for item in value[:5]:
            candidates.extend(_message_candidates(item, from_message_key=from_message_key))
    return candidates[:10]


def _provider_error_code(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("code", "error_code", "errorCode", "type", "status"):
        candidate = value.get(key)
        if isinstance(candidate, (str, int)):
            text = str(candidate).strip()
            if _SHORT_CODE_RE.match(text) and _is_safe_provider_message(text):
                return text
    return None


def _message_category(messages: list[str], keys: list[str]) -> str:
    text = _normalized_provider_error_text(messages, keys)
    has_required = any(marker in text for marker in ("required", "missing", "must include", "must provide", "is required"))
    has_invalid = any(marker in text for marker in ("invalid", "not valid", "bad", "rejected", "unsupported"))
    if any(marker in text for marker in ("x-user-id", "x user id", "user id", "fleet admin", "fleet manager", "user context")) and has_required:
        return "missing_user_context"
    if any(marker in text for marker in ("permission", "authorization", "authorized", "not authorized", "access", "forbidden", "context")) and any(marker in text for marker in ("required", "missing", "denied", "not authorized", "cannot access", "forbidden")):
        return "permission_context_required"
    if any(marker in text for marker in ("start_date", "start date", "end_date", "end date", "date parameter", "date parameters")) and has_required:
        return "missing_date_parameter"
    if any(marker in text for marker in ("date range", "start_date", "start date", "end_date", "end date", "date")) and has_invalid:
        return "invalid_date_parameter"
    if any(marker in text for marker in ("vehicle_ids", "vehicle ids", "vehicle_id", "vehicle id", "vehicle")) and has_required:
        return "missing_vehicle_parameter"
    if any(marker in text for marker in ("vehicle_ids", "vehicle ids", "vehicle_id", "vehicle id", "vehicle")) and has_invalid:
        return "invalid_vehicle_parameter"
    if any(marker in text for marker in ("page_no", "page no", "page number", "per_page", "per page", "pagination")) and (has_required or has_invalid):
        return "invalid_pagination_parameter"
    if any(marker in text for marker in ("parameter", "parameters", "param", "request")) and (has_required or has_invalid):
        return "invalid_request_parameters"
    if "malformed" in text or "bad request" in text:
        return "invalid_request_parameters"
    return "unknown_provider_rejection"


def _provider_error_semantics(messages: list[str], keys: list[str]) -> dict[str, bool]:
    text = _normalized_semantic_text(messages, keys)
    return {
        "mentions_header": _mentions_any(text, ("header", "x user id", "user header")),
        "mentions_parameter": _mentions_any(text, ("parameter", "param", "field", "argument", "query")),
        "mentions_user_context": _mentions_any(text, ("user", "user id", "x user id", "admin", "fleet manager", "fleet user", "role")),
        "mentions_vehicle_context": _mentions_any(text, ("vehicle", "vehicle id", "vehicle ids")),
        "mentions_date_context": _mentions_any(text, ("date", "start date", "end date", "start", "end", "time", "range")),
        "mentions_permission_context": _mentions_any(text, ("permission", "unauthorized", "forbidden", "access", "scope", "role", "authorization")),
        "mentions_required_or_missing": _mentions_any(text, ("required", "missing", "must be present", "must provide", "cannot be blank", "cannot be empty", "needed")),
        "mentions_invalid_or_rejected": _mentions_any(text, ("invalid", "rejected", "malformed", "unsupported", "not allowed", "unrecognized", "bad request")),
    }


def _empty_provider_error_semantics() -> dict[str, bool]:
    return {field: False for field in PROVIDER_400_SEMANTIC_FIELDS}


def _mentions_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _normalized_provider_error_text(messages: list[str], keys: list[str]) -> str:
    return " ".join(messages + keys).lower().replace("-", " ").replace("[]", "s")


def _normalized_semantic_text(messages: list[str], keys: list[str]) -> str:
    return _normalized_provider_error_text(messages, keys).replace("_", " ")


def _is_safe_provider_message(message: str) -> bool:
    if not message or len(message) > 160:
        return False
    lowered = message.lower()
    if any(marker in lowered for marker in _SENSITIVE_MESSAGE_MARKERS):
        return False
    if _EMAIL_RE.search(message) or _UUID_RE.search(message) or _LONG_NUMBER_RE.search(message) or _TOKENISH_RE.search(message) or _VIN_RE.search(message):
        return False
    return True


def _summarize_contract_payload(payload: Any) -> dict[str, Any]:
    top_level_type = _json_type(payload)
    top_level_keys = _safe_sorted_keys(payload) if isinstance(payload, dict) else []
    item_container_key, items = _item_container(payload)
    inspected_item = _first_dict(items)
    item_wrapper_key = _item_wrapper_key(inspected_item)
    item = inspected_item.get(item_wrapper_key) if item_wrapper_key and isinstance(inspected_item.get(item_wrapper_key), dict) else inspected_item
    item_keys = _safe_sorted_keys(item) if isinstance(item, dict) else []
    nested_object_keys = _nested_object_keys(item) if isinstance(item, dict) else {}
    vehicle_identity_paths = _matching_paths(item, _is_vehicle_identity_key) if isinstance(item, dict) else []
    provider_record_id_paths = _matching_paths(item, _is_provider_record_identity_key) if isinstance(item, dict) else []
    period_fields = _matching_paths(item, _is_period_key) if isinstance(item, dict) else []
    pagination = payload.get("pagination") if isinstance(payload, dict) else None
    pagination_keys = _safe_sorted_keys(pagination) if isinstance(pagination, dict) else []
    metrics = {metric: _metric_summary(item, metric) for metric in MOTIVE_VEHICLE_UTILIZATION_METRICS}
    unit_fields = _matching_paths(payload, _is_unit_key)
    schema_compatibility = _schema_compatibility(
        item_container_key=item_container_key,
        item_wrapper_key=item_wrapper_key,
        vehicle_identity_paths=vehicle_identity_paths,
        metrics=metrics,
    )
    provider_returned_reporting_period_fields = bool(period_fields)
    return {
        "top_level_type": top_level_type,
        "top_level_keys": top_level_keys,
        "item_container_key": item_container_key,
        "item_wrapper_key": item_wrapper_key,
        "item_count_observed": len(items),
        "item_keys": item_keys,
        "nested_object_keys": nested_object_keys,
        "vehicle_identity_paths": vehicle_identity_paths,
        "provider_utilization_record_id_paths": provider_record_id_paths,
        "period_fields": period_fields,
        "pagination_keys": pagination_keys,
        "pagination_total_present": "total" in pagination_keys,
        "pagination_page_no_present": "page_no" in pagination_keys,
        "pagination_per_page_present": "per_page" in pagination_keys,
        "metrics": metrics,
        "unit_fields": unit_fields,
        "schema_compatibility": schema_compatibility,
        "provider_schema_compatibility": schema_compatibility,
        "period_source_candidate": "provider_fields" if period_fields else "request_window_documented_summary_scope",
        "request_window": {
            "classification": "CONFIRMED",
            "meaning": "provider-documented utilization summary request scope",
            "source": "request_parameters.start_date/end_date",
            "provider_returned_reporting_period_fields": provider_returned_reporting_period_fields,
        },
        "provider_reporting_period_fields": {
            "present": provider_returned_reporting_period_fields,
            "classification": "DEFERRED" if not provider_returned_reporting_period_fields else "CONFIRMED",
            "reason": "The documented v1 vehicle_utilization response uses the request window as summary scope and does not require returned reporting-period fields.",
        },
        "persistence_readiness": {
            "status": "blocked",
            "schema_ready_for_future_writer_shape": schema_compatibility == _SCHEMA_COMPATIBLE,
            "writer_enabled": False,
            "persistence_enabled": False,
            "checkpoint_advancement_enabled": False,
            "scheduled_sync_enabled": False,
            "broad_sync_enabled": False,
            "durable_identity_certified": False,
            "reasons": [
                "end_date boundary behavior remains unresolved",
                "rollup cardinality and no-activity vehicle behavior remain unresolved",
                "exact company-configured rollup timezone value remains unresolved",
                "durable idempotency key remains unresolved",
                "checkpoint advancement strategy remains unresolved",
            ],
        },
    }


def _base_url() -> str:
    return os.getenv("POLARIS_MOTIVE_API_BASE_URL", MOTIVE_API_BASE_URL).rstrip("/")


def _item_container(payload: Any) -> tuple[str | None, list[Any]]:
    if isinstance(payload, list):
        return None, payload
    if not isinstance(payload, dict):
        return None, []
    preferred = ("vehicle_utilization", "vehicle_utilizations", "utilization", "utilizations", "data", "items", "records")
    for key in preferred:
        value = payload.get(key)
        if isinstance(value, list):
            return key, value
    for key, value in payload.items():
        key_text = str(key)
        if isinstance(value, list) and _safe_schema_key(key_text):
            return key_text, value
    for key, value in payload.items():
        key_text = str(key)
        if isinstance(value, dict) and key != "pagination" and _safe_schema_key(key_text):
            return key_text, [value]
    return None, []


def _first_dict(items: list[Any]) -> dict[str, Any]:
    for item in items:
        if isinstance(item, dict):
            return item
    return {}


def _item_wrapper_key(item: dict[str, Any]) -> str | None:
    if len(item) != 1:
        return None
    key, value = next(iter(item.items()))
    if isinstance(value, dict):
        key_text = str(key)
        return key_text if _safe_schema_key(key_text) else None
    return None


def _safe_sorted_keys(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    return sorted(str(key) for key in value.keys() if _safe_schema_key(str(key)))


def _safe_schema_key(key: str) -> bool:
    lowered = key.lower()
    return not any(marker in lowered for marker in _SECRET_KEY_MARKERS)


def _nested_object_keys(value: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for key, nested in value.items():
        if _safe_schema_key(str(key)) and isinstance(nested, dict):
            result[str(key)] = _safe_sorted_keys(nested)
    return result


def _matching_paths(value: Any, predicate: Any, *, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            if not _safe_schema_key(key_text):
                continue
            path = f"{prefix}.{key_text}" if prefix else key_text
            if predicate(key_text, path):
                paths.append(path)
            if isinstance(nested, dict):
                paths.extend(_matching_paths(nested, predicate, prefix=path))
            elif isinstance(nested, list) and nested and isinstance(nested[0], dict):
                paths.extend(_matching_paths(nested[0], predicate, prefix=f"{path}[]"))
    elif isinstance(value, list) and value and isinstance(value[0], dict):
        paths.extend(_matching_paths(value[0], predicate, prefix=prefix))
    return sorted(set(paths))


def _is_vehicle_identity_key(key: str, path: str) -> bool:
    lowered_key = key.lower()
    lowered_path = path.lower()
    if lowered_key in {"vin", "license_plate", "license_plate_number", "plate"}:
        return False
    if lowered_key in {"vehicle_id", "provider_vehicle_id"}:
        return True
    if lowered_key.endswith("vehicle_id"):
        return True
    return lowered_key == "id" and "vehicle" in lowered_path


def _is_provider_record_identity_key(key: str, path: str) -> bool:
    lowered_key = key.lower()
    lowered_path = path.lower()
    return lowered_key == "id" and "vehicle" not in lowered_path


def _is_period_key(key: str, path: str) -> bool:
    lowered = key.lower()
    if lowered in MOTIVE_VEHICLE_UTILIZATION_METRICS:
        return False
    if lowered in MOTIVE_VEHICLE_UTILIZATION_PERIOD_KEYS:
        return True
    return (
        lowered.endswith("_date")
        or lowered.endswith("_timestamp")
        or lowered.startswith("period_")
        or lowered.startswith("reporting_")
    )


def _is_unit_key(key: str, path: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in ("unit", "timezone", "time_zone", "metric"))


def _metric_summary(item: Any, metric: str) -> dict[str, Any]:
    paths = _metric_paths(item, metric)
    if not paths:
        return {"present": False, "type": None, "null": None, "paths": []}
    value = _value_at_path(item, paths[0])
    return {"present": True, "type": _json_type(value), "null": value is None, "paths": paths}


def _metric_paths(value: Any, metric: str, *, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            if not _safe_schema_key(key_text):
                continue
            path = f"{prefix}.{key_text}" if prefix else key_text
            if key_text == metric:
                paths.append(path)
            if isinstance(nested, dict):
                paths.extend(_metric_paths(nested, metric, prefix=path))
            elif isinstance(nested, list) and nested and isinstance(nested[0], dict):
                paths.extend(_metric_paths(nested[0], metric, prefix=f"{path}[]"))
    return sorted(set(paths))


def _value_at_path(value: Any, path: str) -> Any:
    current = value
    for part in path.replace("[]", "").split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _schema_compatibility(
    *,
    item_container_key: str | None,
    item_wrapper_key: str | None,
    vehicle_identity_paths: list[str],
    metrics: dict[str, dict[str, Any]],
) -> str:
    if not vehicle_identity_paths:
        return _SCHEMA_INSUFFICIENT_IDENTITY
    if item_container_key != "vehicle_idle_rollups" or item_wrapper_key != "vehicle_idle_rollup":
        return _SCHEMA_INCOMPLETE_PROVIDER_SCHEMA
    if any(not metrics.get(metric, {}).get("present") for metric in MOTIVE_VEHICLE_UTILIZATION_METRICS):
        return _SCHEMA_INCOMPLETE_PROVIDER_SCHEMA
    return _SCHEMA_COMPATIBLE


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


run_vehicle_utilization_contract_verification = verify_vehicle_utilization_contract
