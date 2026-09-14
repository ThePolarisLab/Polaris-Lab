from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.motive import MotiveConnector
from app.motive.maintenance_readiness import _children, _read_all_pages
from app.motive.vehicle_utilization_scheduler import resolve_scheduled_organization

FAULT_CODES_ENDPOINT = "/v1/fault_codes"
LOOKBACK_DAYS = 30
IDENTITY_FIELD_PATHS = (
    "id",
    "code",
    "fmi",
    "network_id",
    "source",
    "source_address",
    "code_label",
    "vehicle.id",
    "gateway.id",
)


def certify_fault_lifecycle_evidence(
    session: Session,
    *,
    certification_date: date,
    connector: MotiveConnector | None = None,
) -> dict[str, Any]:
    organization = resolve_scheduled_organization(session)
    client = connector or MotiveConnector(organization_id=organization.id)
    start_date = certification_date - timedelta(days=LOOKBACK_DAYS - 1)
    payload, available, complete = _read_all_pages(
        client,
        FAULT_CODES_ENDPOINT,
        {"start_date": start_date.isoformat(), "end_date": certification_date.isoformat()},
        "fault_lifecycle_certification",
        collection="fault_codes",
    )
    faults = _children(payload, "fault_codes", "fault_code") if available else []
    status_counts = Counter(_norm(fault.get("status")) or "<blank>" for fault in faults)
    identity_fields = {path: _field_evidence(faults, path) for path in IDENTITY_FIELD_PATHS}
    same_provider_id_across_statuses = identity_fields["id"]["values_seen_with_multiple_statuses"] > 0

    temporal_observed = 0
    temporal_valid = 0
    temporal_invalid = 0
    for fault in faults:
        first = _text(fault.get("first_observed_at"))
        last = _text(fault.get("last_observed_at"))
        if first is None or last is None:
            continue
        temporal_observed += 1
        if first <= last:
            temporal_valid += 1
        else:
            temporal_invalid += 1

    return {
        "status": "certification_completed",
        "provider": "motive",
        "operation": "fault_lifecycle_evidence_certification",
        "certification_date": certification_date.isoformat(),
        "lookback_days": LOOKBACK_DAYS,
        "fault_codes_available": available,
        "fault_code_window_complete": complete,
        "records_observed": len(faults),
        "status_values_observed": sorted(status_counts),
        "status_counts": dict(sorted(status_counts.items())),
        "open_records_found": status_counts.get("open", 0) > 0,
        "closed_records_found": status_counts.get("closed", 0) > 0,
        "identity_field_evidence": identity_fields,
        "provider_record_id_present_all_records": bool(faults) and identity_fields["id"]["non_null_count"] == len(faults),
        "provider_record_id_unique_within_window": bool(faults) and identity_fields["id"]["distinct_count"] == len(faults),
        "same_provider_id_observed_across_statuses": same_provider_id_across_statuses,
        "cross_status_same_identity_counts": {
            path: evidence["values_seen_with_multiple_statuses"] for path, evidence in identity_fields.items()
        },
        "first_last_observed_pairs": temporal_observed,
        "first_last_order_valid_count": temporal_valid,
        "first_last_order_invalid_count": temporal_invalid,
        "stable_identity_over_time_certified": False,
        "open_to_closed_transition_certified": False,
        "durable_fault_memory_enabled": False,
        "provider_writes_performed": False,
        "database_writes_performed": False,
        "maintenance_readiness_changed": False,
        "dispatch_readiness_changed": False,
        "vehicle_identity_values_returned": False,
        "fault_code_values_returned": False,
        "raw_provider_payloads_returned": False,
    }


def _field_evidence(faults: list[dict[str, Any]], path: str) -> dict[str, Any]:
    values: list[Any] = []
    statuses_by_value: dict[str, set[str]] = defaultdict(set)
    present_count = 0
    non_null_count = 0
    for fault in faults:
        present, value = _get_path(fault, path)
        if present:
            present_count += 1
        normalized = _stable_scalar(value)
        if normalized is None:
            continue
        non_null_count += 1
        values.append(normalized)
        statuses_by_value[repr(normalized)].add(_norm(fault.get("status")) or "<blank>")
    distinct_count = len({repr(value) for value in values})
    return {
        "field_path": path,
        "present_count": present_count,
        "non_null_count": non_null_count,
        "distinct_count": distinct_count,
        "values_seen_with_multiple_statuses": sum(1 for statuses in statuses_by_value.values() if len(statuses) > 1),
        "all_records_non_null": bool(faults) and non_null_count == len(faults),
        "unique_within_window": bool(values) and distinct_count == len(values),
        "values_returned": False,
    }


def _get_path(value: dict[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _stable_scalar(value: Any) -> str | int | float | bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (str, int, float)):
        return value
    return None


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
