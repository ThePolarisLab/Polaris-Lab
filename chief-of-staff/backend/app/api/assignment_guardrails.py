"""Guardrail layer for read-only Assignment Intelligence.

Wraps the existing assignment engine without changing ranking/provider semantics.
Adds temporal, assignment-consistency, and conservative maintenance advisories.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.assignment_intelligence import _db, assignment_candidates as base_assignment_candidates
from app.connectors.motive import MotiveConnector
from app.motive.maintenance_memory import list_maintenance_memory
from app.motive.maintenance_readiness import LOOKBACK_DAYS, maintenance_readiness_for_trucks
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/api/v1/assignment-intelligence", tags=["assignment-intelligence"])


@router.get("/candidates")
def assignment_candidates_with_guardrails(
    load_number: str = Query(..., min_length=1, max_length=120),
    hos_date: date | None = Query(None),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    reference_date = datetime.now(timezone.utc).date()
    response = base_assignment_candidates(
        load_number=load_number,
        hos_date=hos_date,
        principal=principal,
        session=session,
    )
    response = apply_assignment_guardrails(response, reference_date=reference_date)
    trucks = [
        str(candidate.get("truck_number") or "").strip()
        for candidate in response.get("truck_candidates", [])
        if isinstance(candidate, dict) and str(candidate.get("truck_number") or "").strip()
    ]
    maintenance = maintenance_readiness_for_trucks(
        truck_numbers=trucks,
        as_of_date=reference_date,
        connector=MotiveConnector(organization_id=principal.organization_id),
    )
    response = apply_maintenance_guardrails(response, maintenance)

    durable_by_truck = {
        truck.casefold(): list_maintenance_memory(
            session=session,
            organization_id=principal.organization_id,
            truck_number=truck,
            limit=50,
        )
        for truck in trucks
    }
    return apply_durable_maintenance_context(response, durable_by_truck)


def apply_assignment_guardrails(response: dict[str, Any], *, reference_date: date) -> dict[str, Any]:
    load = response.get("load") if isinstance(response.get("load"), dict) else {}
    pickup = load.get("pickup") if isinstance(load.get("pickup"), dict) else {}
    current_assignment = load.get("current_assignment") if isinstance(load.get("current_assignment"), dict) else {}

    temporal = classify_pickup_temporal_status(pickup.get("scheduled_date"), reference_date=reference_date)
    consistency = classify_assignment_consistency(load.get("status"), current_assignment)
    response["load_guardrails"] = {"pickup_temporal": temporal, "assignment_consistency": consistency}

    load_level_reasons: list[str] = []
    if temporal["status"] == "past":
        load_level_reasons.append("pickup_date_past")
    elif temporal["status"] == "unknown":
        load_level_reasons.append("pickup_date_unparseable_or_missing")
    if not consistency["consistent"]:
        load_level_reasons.extend(consistency["reason_codes"])

    if load_level_reasons:
        for candidate in response.get("truck_candidates", []):
            if not isinstance(candidate, dict):
                continue
            readiness = candidate.get("dispatch_readiness")
            if not isinstance(readiness, dict):
                continue
            reasons = readiness.setdefault("verification_reasons", [])
            for reason in load_level_reasons:
                if reason not in reasons:
                    reasons.append(reason)
            if readiness.get("classification") == "ready":
                readiness["classification"] = "verify"
            readiness["verification_required"] = True

    _recalculate_readiness_summary(response)
    decision_guardrails = response.setdefault("decision_guardrails", {})
    if isinstance(decision_guardrails, dict):
        decision_guardrails.update(
            {
                "pickup_temporal_status_considered": True,
                "pickup_timezone_certified": False,
                "past_pickup_requires_dispatch_verification": temporal["status"] == "past",
                "assignment_consistency_checked": True,
                "assignment_data_inconsistency_present": not consistency["consistent"],
            }
        )
    return response


def apply_maintenance_guardrails(response: dict[str, Any], maintenance: dict[str, Any]) -> dict[str, Any]:
    by_truck = {
        str(item.get("truck_number") or "").strip().casefold(): item
        for item in maintenance.get("classifications", [])
        if isinstance(item, dict)
    }
    for candidate in response.get("truck_candidates", []):
        if not isinstance(candidate, dict):
            continue
        key = str(candidate.get("truck_number") or "").strip().casefold()
        advisory = by_truck.get(key)
        if advisory is None:
            continue
        candidate["maintenance_readiness"] = advisory
        readiness = candidate.get("dispatch_readiness")
        if not isinstance(readiness, dict):
            continue

        maintenance_class = advisory.get("classification")
        if maintenance_class == "not_suitable":
            blockers = readiness.setdefault("hard_blockers", [])
            for blocker in advisory.get("hard_blockers", []):
                code = f"maintenance_{blocker}"
                if code not in blockers:
                    blockers.append(code)
            readiness["classification"] = "not_suitable"
            readiness["verification_required"] = True
        elif maintenance_class == "verify":
            reasons = readiness.setdefault("verification_reasons", [])
            for reason in advisory.get("verification_reasons", []):
                code = f"maintenance_{reason}"
                if code not in reasons:
                    reasons.append(code)
            if readiness.get("classification") == "ready":
                readiness["classification"] = "verify"
            readiness["verification_required"] = True

    counts = {"clear": 0, "verify": 0, "not_suitable": 0}
    for item in maintenance.get("classifications", []):
        if isinstance(item, dict) and item.get("classification") in counts:
            counts[item["classification"]] += 1
    response["maintenance_readiness_summary"] = {
        **counts,
        "as_of_date": maintenance.get("as_of_date"),
        "provider_window_days": LOOKBACK_DAYS,
        "fault_codes_available": maintenance.get("fault_codes_available"),
        "fault_codes_window_complete": maintenance.get("fault_codes_window_complete"),
        "inspection_reports_available": maintenance.get("inspection_reports_available"),
        "inspection_reports_window_complete": maintenance.get("inspection_reports_window_complete"),
    }
    _recalculate_readiness_summary(response)

    guardrails = response.setdefault("decision_guardrails", {})
    if isinstance(guardrails, dict):
        guardrails.update(
            {
                "maintenance_readiness_is_advisory": True,
                "maintenance_readiness_provider_window_days": LOOKBACK_DAYS,
                "maintenance_fault_severity_used_as_hard_blocker": False,
                "maintenance_open_fault_code_requires_verification": True,
                "maintenance_rejected_inspection_is_hard_blocker": True,
                "dispatcher_approval_required": True,
                "autonomous_assignment_performed": False,
            }
        )
    provider_calls = response.setdefault("provider_calls", {})
    if isinstance(provider_calls, dict):
        provider_calls.update({"motive_fault_codes": True, "motive_inspection_reports": True})
    return response


def apply_durable_maintenance_context(
    response: dict[str, Any], durable_by_truck: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    """Attach tenant-owned durable maintenance memory without changing readiness or rank."""
    candidates_with_history = 0
    unresolved_issue_count = 0
    resolved_issue_count = 0

    for candidate in response.get("truck_candidates", []):
        if not isinstance(candidate, dict):
            continue
        truck_number = str(candidate.get("truck_number") or "").strip()
        issues = durable_by_truck.get(truck_number.casefold(), [])
        enriched: list[dict[str, Any]] = []
        unresolved_for_truck = 0
        resolved_for_truck = 0

        for issue in issues:
            if not isinstance(issue, dict):
                continue
            lifecycle_state = str(issue.get("lifecycle_state") or "").strip().casefold()
            is_unresolved = lifecycle_state in {"open", "reopened"}
            is_resolved = lifecycle_state == "resolved"
            if is_unresolved:
                unresolved_for_truck += 1
            elif is_resolved:
                resolved_for_truck += 1
            enriched.append(
                {
                    **issue,
                    "recurring": int(issue.get("open_observation_count") or 0) >= 2,
                    "unresolved": is_unresolved,
                    "dispatcher_summary": _durable_issue_summary(truck_number, issue),
                }
            )

        if enriched:
            candidates_with_history += 1
        unresolved_issue_count += unresolved_for_truck
        resolved_issue_count += resolved_for_truck
        candidate["durable_maintenance_context"] = {
            "issues": enriched,
            "issue_count": len(enriched),
            "unresolved_issue_count": unresolved_for_truck,
            "resolved_issue_count": resolved_for_truck,
            "advisory_only": True,
            "changes_dispatch_readiness": False,
            "changes_ranking": False,
            "source": "polaris_durable_maintenance_memory",
            "provider_call_performed": False,
        }

    response["durable_maintenance_memory_summary"] = {
        "candidates_with_history": candidates_with_history,
        "unresolved_issue_count": unresolved_issue_count,
        "resolved_issue_count": resolved_issue_count,
        "advisory_only": True,
        "changes_dispatch_readiness": False,
        "changes_ranking": False,
        "provider_call_performed": False,
    }
    guardrails = response.setdefault("decision_guardrails", {})
    if isinstance(guardrails, dict):
        guardrails.update(
            {
                "durable_maintenance_memory_considered": True,
                "durable_maintenance_memory_is_advisory": True,
                "durable_maintenance_memory_changes_readiness": False,
                "durable_maintenance_memory_changes_ranking": False,
            }
        )
    return response


def _durable_issue_summary(truck_number: str, issue: dict[str, Any]) -> str:
    category = str(issue.get("part_category") or issue.get("part_name") or "maintenance").strip()
    part_type = str(issue.get("part_type") or "").strip()
    label = f"{category} / {part_type}" if part_type else category
    state = str(issue.get("lifecycle_state") or "unknown").strip().casefold()
    first_open = issue.get("first_open_date") or "unknown date"
    last_seen = issue.get("last_seen_date") or "unknown date"
    observation_count = int(issue.get("open_observation_count") or 0)
    recurring = observation_count >= 2

    if state in {"open", "reopened"}:
        descriptor = "reopened" if state == "reopened" else "unresolved recurring" if recurring else "unresolved"
        summary = (
            f"{truck_number} — {descriptor} {label} issue. First observed {first_open}; "
            f"last seen {last_seen}; {observation_count} open observation"
            f"{'s' if observation_count != 1 else ''}."
        )
        resolution_status = issue.get("explicit_resolution_status")
        resolution_date = issue.get("explicit_resolution_date")
        if state == "reopened" and resolution_status:
            summary += f" Previous explicit resolution status {resolution_status} recorded"
            if resolution_date:
                summary += f" on {resolution_date}"
            summary += "; issue later reopened."
        elif not resolution_status:
            summary += " No explicit repair/resolution recorded."
        return summary

    if state == "resolved":
        resolution_status = issue.get("explicit_resolution_status") or "resolved"
        resolution_date = issue.get("explicit_resolution_date") or "unknown date"
        return (
            f"{truck_number} — resolved {label} issue. First observed {first_open}; "
            f"last seen {last_seen}; explicit resolution status {resolution_status} recorded on {resolution_date}."
        )

    return f"{truck_number} — {label} maintenance history present with lifecycle state {state or 'unknown'}."


def classify_pickup_temporal_status(value: Any, *, reference_date: date) -> dict[str, Any]:
    pickup_date = _parse_iso_date(value)
    if pickup_date is None:
        status = "unknown"
        days_from_reference = None
    else:
        delta = (pickup_date - reference_date).days
        days_from_reference = delta
        status = "past" if delta < 0 else "upcoming" if delta > 0 else "today"
    return {
        "status": status,
        "scheduled_date": pickup_date.isoformat() if pickup_date else None,
        "reference_date": reference_date.isoformat(),
        "days_from_reference": days_from_reference,
        "comparison_basis": "calendar_date_only",
        "pickup_timezone_certified": False,
        "appointment_overdue_confirmed": False,
    }


def classify_assignment_consistency(status: Any, current_assignment: dict[str, Any]) -> dict[str, Any]:
    normalized_status = str(status or "").strip().lower()
    values = {
        "driver_name": _present_text(current_assignment.get("driver_name")),
        "truck_number": _present_text(current_assignment.get("truck_number")),
        "trailer_number": _present_text(current_assignment.get("trailer_number")),
    }
    missing = [field for field, present in values.items() if not present]
    reason_codes: list[str] = []
    classification = "consistent_or_not_applicable"
    if normalized_status == "assigned" and len(missing) == len(values):
        classification = "assigned_without_assignment_details"
        reason_codes.append("assigned_status_without_assignment_details")
    elif normalized_status == "assigned" and missing:
        classification = "assigned_with_partial_assignment_details"
        reason_codes.append("assigned_status_with_partial_assignment_details")
    return {
        "consistent": not reason_codes,
        "classification": classification,
        "missing_fields": missing if normalized_status == "assigned" else [],
        "reason_codes": reason_codes,
        "source": "torqueai_durable_dispatch",
    }


def _recalculate_readiness_summary(response: dict[str, Any]) -> None:
    trucks = [candidate for candidate in response.get("truck_candidates", []) if isinstance(candidate, dict)]
    counts = {"ready": 0, "verify": 0, "not_suitable": 0}
    for candidate in trucks:
        readiness = candidate.get("dispatch_readiness")
        if not isinstance(readiness, dict):
            continue
        classification = readiness.get("classification")
        if classification in counts:
            counts[classification] += 1
    top = trucks[0].get("dispatch_readiness") if trucks else None
    response["readiness_summary"] = {
        **counts,
        "top_ranked_truck_readiness": top.get("classification") if isinstance(top, dict) else None,
    }


def _parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _present_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
