"""Privacy-safe production certification for Motive maintenance signals.

This gate observes schema/type structure only for read-only resources that may
later inform Maintenance Readiness:
- vehicle diagnostic fault codes
- vehicle inspection reports and defects

No provider values, vehicle identities, defect notes, signature URLs, or raw
payloads are returned to the caller. This module does not classify a truck as
safe/unsafe and does not change dispatch readiness.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.connectors.motive import MotiveConnector, MotiveConnectorError
from app.motive.vehicle_utilization_scheduler import resolve_scheduled_organization

FAULT_CODES_ENDPOINT = "/v1/fault_codes"
INSPECTION_REPORTS_ENDPOINT = "/v2/inspection_reports"
LOOKBACK_DAYS = 7
MAX_SCHEMA_DEPTH = 8
MAX_ARRAY_ITEMS_TO_OBSERVE = 5
SAMPLE_PAGE_SIZE = 5


def certify_maintenance_signal_schema(
    session: Session,
    *,
    certification_date: date,
    connector: MotiveConnector | None = None,
) -> dict[str, Any]:
    """Observe maintenance-resource schema without returning provider values."""
    organization = resolve_scheduled_organization(session)
    client = connector or MotiveConnector(organization_id=organization.id)
    start_date = certification_date - timedelta(days=LOOKBACK_DAYS - 1)

    fault_codes = _certify_resource(
        lambda: client._request_json(  # noqa: SLF001 - reuses hardened authenticated read path.
            FAULT_CODES_ENDPOINT,
            params={
                "start_date": start_date.isoformat(),
                "end_date": certification_date.isoformat(),
                "per_page": SAMPLE_PAGE_SIZE,
                "page_no": 1,
            },
            operation="maintenance_signal_fault_code_certification",
        )
    )
    inspection_reports = _certify_resource(
        lambda: client._request_json(  # noqa: SLF001 - reuses hardened authenticated read path.
            INSPECTION_REPORTS_ENDPOINT,
            params={
                "updated_after": start_date.isoformat(),
                "entity_type": "vehicle",
                "per_page": SAMPLE_PAGE_SIZE,
                "page_no": 1,
            },
            operation="maintenance_signal_inspection_report_certification",
        )
    )

    return {
        "status": "certification_completed",
        "provider": "motive",
        "operation": "maintenance_signal_schema_certification",
        "certification_date": certification_date.isoformat(),
        "lookback_days": LOOKBACK_DAYS,
        "resources": {
            "fault_codes": fault_codes,
            "inspection_reports": inspection_reports,
        },
        "schema_values_returned": False,
        "raw_provider_payloads_returned": False,
        "vehicle_identity_values_returned": False,
        "fault_code_values_returned": False,
        "inspection_defect_values_returned": False,
        "inspection_notes_returned": False,
        "signature_urls_returned": False,
        "secrets_exposed": False,
        "maintenance_readiness_changed": False,
        "dispatch_readiness_changed": False,
    }


def _certify_resource(fetcher: Callable[[], Any]) -> dict[str, Any]:
    try:
        payload = fetcher()
    except MotiveConnectorError as exc:
        return {
            "available": False,
            "error_code": exc.code,
            "provider_http_status": exc.http_status,
            "observed_schema_paths": {},
            "non_empty_sample_found": False,
        }
    observed = _schema_paths(payload)
    return {
        "available": True,
        "error_code": None,
        "provider_http_status": 200,
        "observed_schema_paths": observed,
        "non_empty_sample_found": _schema_has_observed_leaf(observed),
    }


def _schema_has_observed_leaf(observed: dict[str, list[str]]) -> bool:
    primitive_types = {"string", "integer", "number", "boolean", "null"}
    return any(
        path != "$" and primitive_types.intersection(types)
        for path, types in observed.items()
        if isinstance(types, list)
    )


def _schema_paths(value: Any) -> dict[str, list[str]]:
    observed: dict[str, set[str]] = {}
    _observe(value, path="$", depth=0, observed=observed)
    return {path: sorted(types) for path, types in sorted(observed.items())}


def _observe(value: Any, *, path: str, depth: int, observed: dict[str, set[str]]) -> None:
    observed.setdefault(path, set()).add(_type_name(value))
    if depth >= MAX_SCHEMA_DEPTH:
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and key:
                _observe(child, path=f"{path}.{key}", depth=depth + 1, observed=observed)
        return
    if isinstance(value, list):
        array_path = f"{path}[]"
        if not value:
            observed.setdefault(array_path, set()).add("empty")
            return
        for child in value[:MAX_ARRAY_ITEMS_TO_OBSERVE]:
            _observe(child, path=array_path, depth=depth + 1, observed=observed)


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "other"
