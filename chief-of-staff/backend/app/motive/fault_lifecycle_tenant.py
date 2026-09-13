from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any

from app.connectors.motive import MotiveConnector
from app.motive.fault_lifecycle_certification import (
    FAULT_CODES_ENDPOINT,
    IDENTITY_FIELD_PATHS,
    LOOKBACK_DAYS,
    _field_evidence,
    _norm,
    _text,
)
from app.motive.maintenance_readiness import _children, _read_all_pages


def certify_fault_lifecycle_for_organization(
    *, organization_id: str, certification_date: date
) -> dict[str, Any]:
    connector = MotiveConnector(organization_id=organization_id)
    start_date = certification_date - timedelta(days=LOOKBACK_DAYS - 1)
    payload, available, complete = _read_all_pages(
        connector,
        FAULT_CODES_ENDPOINT,
        {"start_date": start_date.isoformat(), "end_date": certification_date.isoformat()},
        "fault_lifecycle_certification",
        collection="fault_codes",
    )
    faults = _children(payload, "fault_codes", "fault_code") if available else []
    status_counts = Counter(_norm(fault.get("status")) or "<blank>" for fault in faults)
    identity_fields = {path: _field_evidence(faults, path) for path in IDENTITY_FIELD_PATHS}

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
        "opened_records_found": status_counts.get("opened", 0) > 0,
        "closed_records_found": status_counts.get("closed", 0) > 0,
        "identity_field_evidence": identity_fields,
        "provider_record_id_present_all_records": bool(faults) and identity_fields["id"]["non_null_count"] == len(faults),
        "provider_record_id_unique_within_window": bool(faults) and identity_fields["id"]["distinct_count"] == len(faults),
        "cross_status_same_identity_counts": {
            path: evidence["values_seen_with_multiple_statuses"] for path, evidence in identity_fields.items()
        },
        "first_last_observed_pairs": temporal_observed,
        "first_last_order_valid_count": temporal_valid,
        "first_last_order_invalid_count": temporal_invalid,
        "stable_identity_over_time_certified": False,
        "opened_to_closed_transition_certified": False,
        "durable_fault_memory_enabled": False,
        "provider_writes_performed": False,
        "database_writes_performed": False,
        "maintenance_readiness_changed": False,
        "dispatch_readiness_changed": False,
        "vehicle_identity_values_returned": False,
        "fault_code_values_returned": False,
        "raw_provider_payloads_returned": False,
    }
