"""Bounded human review actions for supplier price discrepancies."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.fuel.price_reconciliation import preview_invoice_prices
from app.models.fuel_review import FuelDiscrepancyReviewEvent


OBSERVED_PRECISION_RATE_BAND = Decimal("0.0005")
DIFFERENCE_STATUSES = {"price_difference", "fallback_difference"}


class DiscrepancyReviewError(ValueError):
    """Sanitized review workflow failure."""


def _decimal(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise DiscrepancyReviewError("invalid_rate_difference")
    if not result.is_finite():
        raise DiscrepancyReviewError("invalid_rate_difference")
    return result


def _find_line(preview: dict, invoice_line_id: int) -> dict:
    for line in preview.get("lines", []):
        if line.get("invoice_line_id") == invoice_line_id:
            return line
    raise DiscrepancyReviewError("invoice_line_not_found")


def _is_precision_candidate(line: dict) -> bool:
    if line.get("status") not in DIFFERENCE_STATUSES:
        return False
    delta = abs(_decimal(line.get("rate_difference")))
    return Decimal("0") < delta <= OBSERVED_PRECISION_RATE_BAND


def _event_payload(event: FuelDiscrepancyReviewEvent, *, already_approved: bool = False) -> dict:
    return {
        "review_event_id": event.id,
        "invoice_run_id": event.invoice_run_id,
        "invoice_line_id": event.invoice_line_id,
        "action": event.action,
        "disposition": "approved_no_action" if event.action == "approved_no_action" else "not_reviewed",
        "approval_mode": event.approval_mode,
        "reason": event.reason,
        "reviewer_identity_id": event.reviewer_identity_id,
        "reviewer_role": event.reviewer_role,
        "reviewed_at": event.created_at.isoformat(),
        "technical_status": event.technical_status,
        "policy_version": event.policy_version,
        "invoice_billed_price": event.invoice_billed_price,
        "quote_price": event.quote_price,
        "rate_difference": event.rate_difference,
        "analytical_impact": event.analytical_impact,
        "already_approved": already_approved,
        "technical_status_unchanged": True,
        "accounting_side_effects": False,
    }


def _new_event(
    *,
    organization_id: str,
    invoice_run_id: int,
    line: dict,
    action: str,
    approval_mode: str | None,
    reason: str | None,
    reviewer_identity_id: str,
    reviewer_role: str,
    policy_version: str,
) -> FuelDiscrepancyReviewEvent:
    return FuelDiscrepancyReviewEvent(
        organization_id=organization_id,
        invoice_run_id=invoice_run_id,
        invoice_line_id=line["invoice_line_id"],
        action=action,
        approval_mode=approval_mode,
        reason=reason.strip() if reason and reason.strip() else None,
        reviewer_identity_id=reviewer_identity_id,
        reviewer_role=reviewer_role,
        technical_status=line.get("status") or "unknown",
        policy_version=policy_version,
        invoice_billed_price=line.get("invoice_billed_price"),
        quote_price=line.get("quote_price"),
        rate_difference=line.get("rate_difference"),
        analytical_impact=line.get("analytical_impact"),
    )


def approve_discrepancy(
    session: Session,
    organization_id: str,
    invoice_run_id: int,
    invoice_line_id: int,
    *,
    reviewer_identity_id: str,
    reviewer_role: str,
    reason: str | None = None,
) -> dict:
    preview = preview_invoice_prices(session, organization_id, invoice_run_id)
    line = _find_line(preview, invoice_line_id)
    if line.get("status") not in DIFFERENCE_STATUSES:
        raise DiscrepancyReviewError("line_not_price_difference")

    review = line.get("review") or {}
    if review.get("disposition") == "approved_no_action" and review.get("review_event_id"):
        event = session.get(FuelDiscrepancyReviewEvent, review["review_event_id"])
        if event is not None and event.organization_id == organization_id:
            return _event_payload(event, already_approved=True)

    precision_candidate = _is_precision_candidate(line)
    if not precision_candidate and not (reason and reason.strip()):
        raise DiscrepancyReviewError("approval_reason_required")

    event = _new_event(
        organization_id=organization_id,
        invoice_run_id=invoice_run_id,
        line=line,
        action="approved_no_action",
        approval_mode="individual_precision" if precision_candidate else "individual_material",
        reason=reason,
        reviewer_identity_id=reviewer_identity_id,
        reviewer_role=reviewer_role,
        policy_version=preview["policy_version"],
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return _event_payload(event)


def approve_precision_discrepancies(
    session: Session,
    organization_id: str,
    invoice_run_id: int,
    *,
    reviewer_identity_id: str,
    reviewer_role: str,
    reason: str | None = None,
) -> dict:
    preview = preview_invoice_prices(session, organization_id, invoice_run_id)
    approved_line_ids: list[int] = []
    skipped_line_ids: list[int] = []

    for line in preview.get("lines", []):
        if not _is_precision_candidate(line):
            continue
        review = line.get("review") or {}
        if review.get("disposition") == "approved_no_action":
            skipped_line_ids.append(line["invoice_line_id"])
            continue
        session.add(_new_event(
            organization_id=organization_id,
            invoice_run_id=invoice_run_id,
            line=line,
            action="approved_no_action",
            approval_mode="bulk_precision",
            reason=reason,
            reviewer_identity_id=reviewer_identity_id,
            reviewer_role=reviewer_role,
            policy_version=preview["policy_version"],
        ))
        approved_line_ids.append(line["invoice_line_id"])

    session.commit()
    return {
        "invoice_run_id": invoice_run_id,
        "disposition": "approved_no_action",
        "approved_count": len(approved_line_ids),
        "approved_line_ids": approved_line_ids,
        "skipped_already_approved_count": len(skipped_line_ids),
        "skipped_already_approved_line_ids": skipped_line_ids,
        "precision_band": format(OBSERVED_PRECISION_RATE_BAND, "f"),
        "technical_status_unchanged": True,
        "supplier_rounding_rule_inferred": False,
        "accounting_side_effects": False,
    }


def reopen_discrepancy(
    session: Session,
    organization_id: str,
    invoice_run_id: int,
    invoice_line_id: int,
    *,
    reviewer_identity_id: str,
    reviewer_role: str,
    reason: str | None = None,
) -> dict:
    preview = preview_invoice_prices(session, organization_id, invoice_run_id)
    line = _find_line(preview, invoice_line_id)
    review = line.get("review") or {}
    if review.get("disposition") != "approved_no_action":
        raise DiscrepancyReviewError("line_not_approved")

    event = _new_event(
        organization_id=organization_id,
        invoice_run_id=invoice_run_id,
        line=line,
        action="reopened",
        approval_mode="manual_reopen",
        reason=reason,
        reviewer_identity_id=reviewer_identity_id,
        reviewer_role=reviewer_role,
        policy_version=preview["policy_version"],
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return _event_payload(event)
