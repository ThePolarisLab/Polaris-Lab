"""ACE operational, search, exception, and reporting API."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ace.outlook_import import import_latest_ace_outlook_report
from app.ace.service import AceImportValidationError, SAFE_IMPORT_ERROR, import_rows, movement_query, refresh_review_state, summary
from app.connectors.outlook import OutlookConnector
from app.connectors.outlook_credentials import OutlookCredentialStore
from app.database.database import SessionLocal
from app.models.ace import AceInBondEvent, AceInBondMovement
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/ace", tags=["ace"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class AceRow(BaseModel):
    inbond_number: str
    bill_of_lading_number: str = ""
    inbond_type_code: str | None = None
    inbond_type_description: str | None = None
    source_type_description: str | None = None
    record_status: str | None = None
    inbond_carrier_code: str | None = None
    inbond_carrier_name: str | None = None
    bonded_carrier_code: str | None = None
    bonded_carrier_name: str | None = None
    manifest_carrier_code: str | None = None
    manifest_carrier_name: str | None = None
    qp_filer_code: str | None = None
    qp_filer_name: str | None = None
    shipper_name: str | None = None
    consignee_name: str | None = None
    origination_port_name: str | None = None
    destination_port_name: str | None = None
    create_date: date | None = None
    arrival_date: date | None = None
    export_date: date | None = None
    transfer_of_liability_at: datetime | None = None
    days_late: int = 0
    days_overdue_for_export: int = 0
    late_in_transit: bool = False
    overdue_for_export: bool = False
    penalty_indicator: bool | None = None


class AceImportRequest(BaseModel):
    source_message_id: str
    source_filename: str | None = None
    source_received_at: datetime | None = None
    rows: list[AceRow]


class ResolutionRequest(BaseModel):
    resolution_notes: str


class AuthorizationRequest(BaseModel):
    authorization_status: str
    authorization_notes: str | None = None
    evidence_reference: str | None = None


def serialize_movement(m: AceInBondMovement, *, include_events: bool = False) -> dict:
    result = {
        "id": m.id,
        "inbond_number": m.inbond_number,
        "bill_of_lading_number": m.bill_of_lading_number,
        "inbond_type_code": m.inbond_type_code,
        "inbond_type_description": m.inbond_type_description,
        "source_type_description": m.source_type_description,
        "record_status": m.record_status,
        "inbond_carrier": {"code": m.inbond_carrier_code, "name": m.inbond_carrier_name},
        "bonded_carrier": {"code": m.bonded_carrier_code, "name": m.bonded_carrier_name},
        "manifest_carrier": {"code": m.manifest_carrier_code, "name": m.manifest_carrier_name},
        "qp_filer": {"code": m.qp_filer_code, "name": m.qp_filer_name},
        "shipper_name": m.shipper_name,
        "consignee_name": m.consignee_name,
        "origination_port_name": m.origination_port_name,
        "destination_port_name": m.destination_port_name,
        "create_date": m.create_date,
        "departure_date": None,
        "arrival_date": m.arrival_date,
        "export_date": m.export_date,
        "days_late": m.days_late,
        "days_overdue_for_export": m.days_overdue_for_export,
        "late_in_transit": m.late_in_transit,
        "overdue_for_export": m.overdue_for_export,
        "penalty_indicator": m.penalty_indicator,
        "transfer_of_liability_at": m.transfer_of_liability_at,
        "authorization_status": m.authorization_status,
        "authorization_notes": m.authorization_notes,
        "evidence_reference": m.evidence_reference,
        "review_status": m.review_status,
        "review_reason": m.review_reason,
        "resolved_at": m.resolved_at,
        "resolution_notes": m.resolution_notes,
        "first_seen_at": m.first_seen_at,
        "last_seen_at": m.last_seen_at,
    }
    if include_events:
        result["events"] = [
            {
                "id": e.id,
                "event_type": e.event_type,
                "field_name": e.field_name,
                "old_value": e.old_value,
                "new_value": e.new_value,
                "detail": e.detail,
                "occurred_at": e.occurred_at,
            }
            for e in sorted(m.events, key=lambda event: event.occurred_at, reverse=True)
        ]
    return result


@router.get("/summary")
def get_summary(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_READ)),
    db: Session = Depends(get_db),
):
    return summary(db, principal.organization_id)


@router.get("/movements")
def list_movements(
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    shipper: str | None = Query(default=None),
    inbond_number: str | None = Query(default=None),
    bol: str | None = Query(default=None),
    consignee: str | None = Query(default=None),
    qp_filer: str | None = Query(default=None),
    inbond_carrier: str | None = Query(default=None),
    bonded_carrier: str | None = Query(default=None),
    manifest_carrier: str | None = Query(default=None),
    origin_port: str | None = Query(default=None),
    destination_port: str | None = Query(default=None),
    inbond_type: str | None = Query(default=None),
    authorization_status: str | None = Query(default=None),
    exception_type: str | None = Query(default=None),
    open_closed: str | None = Query(default=None),
    late: bool | None = Query(default=None),
    overdue: bool | None = Query(default=None),
    penalty: bool | None = Query(default=None),
    transfer_of_liability: bool | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    active_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_READ)),
    db: Session = Depends(get_db),
):
    query = movement_query(
        db, principal.organization_id, search=search, status=status, shipper=shipper,
        qp_filer=qp_filer, inbond_carrier=inbond_carrier, bonded_carrier=bonded_carrier,
        manifest_carrier=manifest_carrier, start_date=start_date, end_date=end_date,
        active_only=active_only, inbond_number=inbond_number, bol=bol, consignee=consignee,
        origin_port=origin_port, destination_port=destination_port, inbond_type=inbond_type,
        authorization_status=authorization_status, exception_type=exception_type, open_closed=open_closed,
        late=late, overdue=overdue, penalty=penalty, transfer_of_liability=transfer_of_liability,
    )
    total = query.count()
    rows = query.order_by(AceInBondMovement.create_date.desc(), AceInBondMovement.id.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [serialize_movement(row) for row in rows]}


@router.get("/exceptions")
def list_exceptions(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_READ)),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AceInBondMovement)
        .filter(
            AceInBondMovement.organization_id == principal.organization_id,
            AceInBondMovement.resolved_at.is_(None),
            AceInBondMovement.review_status.in_(["review", "critical"]),
        )
        .order_by(AceInBondMovement.review_status.desc(), AceInBondMovement.last_seen_at.desc())
        .all()
    )
    return [serialize_movement(row) for row in rows]


@router.get("/movements/{movement_id}")
def get_movement(
    movement_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_READ)),
    db: Session = Depends(get_db),
):
    row = db.query(AceInBondMovement).filter(
        AceInBondMovement.id == movement_id,
        AceInBondMovement.organization_id == principal.organization_id,
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="ACE movement not found")
    return serialize_movement(row, include_events=True)


@router.post("/movements/import")
def import_movements(
    payload: AceImportRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_WRITE)),
    db: Session = Depends(get_db),
):
    try:
        return import_rows(
            db,
            principal.organization_id,
            source_message_id=payload.source_message_id,
            source_filename=payload.source_filename,
            source_received_at=payload.source_received_at,
            rows=[row.model_dump() for row in payload.rows],
        )
    except AceImportValidationError as exc:
        raise HTTPException(status_code=400, detail=SAFE_IMPORT_ERROR) from exc


@router.post("/import/outlook-latest")
def import_latest_outlook_report(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_WRITE)),
    db: Session = Depends(get_db),
):
    connector = OutlookConnector(credential_store=OutlookCredentialStore(principal.organization_id))
    return import_latest_ace_outlook_report(db, principal.organization_id, connector=connector)


@router.patch("/movements/{movement_id}/authorization")
def set_authorization(
    movement_id: int,
    payload: AuthorizationRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_WRITE)),
    db: Session = Depends(get_db),
):
    row = db.query(AceInBondMovement).filter(
        AceInBondMovement.id == movement_id,
        AceInBondMovement.organization_id == principal.organization_id,
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="ACE movement not found")
    old = row.authorization_status
    row.authorization_status = payload.authorization_status
    row.authorization_notes = payload.authorization_notes
    row.evidence_reference = payload.evidence_reference
    row.review_status, row.review_reason = refresh_review_state(row)
    db.add(AceInBondEvent(
        organization_id=principal.organization_id,
        movement_id=row.id,
        event_type="authorization_changed",
        field_name="authorization_status",
        old_value=old,
        new_value=row.authorization_status,
        occurred_at=datetime.now(timezone.utc),
    ))
    db.commit()
    db.refresh(row)
    return serialize_movement(row)


@router.post("/movements/{movement_id}/resolve")
def resolve_movement(
    movement_id: int,
    payload: ResolutionRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_WRITE)),
    db: Session = Depends(get_db),
):
    row = db.query(AceInBondMovement).filter(
        AceInBondMovement.id == movement_id,
        AceInBondMovement.organization_id == principal.organization_id,
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="ACE movement not found")
    now = datetime.now(timezone.utc)
    row.resolved_at = now
    row.resolution_notes = payload.resolution_notes
    row.review_status = "resolved"
    db.add(AceInBondEvent(
        organization_id=principal.organization_id,
        movement_id=row.id,
        event_type="resolved",
        detail=payload.resolution_notes,
        occurred_at=now,
    ))
    db.commit()
    db.refresh(row)
    return serialize_movement(row)


@router.post("/movements/{movement_id}/reopen")
def reopen_movement(
    movement_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_WRITE)),
    db: Session = Depends(get_db),
):
    row = db.query(AceInBondMovement).filter(
        AceInBondMovement.id == movement_id,
        AceInBondMovement.organization_id == principal.organization_id,
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="ACE movement not found")
    row.resolved_at = None
    row.resolution_notes = None
    row.review_status, row.review_reason = refresh_review_state(row)
    db.add(AceInBondEvent(
        organization_id=principal.organization_id,
        movement_id=row.id,
        event_type="reopened",
        occurred_at=datetime.now(timezone.utc),
    ))
    db.commit()
    db.refresh(row)
    return serialize_movement(row)
