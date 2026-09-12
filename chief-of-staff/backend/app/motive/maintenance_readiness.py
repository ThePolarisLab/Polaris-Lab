"""Read-only Motive maintenance readiness and bounded operational detail."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.connectors.motive import MotiveConnector, MotiveConnectorError

LOOKBACK_DAYS = 7
PAGE_SIZE = 100
MAX_PAGES = 20
MAX_WINDOW_ROWS = PAGE_SIZE * MAX_PAGES
MAX_DETAILS_PER_TRUCK = 10
RESOLUTION_STATUSES = {"open", "repaired", "no_repair_needed", "good"}
EXPLICIT_RESOLVED_STATUSES = {"repaired", "no_repair_needed"}


def maintenance_readiness_for_trucks(
    *, truck_numbers: list[str], as_of_date: date, connector: MotiveConnector
) -> dict[str, Any]:
    wanted = {n.strip().casefold(): n.strip() for n in truck_numbers if n and n.strip()}
    if not wanted:
        return _empty_result(as_of_date)

    start = as_of_date - timedelta(days=LOOKBACK_DAYS - 1)
    faults, fa, fc = _read_all_pages(
        connector,
        "/v1/fault_codes",
        {"start_date": start.isoformat(), "end_date": as_of_date.isoformat()},
        "assignment_maintenance_fault_codes",
        collection="fault_codes",
    )
    reports, ra, rc = _read_all_pages(
        connector,
        "/v2/inspection_reports",
        {"updated_after": start.isoformat(), "entity_type": "vehicle"},
        "assignment_maintenance_inspection_reports",
        collection="inspection_reports",
    )

    data = {
        key: {
            "truck_number": display,
            "opened_fault_count": 0,
            "rejected_inspection_count": 0,
            "open_inspection_part_count": 0,
            "open_fault_details": [],
            "inspection_issue_details": [],
            "_inspection_group_observations": {},
            "_inspection_resolution_observations": {},
        }
        for key, display in wanted.items()
    }

    if fa:
        for fault in _children(faults, "fault_codes", "fault_code"):
            vehicle = fault.get("vehicle") if isinstance(fault.get("vehicle"), dict) else {}
            item = data.get(str(vehicle.get("number") or "").strip().casefold())
            if item is None or _norm(fault.get("status")) != "opened":
                continue
            item["opened_fault_count"] += 1
            if len(item["open_fault_details"]) < MAX_DETAILS_PER_TRUCK:
                item["open_fault_details"].append(_fault_detail(fault))

    if ra:
        for report in _children(reports, "inspection_reports", "inspection_report"):
            vehicle = report.get("vehicle") if isinstance(report.get("vehicle"), dict) else {}
            item = data.get(str(vehicle.get("number") or "").strip().casefold())
            if item is None:
                continue

            rejected = report.get("is_rejected") is True
            if rejected:
                item["rejected_inspection_count"] += 1
                if len(item["inspection_issue_details"]) < MAX_DETAILS_PER_TRUCK:
                    item["inspection_issue_details"].append(_inspection_detail(report, part=None))

            parts = report.get("inspected_parts") if isinstance(report.get("inspected_parts"), list) else []
            for part in parts:
                if not isinstance(part, dict):
                    continue
                detail = _inspection_detail(report, part=part)
                group_key = _inspection_group_key(detail)
                part_status = _norm(part.get("status"))

                if group_key and group_key[0] != "__unidentified__" and part_status in RESOLUTION_STATUSES:
                    resolution_groups = item["_inspection_resolution_observations"]
                    resolution_groups.setdefault(group_key, []).append(detail)

                if part_status != "open":
                    continue
                item["open_inspection_part_count"] += 1
                if len(item["inspection_issue_details"]) < MAX_DETAILS_PER_TRUCK:
                    item["inspection_issue_details"].append(detail)
                groups = item["_inspection_group_observations"]
                groups.setdefault(group_key, []).append(detail)

    results = []
    for key in wanted:
        item = data[key]
        recurring_groups = _build_recurring_inspection_groups(item.pop("_inspection_group_observations"))
        resolution_groups = _build_resolution_inspection_groups(item.pop("_inspection_resolution_observations"))
        blockers: list[str] = []
        reasons: list[str] = []
        if item["rejected_inspection_count"]:
            blockers.append("inspection_report_rejected")
        if not fa:
            reasons.append("fault_code_data_unavailable")
        elif not fc:
            reasons.append("fault_code_result_window_incomplete")
        elif item["opened_fault_count"]:
            reasons.append("opened_fault_code_present")
        if not ra:
            reasons.append("inspection_data_unavailable")
        elif not rc:
            reasons.append("inspection_result_window_incomplete")
        elif item["open_inspection_part_count"]:
            reasons.append("open_inspection_part_present")

        classification = "not_suitable" if blockers else "verify" if reasons else "clear"
        results.append(
            {
                **item,
                "recurring_inspection_issue_groups": recurring_groups,
                "recurring_inspection_issue_count": sum(1 for group in recurring_groups if group["recurring"]),
                "inspection_resolution_groups": resolution_groups,
                "explicitly_resolved_inspection_issue_count": sum(
                    1 for group in resolution_groups if group["resolution_state"] == "resolved"
                ),
                "reopened_inspection_issue_count": sum(
                    1 for group in resolution_groups if group["resolution_state"] == "reopened"
                ),
                "classification": classification,
                "hard_blockers": blockers,
                "verification_reasons": reasons,
                "detail_limit_per_type": MAX_DETAILS_PER_TRUCK,
                "fault_details_truncated": item["opened_fault_count"] > len(item["open_fault_details"]),
                "inspection_details_truncated": (
                    item["rejected_inspection_count"] + item["open_inspection_part_count"]
                    > len(item["inspection_issue_details"])
                ),
                "recurrence_changes_readiness": False,
                "recurrence_basis": "same_structured_part_identity_within_provider_window",
                "resolution_changes_readiness": False,
                "resolution_basis": "explicit_structured_part_status_transition_within_provider_window",
                "disappearance_means_resolved": False,
                "durable_maintenance_history_enabled": False,
                "safety_classification_certified": False,
                "defect_free_text_returned": False,
                "advisory_only": True,
                "dispatcher_approval_required": True,
                "provider_window_days": LOOKBACK_DAYS,
            }
        )

    return {
        "as_of_date": as_of_date.isoformat(),
        "fault_codes_available": fa,
        "fault_codes_window_complete": fc,
        "inspection_reports_available": ra,
        "inspection_reports_window_complete": rc,
        "classifications": results,
        "provider_writes_performed": False,
        "dispatch_mutation_performed": False,
        "autonomous_assignment_performed": False,
    }


def _fault_detail(fault: dict[str, Any]) -> dict[str, Any]:
    """Whitelisted structured fault fields; excludes vehicle identity and raw payload."""
    return {
        "status": _safe_scalar(fault.get("status")),
        "code": _safe_scalar(fault.get("code")),
        "code_label": _safe_scalar(fault.get("code_label")),
        "code_description": _safe_scalar(fault.get("code_description")),
        "first_observed_at": _safe_scalar(fault.get("first_observed_at")),
        "last_observed_at": _safe_scalar(fault.get("last_observed_at")),
        "occurrence_count": _safe_scalar(fault.get("occurrence_count")),
        "observation_count": _safe_scalar(fault.get("observation_count")),
        "fmi": _safe_scalar(fault.get("fmi")),
        "fmi_description": _safe_scalar(fault.get("fmi_description")),
        "severity_used_for_decision": False,
    }


def _inspection_detail(report: dict[str, Any], *, part: dict[str, Any] | None) -> dict[str, Any]:
    """Whitelisted report/part fields; excludes notes, signatures and defect text."""
    detail = {
        "report_date": _safe_scalar(report.get("date")),
        "report_time": _safe_scalar(report.get("time")),
        "inspection_type": _safe_scalar(report.get("inspection_type")),
        "report_status": _safe_scalar(report.get("status")),
        "is_rejected": report.get("is_rejected") is True,
        "odometer": _safe_scalar(report.get("odometer")),
        "part_name": None,
        "part_category": None,
        "part_type": None,
        "part_status": None,
        "defect_count": 0,
        "safety_related_confirmed": False,
    }
    if part is not None:
        defects = part.get("defects") if isinstance(part.get("defects"), list) else []
        detail.update(
            {
                "part_name": _safe_scalar(part.get("name")),
                "part_category": _safe_scalar(part.get("category")),
                "part_type": _safe_scalar(part.get("type")),
                "part_status": _safe_scalar(part.get("status")),
                "defect_count": len(defects),
            }
        )
    return detail


def _inspection_group_key(detail: dict[str, Any]) -> tuple[str, ...]:
    identity = (
        _norm(detail.get("part_category")),
        _norm(detail.get("part_type")),
        _norm(detail.get("part_name")),
    )
    if any(identity):
        return identity
    return (
        "__unidentified__",
        str(detail.get("report_date") or ""),
        str(detail.get("report_time") or ""),
    )


def _build_recurring_inspection_groups(
    grouped: dict[tuple[str, ...], list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for group_key, observations in grouped.items():
        if not observations or (group_key and group_key[0] == "__unidentified__"):
            continue
        ordered = sorted(observations, key=_inspection_observation_sort_key)
        first = ordered[0]
        latest = ordered[-1]
        report_dates = sorted(
            {
                value
                for observation in observations
                if isinstance((value := observation.get("report_date")), str) and value
            }
        )
        groups.append(
            {
                "part_name": latest.get("part_name"),
                "part_category": latest.get("part_category"),
                "part_type": latest.get("part_type"),
                "source_record_count": len(observations),
                "distinct_report_days": len(report_dates),
                "recurring": len(observations) >= 2,
                "first_seen_date": first.get("report_date"),
                "latest_seen_date": latest.get("report_date"),
                "latest_report_time": latest.get("report_time"),
                "latest_odometer": latest.get("odometer"),
                "latest_part_status": latest.get("part_status"),
                "latest_report_status": latest.get("report_status"),
                "latest_inspection_type": latest.get("inspection_type"),
                "consecutive_days_confirmed": False,
                "repair_resolution_confirmed": False,
                "safety_related_confirmed": False,
            }
        )
    return sorted(
        groups,
        key=lambda group: (
            not bool(group.get("recurring")),
            -int(group.get("source_record_count") or 0),
            str(group.get("part_category") or ""),
            str(group.get("part_type") or ""),
        ),
    )


def _build_resolution_inspection_groups(
    grouped: dict[tuple[str, ...], list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for group_key, observations in grouped.items():
        if not observations or (group_key and group_key[0] == "__unidentified__"):
            continue
        ordered = sorted(observations, key=_inspection_observation_sort_key)
        compact: list[dict[str, Any]] = []
        for observation in ordered:
            status = _norm(observation.get("part_status"))
            if status not in RESOLUTION_STATUSES:
                continue
            entry = {
                "report_date": observation.get("report_date"),
                "report_time": observation.get("report_time"),
                "status": status,
                "odometer": observation.get("odometer"),
            }
            if not compact or compact[-1]["status"] != status:
                compact.append(entry)
            else:
                compact[-1] = entry
        if not compact:
            continue

        latest = ordered[-1]
        first_open = next((entry for entry in compact if entry["status"] == "open"), None)
        resolved_index = next(
            (index for index, entry in enumerate(compact) if entry["status"] in EXPLICIT_RESOLVED_STATUSES and first_open is not None),
            None,
        )
        resolved_entry = compact[resolved_index] if resolved_index is not None else None
        reopened_entry = None
        if resolved_index is not None:
            reopened_entry = next(
                (entry for entry in compact[resolved_index + 1 :] if entry["status"] == "open"),
                None,
            )

        latest_status = _norm(latest.get("part_status"))
        if reopened_entry is not None and latest_status == "open":
            state = "reopened"
        elif resolved_entry is not None and latest_status in EXPLICIT_RESOLVED_STATUSES:
            state = "resolved"
        elif latest_status == "open":
            state = "open"
        else:
            state = "observed_non_open"

        groups.append(
            {
                "part_name": latest.get("part_name"),
                "part_category": latest.get("part_category"),
                "part_type": latest.get("part_type"),
                "resolution_state": state,
                "latest_structured_status": latest_status or None,
                "first_open_date": first_open.get("report_date") if first_open else None,
                "explicit_resolution_status": resolved_entry.get("status") if resolved_entry else None,
                "explicit_resolution_date": resolved_entry.get("report_date") if resolved_entry else None,
                "reopened_date": reopened_entry.get("report_date") if reopened_entry else None,
                "latest_seen_date": latest.get("report_date"),
                "latest_odometer": latest.get("odometer"),
                "status_transitions": compact,
                "resolution_confirmed": state == "resolved",
                "reopened_confirmed": state == "reopened",
                "good_status_proves_repair": False,
                "disappearance_means_resolved": False,
                "window_bounded": True,
            }
        )
    return sorted(
        groups,
        key=lambda group: (
            group.get("resolution_state") != "reopened",
            group.get("resolution_state") != "open",
            str(group.get("part_category") or ""),
            str(group.get("part_type") or ""),
        ),
    )


def _inspection_observation_sort_key(detail: dict[str, Any]) -> tuple[str, str]:
    return (
        str(detail.get("report_date") or ""),
        str(detail.get("report_time") or ""),
    )


def _safe_scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return None


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


def _read_all_pages(
    connector: MotiveConnector,
    endpoint: str,
    base_params: dict[str, Any],
    operation: str,
    *,
    collection: str,
) -> tuple[dict[str, Any], bool, bool]:
    combined: list[Any] = []
    expected_total: int | None = None
    for page_no in range(1, MAX_PAGES + 1):
        params = {**base_params, "per_page": PAGE_SIZE, "page_no": page_no}
        try:
            payload = connector._request_json(endpoint, params=params, operation=operation)  # noqa: SLF001
        except MotiveConnectorError:
            return {collection: combined}, False, False
        if not isinstance(payload, dict):
            return {collection: combined}, False, False
        rows = payload.get(collection)
        total = payload.get("total")
        if not isinstance(rows, list) or not isinstance(total, int) or total < 0:
            return {collection: combined}, True, False
        if expected_total is None:
            expected_total = total
            if expected_total > MAX_WINDOW_ROWS:
                return {collection: combined + rows, "total": expected_total}, True, False
        elif total != expected_total:
            return {collection: combined + rows, "total": expected_total}, True, False
        combined.extend(rows)
        if len(combined) >= expected_total:
            return {collection: combined[:expected_total], "total": expected_total}, True, True
        if not rows:
            return {collection: combined, "total": expected_total}, True, False
    return {collection: combined, "total": expected_total}, True, False


def _children(payload: dict[str, Any], collection: str, child: str) -> list[dict[str, Any]]:
    rows = payload.get(collection)
    if not isinstance(rows, list):
        return []
    return [row[child] for row in rows if isinstance(row, dict) and isinstance(row.get(child), dict)]


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()
