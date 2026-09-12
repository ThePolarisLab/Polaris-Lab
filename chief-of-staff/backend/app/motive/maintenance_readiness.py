"""Read-only Motive maintenance readiness advisory.

Uses only maintenance fields certified for MOR plus documented provider status
semantics. This layer is advisory: it never writes Motive data or dispatch state.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.connectors.motive import MotiveConnector, MotiveConnectorError

LOOKBACK_DAYS = 7
MAX_ROWS = 100


def maintenance_readiness_for_trucks(
    *,
    truck_numbers: list[str],
    as_of_date: date,
    connector: MotiveConnector,
) -> dict[str, Any]:
    wanted = {n.strip().casefold(): n.strip() for n in truck_numbers if n and n.strip()}
    if not wanted:
        return _empty_result(as_of_date)

    start = as_of_date - timedelta(days=LOOKBACK_DAYS - 1)
    faults, faults_available, faults_complete = _read(
        connector,
        "/v1/fault_codes",
        {
            "start_date": start.isoformat(),
            "end_date": as_of_date.isoformat(),
            "per_page": MAX_ROWS,
            "page_no": 1,
        },
        "assignment_maintenance_fault_codes",
        collection="fault_codes",
    )
    reports, reports_available, reports_complete = _read(
        connector,
        "/v2/inspection_reports",
        {
            "updated_after": start.isoformat(),
            "entity_type": "vehicle",
            "per_page": MAX_ROWS,
            "page_no": 1,
        },
        "assignment_maintenance_inspection_reports",
        collection="inspection_reports",
    )

    data = {
        key: {
            "truck_number": display,
            "opened_fault_count": 0,
            "rejected_inspection_count": 0,
            "open_inspection_part_count": 0,
        }
        for key, display in wanted.items()
    }

    if faults_available:
        for fault in _children(faults, "fault_codes", "fault_code"):
            vehicle = fault.get("vehicle") if isinstance(fault.get("vehicle"), dict) else {}
            item = data.get(str(vehicle.get("number") or "").strip().casefold())
            if item is not None and _norm(fault.get("status")) == "opened":
                item["opened_fault_count"] += 1

    if reports_available:
        for report in _children(reports, "inspection_reports", "inspection_report"):
            vehicle = report.get("vehicle") if isinstance(report.get("vehicle"), dict) else {}
            item = data.get(str(vehicle.get("number") or "").strip().casefold())
            if item is None:
                continue
            if report.get("is_rejected") is True:
                item["rejected_inspection_count"] += 1
            parts = report.get("inspected_parts") if isinstance(report.get("inspected_parts"), list) else []
            for part in parts:
                if isinstance(part, dict) and _norm(part.get("status")) == "open":
                    item["open_inspection_part_count"] += 1

    results: list[dict[str, Any]] = []
    for key in wanted:
        item = data[key]
        blockers: list[str] = []
        reasons: list[str] = []

        # Rejected inspection is the only maintenance hard blocker in v1.
        if item["rejected_inspection_count"]:
            blockers.append("inspection_report_rejected")

        if not faults_available:
            reasons.append("fault_code_data_unavailable")
        elif not faults_complete:
            reasons.append("fault_code_result_window_incomplete")
        elif item["opened_fault_count"]:
            reasons.append("opened_fault_code_present")

        if not reports_available:
            reasons.append("inspection_data_unavailable")
        elif not reports_complete:
            reasons.append("inspection_result_window_incomplete")
        elif item["open_inspection_part_count"]:
            reasons.append("open_inspection_part_present")

        classification = "not_suitable" if blockers else "verify" if reasons else "clear"
        results.append(
            {
                **item,
                "classification": classification,
                "hard_blockers": blockers,
                "verification_reasons": reasons,
                "advisory_only": True,
                "dispatcher_approval_required": True,
                "provider_window_days": LOOKBACK_DAYS,
            }
        )

    return {
        "as_of_date": as_of_date.isoformat(),
        "fault_codes_available": faults_available,
        "fault_codes_window_complete": faults_complete,
        "inspection_reports_available": reports_available,
        "inspection_reports_window_complete": reports_complete,
        "classifications": results,
        "provider_writes_performed": False,
        "dispatch_mutation_performed": False,
        "autonomous_assignment_performed": False,
    }


def _empty_result(as_of_date: date) -> dict[str, Any]:
    return {
        "as_of_date": as_of_date.isoformat(),
        "fault_codes_available": None,
        "fault_codes_window_complete": None,
        "inspection_reports_available": None,
        "inspection_reports_window_complete": None,
        "classifications": [],
        "provider_writes_performed": False,
        "dispatch_mutation_performed": False,
        "autonomous_assignment_performed": False,
    }


def _read(
    connector: MotiveConnector,
    endpoint: str,
    params: dict[str, Any],
    operation: str,
    *,
    collection: str,
) -> tuple[dict[str, Any], bool, bool]:
    try:
        payload = connector._request_json(endpoint, params=params, operation=operation)  # noqa: SLF001
    except MotiveConnectorError:
        return {}, False, False
    if not isinstance(payload, dict):
        return {}, False, False
    rows = payload.get(collection)
    total = payload.get("total")
    complete = isinstance(rows, list) and isinstance(total, int) and total <= len(rows) <= MAX_ROWS
    return payload, True, complete


def _children(payload: dict[str, Any], collection: str, child: str) -> list[dict[str, Any]]:
    rows = payload.get(collection)
    if not isinstance(rows, list):
        return []
    return [row[child] for row in rows if isinstance(row, dict) and isinstance(row.get(child), dict)]


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()
