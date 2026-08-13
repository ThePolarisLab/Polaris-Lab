"""ACE in-bond reconciliation, exception lifecycle, search, and reporting helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.ace import AceInBondEvent, AceInBondMovement

TRACKED_FIELDS = (
    "record_status", "arrival_date", "export_date", "days_late", "days_overdue_for_export",
    "late_in_transit", "overdue_for_export", "penalty_indicator", "inbond_carrier_code",
    "manifest_carrier_code", "qp_filer_code", "transfer_of_liability_at",
)

MANUAL_AUTHORIZATION_STATUSES = {"UNAUTHORIZED - NO MOR PERMISSION", "AUTHORIZED", "AUTHORIZED - THIRD PARTY"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _text(value) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().upper() in {"Y", "YES", "TRUE", "1"}


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _datetime(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def normalized_payload(row: dict) -> dict:
    """Map a normalized ACE row into the persisted movement schema."""
    return {
        "inbond_number": str(row.get("inbond_number") or "").strip(),
        "bill_of_lading_number": str(row.get("bill_of_lading_number") or "").strip(),
        "inbond_type_code": _text(row.get("inbond_type_code")),
        "inbond_type_description": _text(row.get("inbond_type_description")),
        "source_type_description": _text(row.get("source_type_description")),
        "record_status": _text(row.get("record_status")),
        "inbond_carrier_code": _text(row.get("inbond_carrier_code")),
        "inbond_carrier_name": _text(row.get("inbond_carrier_name")),
        "bonded_carrier_code": _text(row.get("bonded_carrier_code")),
        "bonded_carrier_name": _text(row.get("bonded_carrier_name")),
        "manifest_carrier_code": _text(row.get("manifest_carrier_code")),
        "manifest_carrier_name": _text(row.get("manifest_carrier_name")),
        "qp_filer_code": _text(row.get("qp_filer_code")),
        "qp_filer_name": _text(row.get("qp_filer_name")),
        "shipper_name": _text(row.get("shipper_name")),
        "consignee_name": _text(row.get("consignee_name")),
        "origination_port_name": _text(row.get("origination_port_name")),
        "destination_port_name": _text(row.get("destination_port_name")),
        "create_date": _date(row.get("create_date")),
        "arrival_date": _date(row.get("arrival_date")),
        "export_date": _date(row.get("export_date")),
        "transfer_of_liability_at": _datetime(row.get("transfer_of_liability_at")),
        "days_late": _int(row.get("days_late")),
        "days_overdue_for_export": _int(row.get("days_overdue_for_export")),
        "late_in_transit": _bool(row.get("late_in_transit")),
        "overdue_for_export": _bool(row.get("overdue_for_export")),
        "penalty_indicator": _bool(row.get("penalty_indicator")),
    }


def review_reasons(movement: AceInBondMovement) -> list[str]:
    reasons: list[str] = []
    if movement.authorization_status == "UNAUTHORIZED - NO MOR PERMISSION":
        reasons.append("unauthorized")
    if (movement.record_status or "").lower() == "open":
        reasons.append("open")
    if movement.overdue_for_export:
        reasons.append("overdue_for_export")
    if movement.late_in_transit:
        reasons.append("late_in_transit")
    if movement.penalty_indicator:
        reasons.append("penalty")
    if movement.inbond_carrier_code == "MLVM" and movement.manifest_carrier_code not in (None, "", "MLVM"):
        reasons.append("carrier_mismatch")
    if movement.qp_filer_code == "8MH":
        reasons.append("qp_filer_review")
    return reasons


def refresh_review_state(movement: AceInBondMovement) -> tuple[str, str | None]:
    reasons = review_reasons(movement)
    if movement.resolved_at is not None:
        return "resolved", ", ".join(reasons) or movement.review_reason
    if "unauthorized" in reasons or "penalty" in reasons:
        return "critical", ", ".join(reasons)
    if reasons:
        return "review", ", ".join(reasons)
    return "clear", None


def reconcile_rows(db: Session, organization_id: str, rows: Iterable[dict]) -> dict:
    inserted = updated = exceptions = 0
    now = utcnow()

    for raw in rows:
        payload = normalized_payload(raw)
        if not payload["inbond_number"]:
            continue
        movement = (
            db.query(AceInBondMovement)
            .filter(
                AceInBondMovement.organization_id == organization_id,
                AceInBondMovement.inbond_number == payload["inbond_number"],
                AceInBondMovement.bill_of_lading_number == payload["bill_of_lading_number"],
            )
            .one_or_none()
        )

        if movement is None:
            movement = AceInBondMovement(organization_id=organization_id, **payload, first_seen_at=now, last_seen_at=now)
            movement.review_status, movement.review_reason = refresh_review_state(movement)
            db.add(movement)
            db.flush()
            db.add(AceInBondEvent(
                organization_id=organization_id, movement_id=movement.id,
                event_type="first_seen", detail="Movement first appeared in ACE", occurred_at=now,
            ))
            inserted += 1
            if movement.review_status in {"review", "critical"}:
                exceptions += 1
            continue

        old_review = movement.review_status
        changed = False
        for field, new_value in payload.items():
            old_value = getattr(movement, field)
            if old_value != new_value:
                setattr(movement, field, new_value)
                changed = True
                if field in TRACKED_FIELDS:
                    db.add(AceInBondEvent(
                        organization_id=organization_id,
                        movement_id=movement.id,
                        event_type="field_changed",
                        field_name=field,
                        old_value=str(old_value) if old_value is not None else None,
                        new_value=str(new_value) if new_value is not None else None,
                        occurred_at=now,
                    ))
        movement.last_seen_at = now
        movement.review_status, movement.review_reason = refresh_review_state(movement)
        if changed:
            updated += 1
        if old_review not in {"review", "critical"} and movement.review_status in {"review", "critical"}:
            exceptions += 1
            db.add(AceInBondEvent(
                organization_id=organization_id, movement_id=movement.id,
                event_type="exception_opened", detail=movement.review_reason, occurred_at=now,
            ))

    db.commit()
    return {"inserted": inserted, "updated": updated, "exceptions_created": exceptions}


def movement_query(db: Session, organization_id: str, *, search: str | None = None, status: str | None = None,
                   shipper: str | None = None, qp_filer: str | None = None, inbond_carrier: str | None = None,
                   bonded_carrier: str | None = None, manifest_carrier: str | None = None,
                   start_date: date | None = None, end_date: date | None = None, active_only: bool = False):
    query = db.query(AceInBondMovement).filter(AceInBondMovement.organization_id == organization_id)
    if search:
        token = f"%{search.strip()}%"
        query = query.filter(or_(
            AceInBondMovement.inbond_number.ilike(token),
            AceInBondMovement.bill_of_lading_number.ilike(token),
            AceInBondMovement.shipper_name.ilike(token),
            AceInBondMovement.consignee_name.ilike(token),
            AceInBondMovement.qp_filer_code.ilike(token),
            AceInBondMovement.qp_filer_name.ilike(token),
            AceInBondMovement.inbond_carrier_code.ilike(token),
            AceInBondMovement.inbond_carrier_name.ilike(token),
            AceInBondMovement.bonded_carrier_code.ilike(token),
            AceInBondMovement.bonded_carrier_name.ilike(token),
            AceInBondMovement.manifest_carrier_code.ilike(token),
            AceInBondMovement.manifest_carrier_name.ilike(token),
            AceInBondMovement.origination_port_name.ilike(token),
            AceInBondMovement.destination_port_name.ilike(token),
        ))
    if status:
        query = query.filter(AceInBondMovement.record_status == status)
    if shipper:
        query = query.filter(AceInBondMovement.shipper_name.ilike(f"%{shipper}%"))
    if qp_filer:
        query = query.filter(or_(AceInBondMovement.qp_filer_code.ilike(f"%{qp_filer}%"), AceInBondMovement.qp_filer_name.ilike(f"%{qp_filer}%")))
    if inbond_carrier:
        query = query.filter(or_(AceInBondMovement.inbond_carrier_code.ilike(f"%{inbond_carrier}%"), AceInBondMovement.inbond_carrier_name.ilike(f"%{inbond_carrier}%")))
    if bonded_carrier:
        query = query.filter(or_(AceInBondMovement.bonded_carrier_code.ilike(f"%{bonded_carrier}%"), AceInBondMovement.bonded_carrier_name.ilike(f"%{bonded_carrier}%")))
    if manifest_carrier:
        query = query.filter(or_(AceInBondMovement.manifest_carrier_code.ilike(f"%{manifest_carrier}%"), AceInBondMovement.manifest_carrier_name.ilike(f"%{manifest_carrier}%")))
    if start_date:
        query = query.filter(AceInBondMovement.create_date >= start_date)
    if end_date:
        query = query.filter(AceInBondMovement.create_date <= end_date)
    if active_only:
        query = query.filter(AceInBondMovement.resolved_at.is_(None)).filter(or_(
            AceInBondMovement.record_status == "Open",
            AceInBondMovement.review_status.in_(["review", "critical"]),
            AceInBondMovement.export_date.is_(None),
        ))
    return query


def summary(db: Session, organization_id: str) -> dict:
    q = db.query(AceInBondMovement).filter(AceInBondMovement.organization_id == organization_id)
    return {
        "total": q.count(),
        "active": q.filter(AceInBondMovement.resolved_at.is_(None)).filter(or_(AceInBondMovement.record_status == "Open", AceInBondMovement.export_date.is_(None))).count(),
        "open": q.filter(AceInBondMovement.record_status == "Open").count(),
        "overdue": q.filter(AceInBondMovement.overdue_for_export.is_(True)).count(),
        "late": q.filter(AceInBondMovement.late_in_transit.is_(True)).count(),
        "penalties": q.filter(AceInBondMovement.penalty_indicator.is_(True)).count(),
        "exceptions": q.filter(AceInBondMovement.resolved_at.is_(None), AceInBondMovement.review_status.in_(["review", "critical"])).count(),
        "unauthorized": q.filter(AceInBondMovement.authorization_status == "UNAUTHORIZED - NO MOR PERMISSION", AceInBondMovement.resolved_at.is_(None)).count(),
    }
