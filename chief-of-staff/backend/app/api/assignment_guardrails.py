"""Guardrail layer for read-only Assignment Intelligence.

This module deliberately wraps the existing assignment engine instead of changing
its provider/ranking logic. It adds only load-level temporal and assignment-data
consistency checks and can conservatively downgrade an otherwise `ready`
candidate to `verify`.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.assignment_intelligence import _db, assignment_candidates as base_assignment_candidates
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
    """Return existing assignment intelligence plus conservative load guardrails."""
    response = base_assignment_candidates(
        load_number=load_number,
        hos_date=hos_date,
        principal=principal,
        session=session,
    )
    return apply_assignment_guardrails(response, reference_date=datetime.now(timezone.utc).date())


def apply_assignment_guardrails(response: dict[str, Any], *, reference_date: date) -> dict[str, Any]:
    load = response.get("load") if isinstance(response.get("load"), dict) else {}
    pickup = load.get("pickup") if isinstance(load.get("pickup"), dict) else {}
    current_assignment = load.get("current_assignment") if isinstance(load.get("current_assignment"), dict) else {}

    temporal = classify_pickup_temporal_status(pickup.get("scheduled_date"), reference_date=reference_date)
    consistency = classify_assignment_consistency(load.get("status"), current_assignment)

    response["load_guardrails"] = {
        "pickup_temporal": temporal,
        "assignment_consistency": consistency,
    }

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
    top_classification = top.get("classification") if isinstance(top, dict) else None
    response["readiness_summary"] = {
        **counts,
        "top_ranked_truck_readiness": top_classification,
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
