"""Fuel evidence import API."""

from __future__ import annotations

from typing import Any
from datetime import date

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.connectors.outlook import OutlookConnector
from app.connectors.outlook_credentials import OutlookCredentialStore
from app.database.database import SessionLocal
from app.fuel.eco_outlook_import import EcoPriceOutlookImportError, import_latest_eco_price_outlook
from app.fuel.eco_historical_import import import_historical_eco_price_outlook
from app.fuel.invoice_outlook_import import (
    FuelInvoiceOutlookImportError,
    import_latest_bvd_invoice_outlook,
    import_latest_eco_invoice_outlook,
)
from app.fuel.outlook_import import BvdPcnOutlookImportError, import_latest_bvd_pcn_outlook
from app.organizations.models import Organization
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission
from app.fuel.price_reconciliation import PricePreviewError, preview_invoice_prices
from app.fuel.discrepancy_review import (
    DiscrepancyReviewError,
    approve_discrepancy,
    approve_precision_discrepancies,
    reopen_discrepancy,
)


router = APIRouter(prefix="/api/v1/fuel", tags=["fuel"])


def _db() -> Session:
    with SessionLocal() as session:
        yield session


@router.get("/invoices/{invoice_run_id}/price-reconciliation")
def invoice_price_reconciliation(
    invoice_run_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Read-only evidence preview with separately persisted review disposition."""
    try:
        return preview_invoice_prices(session, principal.organization_id, invoice_run_id)
    except PricePreviewError as exc:
        raise HTTPException(status_code=404 if str(exc) == "invoice_not_found" else 409, detail=str(exc)) from exc


class DiscrepancyReviewRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


def _review_http_error(exc: ValueError) -> HTTPException:
    category = str(exc)
    return HTTPException(
        status_code=404 if category in {"invoice_not_found", "invoice_line_not_found"} else 409,
        detail=category,
    )


@router.post("/invoices/{invoice_run_id}/price-reconciliation/approve-precision")
def approve_precision_price_discrepancies(
    invoice_run_id: int,
    request: DiscrepancyReviewRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Approve only observed precision-sized discrepancies; never creates a tolerance rule."""
    try:
        return approve_precision_discrepancies(
            session,
            principal.organization_id,
            invoice_run_id,
            reviewer_identity_id=principal.identity_id,
            reviewer_role=principal.role,
            reason=request.reason,
        )
    except (PricePreviewError, DiscrepancyReviewError) as exc:
        raise _review_http_error(exc) from exc


@router.post("/invoices/{invoice_run_id}/price-reconciliation/{invoice_line_id}/approve")
def approve_price_discrepancy(
    invoice_run_id: int,
    invoice_line_id: int,
    request: DiscrepancyReviewRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Record approved-no-action separately from the immutable technical discrepancy."""
    try:
        return approve_discrepancy(
            session,
            principal.organization_id,
            invoice_run_id,
            invoice_line_id,
            reviewer_identity_id=principal.identity_id,
            reviewer_role=principal.role,
            reason=request.reason,
        )
    except (PricePreviewError, DiscrepancyReviewError) as exc:
        raise _review_http_error(exc) from exc


@router.post("/invoices/{invoice_run_id}/price-reconciliation/{invoice_line_id}/reopen")
def reopen_price_discrepancy(
    invoice_run_id: int,
    invoice_line_id: int,
    request: DiscrepancyReviewRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Append a reopen event without deleting the prior approval audit record."""
    try:
        return reopen_discrepancy(
            session,
            principal.organization_id,
            invoice_run_id,
            invoice_line_id,
            reviewer_identity_id=principal.identity_id,
            reviewer_role=principal.role,
            reason=request.reason,
        )
    except (PricePreviewError, DiscrepancyReviewError) as exc:
        raise _review_http_error(exc) from exc


def _organization_company_name(session: Session, organization_id: str) -> str:
    organization = (
        session.query(Organization)
        .filter(Organization.id == organization_id)
        .one_or_none()
    )
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization.legal_name or organization.display_name


@router.post("/bvd/pcn/import-outlook-latest")
def import_latest_bvd_pcn_from_outlook(
    currency: str = Query(..., min_length=3, max_length=3),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Manually import the latest trusted BVD PCN email for CAD or USD."""

    expected_company_name = _organization_company_name(session, principal.organization_id)
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


@router.post("/eco/prices/import-outlook-latest")
def import_latest_eco_price_from_outlook(
    currency: str = Query(..., min_length=3, max_length=3),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Manually import the latest trusted Eco pricing email for CAD or USD."""

    expected_company_name = _organization_company_name(session, principal.organization_id)
    connector = OutlookConnector(
        credential_store=OutlookCredentialStore(principal.organization_id)
    )
    try:
        return import_latest_eco_price_outlook(
            session,
            principal.organization_id,
            connector=connector,
            expected_company_name=expected_company_name,
            currency=currency,
        )
    except EcoPriceOutlookImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class EcoHistoricalPriceRequest(BaseModel):
    message_id: str = Field(min_length=1, max_length=2048)
    currency: str = Field(pattern="^(CAD|USD)$")
    effective_date: date


@router.post("/eco/prices/import-outlook-selected")
def import_selected_eco_price_from_outlook(
    request: EcoHistoricalPriceRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Explicit single-sheet import; no date range, scheduler or latest fallback."""
    try:
        return import_historical_eco_price_outlook(
            session, principal.organization_id,
            connector=OutlookConnector(credential_store=OutlookCredentialStore(principal.organization_id)),
            expected_company_name=_organization_company_name(session, principal.organization_id),
            **request.model_dump(),
        )
    except EcoPriceOutlookImportError as exc:
        raise HTTPException(status_code=400, detail=exc.category) from exc


@router.post("/bvd/invoices/import-outlook-latest")
def import_latest_bvd_invoice_from_outlook(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Manually import the newest trusted BVD fuel invoice from Outlook."""

    expected_company_name = _organization_company_name(session, principal.organization_id)
    connector = OutlookConnector(credential_store=OutlookCredentialStore(principal.organization_id))
    try:
        return import_latest_bvd_invoice_outlook(
            session,
            principal.organization_id,
            connector=connector,
            expected_company_name=expected_company_name,
        )
    except FuelInvoiceOutlookImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/eco/invoices/import-outlook-latest")
def import_latest_eco_invoice_from_outlook(
    currency: str = Query(..., min_length=3, max_length=3),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Manually import the newest trusted Eco CAD or USD fuel invoice from Outlook."""

    expected_company_name = _organization_company_name(session, principal.organization_id)
    connector = OutlookConnector(credential_store=OutlookCredentialStore(principal.organization_id))
    try:
        return import_latest_eco_invoice_outlook(
            session,
            principal.organization_id,
            connector=connector,
            expected_company_name=expected_company_name,
            currency=currency,
        )
    except FuelInvoiceOutlookImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
