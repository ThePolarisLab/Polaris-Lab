"""Eco Petroleum fuel-price report parsing and durable evidence ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
import re

from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.models.fuel import FuelPriceEvidence, FuelPriceImportRun


SUPPLIER = "eco"
SOURCE_KIND = "price_report_pdf"
_FILENAME_RE = re.compile(r"^(CAD|USD)_Pricing_[A-Za-z0-9._-]+_(\d{4}-\d{2}-\d{2})\.pdf$", re.IGNORECASE)
_REPORT_LINE_RE = re.compile(r"^(CAD|USD)\s*\|\s*(\d{4}-\d{2}-\d{2})$", re.IGNORECASE)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class EcoPriceImportError(RuntimeError):
    """Safe Eco price-report source-contract failure."""

    def __init__(self, category: str) -> None:
        super().__init__("Eco price report import failed validation.")
        self.category = category


@dataclass(frozen=True)
class EcoPriceRow:
    brand: str
    supplier_site_id: str
    location_name: str
    region_code: str
    product_code: str
    contracted_price: str
    retail_price: str | None = None
    savings: str | None = None
    eco_price: str | None = None
    eco_gst_hst: str | None = None
    eco_total_price: str | None = None


@dataclass(frozen=True)
class EcoPriceDocument:
    currency: str
    effective_date: date
    company_name: str
    rows: tuple[EcoPriceRow, ...]


def parse_eco_price_pdf(content: bytes, *, filename: str) -> EcoPriceDocument:
    """Parse one certified Eco CAD/USD pricing PDF preserving decimal text."""

    expected_currency, filename_date = _filename_contract(filename)
    try:
        reader = PdfReader(BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise EcoPriceImportError("source_contract_error") from exc
    if not pages or not any(page.strip() for page in pages):
        raise EcoPriceImportError("source_contract_error")

    document = parse_eco_price_text("\n".join(pages), expected_currency=expected_currency)
    if document.effective_date != filename_date:
        raise EcoPriceImportError("effective_date_mismatch")
    return document


def parse_eco_price_text(text: str, *, expected_currency: str | None = None) -> EcoPriceDocument:
    """Parse the provider text contract exposed by Eco's price-report PDFs."""

    lines = [_clean(line) for line in str(text or "").splitlines() if _clean(line)]
    try:
        report_index = lines.index("Fuel Price Report")
    except ValueError as exc:
        raise EcoPriceImportError("source_contract_error") from exc
    if report_index + 2 >= len(lines):
        raise EcoPriceImportError("source_contract_error")

    company_name = lines[report_index + 1]
    report_match = _REPORT_LINE_RE.fullmatch(lines[report_index + 2])
    if not company_name or report_match is None:
        raise EcoPriceImportError("source_contract_error")
    currency = report_match.group(1).upper()
    if expected_currency is not None and currency != str(expected_currency).strip().upper():
        raise EcoPriceImportError("currency_contract_error")
    try:
        effective_date = date.fromisoformat(report_match.group(2))
    except ValueError as exc:
        raise EcoPriceImportError("source_contract_error") from exc

    rows: list[EcoPriceRow] = []
    for index, line in enumerate(lines):
        if not _DATE_RE.fullmatch(line) or index < 8:
            continue
        values = lines[index - 8 : index]
        if not values[1].isdigit():
            continue
        if line != effective_date.isoformat():
            raise EcoPriceImportError("effective_date_mismatch")
        rows.append(_normalize_row(values, currency=currency))

    if not rows:
        raise EcoPriceImportError("source_contract_error")
    if len({row.supplier_site_id for row in rows}) != len(rows):
        raise EcoPriceImportError("duplicate_site_error")

    return EcoPriceDocument(
        currency=currency,
        effective_date=effective_date,
        company_name=company_name,
        rows=tuple(rows),
    )


