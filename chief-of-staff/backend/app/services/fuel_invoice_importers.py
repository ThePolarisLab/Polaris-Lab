"""Provider-specific durable fuel invoice import entrypoints."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.services.bvd_invoice import parse_bvd_invoice_pdf
from app.services.eco_invoice import parse_eco_invoice_pdf
from app.services.fuel_invoice import import_fuel_invoice_pdf


def import_bvd_invoice_pdf(
    db: Session,
    organization_id: str,
    *,
    content: bytes,
    source_filename: str,
    expected_company_name: str,
    source_message_id: str | None = None,
    source_attachment_id: str | None = None,
    source_received_at: datetime | None = None,
) -> dict[str, object]:
    return import_fuel_invoice_pdf(
        db,
        organization_id,
        supplier="bvd",
        content=content,
        source_filename=source_filename,
        expected_company_name=expected_company_name,
        parser=parse_bvd_invoice_pdf,
        source_message_id=source_message_id,
        source_attachment_id=source_attachment_id,
        source_received_at=source_received_at,
    )


def import_eco_invoice_pdf(
    db: Session,
    organization_id: str,
    *,
    content: bytes,
    source_filename: str,
    expected_company_name: str,
    source_message_id: str | None = None,
    source_attachment_id: str | None = None,
    source_received_at: datetime | None = None,
) -> dict[str, object]:
    return import_fuel_invoice_pdf(
        db,
        organization_id,
        supplier="eco",
        content=content,
        source_filename=source_filename,
        expected_company_name=expected_company_name,
        parser=parse_eco_invoice_pdf,
        source_message_id=source_message_id,
        source_attachment_id=source_attachment_id,
        source_received_at=source_received_at,
    )
