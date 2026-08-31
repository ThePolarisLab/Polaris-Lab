"""Shared durable supplier invoice evidence ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import re
from typing import Callable

from sqlalchemy.orm import Session

from app.models.fuel_invoice import FuelInvoiceImportRun, FuelInvoiceLineEvidence


SOURCE_KIND = "invoice_pdf"


class FuelInvoiceImportError(RuntimeError):
    """Safe supplier invoice source-contract failure."""

    def __init__(self, category: str) -> None:
        super().__init__("Fuel invoice import failed validation.")
        self.category = category


@dataclass(frozen=True)
class FuelInvoiceLine:
    provider_transaction_id: str | None
    card_number: str | None
    driver_name: str | None
    unit_raw: str | None
    transaction_at: datetime | None
    supplier_site_id: str | None
    site_name: str | None
    site_city: str | None
    region_code: str | None
    product_code: str
    category: str
    quantity: str
    billed_price: str
    retail_price: str | None = None
    unit_price: str | None = None
    sales_tax: str | None = None
    hst: str | None = None
    gst: str | None = None
    pst: str | None = None
    qst: str | None = None
    discount_per_unit: str | None = None
    discount_amount: str | None = None
    transaction_fee: str | None = None
    pre_tax_amount: str | None = None
    total_amount: str | None = None
    final_amount: str | None = None
    cash_amount: str | None = None


@dataclass(frozen=True)
class FuelInvoiceDocument:
    supplier: str
    invoice_number: str
    currency: str
    company_name: str
    invoice_date: date | None
    period_start: date
    period_end: date
    due_date: date | None
    lines: tuple[FuelInvoiceLine, ...]


InvoiceParser = Callable[[bytes, str], FuelInvoiceDocument]


def import_fuel_invoice_pdf(
    db: Session,
    organization_id: str,
    *,
    supplier: str,
    content: bytes,
    source_filename: str,
    expected_company_name: str,
    parser: InvoiceParser,
    source_message_id: str | None = None,
    source_attachment_id: str | None = None,
    source_received_at: datetime | None = None,
) -> dict[str, object]:
    """Persist one supplier invoice while preserving provider-authored line evidence."""

    supplier_key = _clean(supplier).casefold()
    if supplier_key not in {"bvd", "eco"}:
        raise FuelInvoiceImportError("supplier_contract_error")

    started = datetime.now(timezone.utc)
    source_hash = sha256(content).hexdigest()
    run = (
        db.query(FuelInvoiceImportRun)
        .filter(
            FuelInvoiceImportRun.organization_id == organization_id,
            FuelInvoiceImportRun.supplier == supplier_key,
            FuelInvoiceImportRun.source_sha256 == source_hash,
        )
        .one_or_none()
    )
    if run is not None and run.status == "completed":
        return _result(run, status="idempotent_replay", replayed=True)

    if run is None:
        run = FuelInvoiceImportRun(
            organization_id=organization_id,
            supplier=supplier_key,
            source_kind=SOURCE_KIND,
            source_message_id=source_message_id,
            source_attachment_id=source_attachment_id,
            source_filename=source_filename,
            source_received_at=source_received_at,
            source_sha256=source_hash,
            status="processing",
            started_at=started,
        )
        db.add(run)
        db.flush()
    else:
        run.source_message_id = source_message_id or run.source_message_id
        run.source_attachment_id = source_attachment_id or run.source_attachment_id
        run.source_filename = source_filename
        run.source_received_at = source_received_at or run.source_received_at
        run.status = "processing"
        run.error_category = None
        run.invoice_number = None
        run.currency = None
        run.company_name = None
        run.invoice_date = None
        run.period_start = None
        run.period_end = None
        run.due_date = None
        run.records_read = 0
        run.records_inserted = 0
        run.started_at = started
        run.completed_at = None

    try:
        document = parser(content, source_filename)
        if document.supplier != supplier_key:
            raise FuelInvoiceImportError("supplier_contract_error")
        if _company_key(document.company_name) != _company_key(expected_company_name):
            raise FuelInvoiceImportError("company_identity_mismatch")
        if not document.lines:
            raise FuelInvoiceImportError("source_contract_error")

        run.invoice_number = document.invoice_number
        run.currency = document.currency
        run.company_name = document.company_name
        run.invoice_date = document.invoice_date
        run.period_start = document.period_start
        run.period_end = document.period_end
        run.due_date = document.due_date
        run.records_read = len(document.lines)
        if run.lines:
            run.lines.clear()
            db.flush()

        for line_number, line in enumerate(document.lines, start=1):
            db.add(
                FuelInvoiceLineEvidence(
                    organization_id=organization_id,
                    import_run_id=run.id,
                    supplier=supplier_key,
                    source_sha256=source_hash,
                    invoice_number=document.invoice_number,
                    currency=document.currency,
                    line_number=line_number,
                    provider_transaction_id=line.provider_transaction_id,
                    card_number=line.card_number,
                    driver_name=line.driver_name,
                    unit_raw=line.unit_raw,
                    unit_normalized=normalize_unit(line.unit_raw),
                    transaction_at=line.transaction_at,
                    supplier_site_id=line.supplier_site_id,
                    site_name=line.site_name,
                    site_city=line.site_city,
                    region_code=line.region_code,
                    product_code=line.product_code,
                    category=line.category,
                    quantity=line.quantity,
                    retail_price=line.retail_price,
                    unit_price=line.unit_price,
                    billed_price=line.billed_price,
                    sales_tax=line.sales_tax,
                    hst=line.hst,
                    gst=line.gst,
                    pst=line.pst,
                    qst=line.qst,
                    discount_per_unit=line.discount_per_unit,
                    discount_amount=line.discount_amount,
                    transaction_fee=line.transaction_fee,
                    pre_tax_amount=line.pre_tax_amount,
                    total_amount=line.total_amount,
                    final_amount=line.final_amount,
                    cash_amount=line.cash_amount,
                )
            )

        run.records_inserted = len(document.lines)
        run.status = "completed"
        run.error_category = None
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        return _result(run, status="import_success", replayed=False)
    except FuelInvoiceImportError as exc:
        db.rollback()
        run = (
            db.query(FuelInvoiceImportRun)
            .filter(
                FuelInvoiceImportRun.organization_id == organization_id,
                FuelInvoiceImportRun.supplier == supplier_key,
                FuelInvoiceImportRun.source_sha256 == source_hash,
            )
            .one_or_none()
        )
        if run is None:
            run = FuelInvoiceImportRun(
                organization_id=organization_id,
                supplier=supplier_key,
                source_kind=SOURCE_KIND,
                source_message_id=source_message_id,
                source_attachment_id=source_attachment_id,
                source_filename=source_filename,
                source_received_at=source_received_at,
                source_sha256=source_hash,
                started_at=started,
            )
            db.add(run)
        run.status = "failed"
        run.error_category = exc.category
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        return _result(run, status="import_failed", replayed=False)


def normalize_unit(value: str | None) -> str | None:
    """Normalize truck IDs only where MOR's known optional leading-M rule applies."""

    text = _clean(value).upper()
    if not text:
        return None
    match = re.fullmatch(r"M?(\d+)", text)
    if match is None:
        return text
    return f"M{match.group(1)}"


def validate_decimal_text(value: object) -> str:
    """Validate a provider decimal while returning its exact cleaned display text."""

    text = _clean(value)
    if not text:
        raise FuelInvoiceImportError("source_contract_error")
    try:
        number = Decimal(text.replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise FuelInvoiceImportError("source_contract_error") from exc
    if not number.is_finite():
        raise FuelInvoiceImportError("source_contract_error")
    return text


def _company_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _result(run: FuelInvoiceImportRun, *, status: str, replayed: bool) -> dict[str, object]:
    return {
        "status": status,
        "supplier": run.supplier,
        "source_kind": run.source_kind,
        "invoice_number": run.invoice_number,
        "currency": run.currency,
        "period_start": run.period_start.isoformat() if run.period_start else None,
        "period_end": run.period_end.isoformat() if run.period_end else None,
        "records_read": int(run.records_read or 0),
        "records_inserted": int(run.records_inserted or 0),
        "replayed": replayed,
        "error_category": run.error_category,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "supplier_api_called": False,
        "secrets_exposed": False,
    }
