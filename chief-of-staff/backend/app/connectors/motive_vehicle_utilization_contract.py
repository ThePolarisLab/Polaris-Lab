"""Verification-only Motive vehicle utilization contract inspection.

This module performs one bounded read-only request and returns only sanitized
schema metadata. It must not persist utilization data or expose provider values.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any

import httpx

from app.connectors.models import ConnectorStatus
from app.connectors.motive import MOTIVE_API_BASE_URL, MotiveConnectorError, _api_key, _retry_after_seconds, _timeout_seconds

logger = logging.getLogger(__name__)

MOTIVE_VEHICLE_UTILIZATION_ENDPOINT = "/v1/vehicle_utilization"
MOTIVE_VEHICLE_UTILIZATION_CONTRACT_PARAMS = {"per_page": 1, "page_no": 1}
MOTIVE_VEHICLE_UTILIZATION_METRICS = ("utilization", "idle_time", "idle_fuel", "driving_time", "driving_fuel")
MOTIVE_VEHICLE_UTILIZATION_TIME_ZONE = "America/Winnipeg"
_SCHEMA_COMPATIBLE = "compatible"
_SCHEMA_REQUIRES_MAPPING_REVIEW = "requires_mapping_review"
_SCHEMA_INSUFFICIENT_IDENTITY = "insufficient_identity"
_SCHEMA_INSUFFICIENT_PERIOD = "insufficient_period"
_SECRET_KEY_MARKERS = ("token", "secret", "authorization", "api_key", "x-api-key", "credential")


def verify_vehicle_utilization_contract(
    *,
    organization_id: str,
    provider_vehicle_id: str,
    request_date: date,
    http_client: httpx.Client | None = None,
    time_zone: str = MOTIVE_VEHICLE_UTILIZATION_TIME_ZONE,
) -> dict[str, Any]:
    """Make exactly one read-only provider call and summarize the response schema."""
    if not provider_vehicle_id:
        raise MotiveConnectorError("Motive vehicle utilization contract verification requires a stored vehicle id", status=ConnectorStatus.FAILED, code="provider_contract_error")
    params: dict[str, Any] = {
        "vehicle_ids[]": provider_vehicle_id,
        "start_date": request_date.isoformat(),
        "end_date": request_date.isoformat(),
        "per_page": MOTIVE_VEHICLE_UTILIZATION_CONTRACT_PARAMS["per_page"],
        "page_no": MOTIVE_VEHICLE_UTILIZATION_CONTRACT_PARAMS["page_no"],
    }
    headers = {"Accept": "application/json", "X-API-Key": _api_key(), "X-Time-Zone": time_zone}
    metric_units = os.getenv("POLARIS_MOTIVE_X_METRIC_UNITS")
    if metric_units:
        headers["X-Metric-Units"] = metric_units
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=_timeout_seconds())
    try:
        response = client.get(f"{_base_url()}{MOTIVE_VEHICLE_UTILIZATION_ENDPOINT}", params=params, headers=headers)
        payload = _contract_json_response(response)
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
    except httpx.TimeoutException as exc:
        raise MotiveConnectorError("Motive vehicle utilization contract request timed out", status=ConnectorStatus.FAILED, retryable=False, code="provider_timeout") from exc
    except httpx.HTTPError as exc:
        raise MotiveConnectorError("Motive vehicle utilization contract request failed due to a network error", status=ConnectorStatus.FAILED, retryable=False, code="network_failure") from exc
    finally:
        if owns_client:
            client.close()
    summary = _summarize_contract_payload(payload, request_date=request_date)
    logger.info(
        "MOTIVE VEHICLE UTILIZATION CONTRACT VERIFY",
        extra={
            "motive_operation": "vehicle_utilization_contract_verify",
            "organization_id": organization_id,
            "http_status": response.status_code,
            "response_type": summary["top_level_type"],
            "item_count": summary["item_count_observed"],
            "schema_compatibility": summary["schema_compatibility"],
        },
    )
    return {
        "status": "success",
        "endpoint": MOTIVE_VEHICLE_UTILIZATION_ENDPOINT,
        "provider_vehicle_selected": True,
        "vehicle_id_redacted": True,
        "request_period": {"start_date": request_date.isoformat(), "end_date": request_date.isoformat()},
        "request_shape": {
            "method": "GET",
            "path": MOTIVE_VEHICLE_UTILIZATION_ENDPOINT,
            "params": {"vehicle_ids[]": "[REDACTED]", "start_date": request_date.isoformat(), "end_date": request_date.isoformat(), "per_page": 1, "page_no": 1},
            "headers": {"Accept": "application/json", "X-Time-Zone": time_zone, "X-Metric-Units": metric_units if metric_units else None, "X-API-Key": "[REDACTED]"},
            "max_provider_attempts": 1,
        },
        **summary,
        "secrets_exposed": False,
    }


def _contract_json_response(response: httpx.Response) -> Any:
    retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
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


def _summarize_contract_payload(payload: Any, *, request_date: date) -> dict[str, Any]:
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
    schema_compatibility = _schema_compatibility(vehicle_identity_paths, period_fields, request_date=request_date)
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
        "period_source_candidate": "provider_fields" if period_fields else "request_window_requires_review",
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
        if isinstance(value, list):
            return str(key), value
    for key, value in payload.items():
        if isinstance(value, dict) and key != "pagination":
            return str(key), [value]
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
        return str(key)
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
    return any(marker in lowered for marker in ("start", "end", "date", "time", "timestamp", "period"))


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


def _schema_compatibility(vehicle_identity_paths: list[str], period_fields: list[str], *, request_date: date) -> str:
    if not vehicle_identity_paths:
        return _SCHEMA_INSUFFICIENT_IDENTITY
    if period_fields:
        return _SCHEMA_COMPATIBLE
    if request_date:
        return _SCHEMA_REQUIRES_MAPPING_REVIEW
    return _SCHEMA_INSUFFICIENT_PERIOD


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