def import_eco_price_pdf(
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
    """Persist immutable Eco price evidence with exact-file replay protection."""

    started = datetime.now(timezone.utc)
    source_hash = sha256(content).hexdigest()
    currency: str | None = None
    run = (
        db.query(FuelPriceImportRun)
        .filter(
            FuelPriceImportRun.organization_id == organization_id,
            FuelPriceImportRun.supplier == SUPPLIER,
            FuelPriceImportRun.source_sha256 == source_hash,
        )
        .one_or_none()
    )
    if run is not None and run.status == "completed":
        return _result(run, status="idempotent_replay", replayed=True)

    if run is None:
        run = FuelPriceImportRun(
            organization_id=organization_id,
            supplier=SUPPLIER,
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
        run.currency = None
        run.status = "processing"
        run.error_category = None
        run.records_read = 0
        run.records_inserted = 0
        run.started_at = started
        run.completed_at = None

    try:
        currency, _ = _filename_contract(source_filename)
        run.currency = currency
        document = parse_eco_price_pdf(content, filename=source_filename)
        if _company_key(document.company_name) != _company_key(expected_company_name):
            raise EcoPriceImportError("company_identity_mismatch")

        run.company_name = document.company_name
        run.effective_start = document.effective_date
        run.effective_end = document.effective_date
        run.records_read = len(document.rows)
        if run.evidence:
            run.evidence.clear()
            db.flush()

        for row in document.rows:
            db.add(
                FuelPriceEvidence(
                    organization_id=organization_id,
                    import_run_id=run.id,
                    supplier=SUPPLIER,
                    source_sha256=source_hash,
                    currency=document.currency,
                    company_name=document.company_name,
                    effective_start=document.effective_date,
                    effective_end=document.effective_date,
                    supplier_site_id=row.supplier_site_id,
                    brand=row.brand,
                    location_name=row.location_name,
                    region_code=row.region_code,
                    product_code=row.product_code,
                    eco_price=row.eco_price,
                    eco_gst_hst=row.eco_gst_hst,
                    eco_total_price=row.eco_total_price,
                    retail_price=row.retail_price,
                    contracted_price=row.contracted_price,
                    savings=row.savings,
                )
            )

        run.records_inserted = len(document.rows)
        run.status = "completed"
        run.error_category = None
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        return _result(run, status="import_success", replayed=False)
    except EcoPriceImportError as exc:
        db.rollback()
        run = (
            db.query(FuelPriceImportRun)
            .filter(
                FuelPriceImportRun.organization_id == organization_id,
                FuelPriceImportRun.supplier == SUPPLIER,
                FuelPriceImportRun.source_sha256 == source_hash,
            )
            .one_or_none()
        )
        if run is None:
            run = FuelPriceImportRun(
                organization_id=organization_id,
                supplier=SUPPLIER,
                source_kind=SOURCE_KIND,
                source_message_id=source_message_id,
                source_attachment_id=source_attachment_id,
                source_filename=source_filename,
                source_received_at=source_received_at,
                source_sha256=source_hash,
                currency=currency,
                started_at=started,
            )
            db.add(run)
        run.status = "failed"
        run.error_category = exc.category
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        return _result(run, status="import_failed", replayed=False)


def _normalize_row(values: list[str], *, currency: str) -> EcoPriceRow:
    brand, site_id, location, region, product = values[:5]
    if not brand or not site_id.isdigit() or not location or not region or not product:
        raise EcoPriceImportError("source_contract_error")

    if currency == "USD":
        retail = _decimal_text(values[5])
        your_price = _decimal_text(values[6])
        savings = _decimal_text(values[7])
        return EcoPriceRow(
            brand=brand,
            supplier_site_id=site_id,
            location_name=location,
            region_code=region.upper(),
            product_code=product.upper(),
            retail_price=retail,
            contracted_price=your_price,
            savings=savings,
        )

    price = _decimal_text(values[5])
    gst_hst = _decimal_text(values[6])
    total_price = _decimal_text(values[7])
    return EcoPriceRow(
        brand=brand,
        supplier_site_id=site_id,
        location_name=location,
        region_code=region.upper(),
        product_code=product.upper(),
        eco_price=price,
        eco_gst_hst=gst_hst,
        eco_total_price=total_price,
        contracted_price=total_price,
    )


def _filename_contract(filename: str) -> tuple[str, date]:
    match = _FILENAME_RE.fullmatch(str(filename or "").strip())
    if match is None:
        raise EcoPriceImportError("source_contract_error")
    try:
        return match.group(1).upper(), date.fromisoformat(match.group(2))
    except ValueError as exc:
        raise EcoPriceImportError("source_contract_error") from exc


def _decimal_text(value: str) -> str:
    text = _clean(value)
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise EcoPriceImportError("source_contract_error") from exc
    if not number.is_finite():
        raise EcoPriceImportError("source_contract_error")
    return text


def _company_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _result(run: FuelPriceImportRun, *, status: str, replayed: bool) -> dict[str, object]:
    return {
        "status": status,
        "supplier": run.supplier,
        "source_kind": run.source_kind,
        "currency": run.currency,
        "effective_start": run.effective_start.isoformat() if run.effective_start else None,
        "effective_end": run.effective_end.isoformat() if run.effective_end else None,
        "records_read": int(run.records_read or 0),
        "records_inserted": int(run.records_inserted or 0),
        "replayed": replayed,
        "error_category": run.error_category,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "supplier_api_called": False,
        "secrets_exposed": False,
    }
