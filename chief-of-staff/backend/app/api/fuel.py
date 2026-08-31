"""Fuel evidence import API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.connectors.outlook import OutlookConnector
from app.connectors.outlook_credentials import OutlookCredentialStore
from app.database.database import SessionLocal
from app.fuel.outlook_import import BvdPcnOutlookImportError, import_latest_bvd_pcn_outlook
from app.organizations.models import Organization
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission


router = APIRouter(prefix="/api/v1/fuel", tags=["fuel"])


def _db() -> Session:
    with SessionLocal() as session:
        yield session


@router.post("/bvd/pcn/import-outlook-latest")
def import_latest_bvd_pcn_from_outlook(
    currency: str = Query(..., min_length=3, max_length=3),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Manually import the latest trusted BVD PCN email for CAD or USD."""

    organization = (
        session.query(Organization)
        .filter(Organization.id == principal.organization_id)
        .one_or_none()
    )
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    expected_company_name = organization.legal_name or organization.display_name
    connector = OutlookConnector(
        credential_store=OutlookCredentialStore(principal.organization_id)
    )
    try:
        return import_latest_bvd_pcn_outlook(
            session,
            principal.organization_id,
            connector=connector,
            expected_company_name=expected_company_name,
            currency=currency,
        )
    except BvdPcnOutlookImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
