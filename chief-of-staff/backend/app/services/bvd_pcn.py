"""BVD PCN price-file parsing and durable evidence ingestion."""

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


SUPPLIER = "bvd"
SOURCE_KIND = "pcn_pdf"
_EXPECTED_COLUMNS = (
    "Site",
    "Name",
    "City",
    "Prov",
    "Cost",
    "Freight",
    "Base",
    "FET",
    "PFT",
    "PCT",
    "Local",
    "Fuel",
    "SalesTax",
    "InTax",
    "QST",
    "Retail",
    "Your",
    "Savings",
)
_FILENAME_RE = re.compile(r"^pcn-(cad|usd)-.+\.pdf$", re.IGNORECASE)
_ROW_RE = re.compile(r"^\s*\d{5}\s")
_METADATA_RE = re.compile(
    r"(?m)^\s*(?P<start>\d{4}-\d{2}-\d{2})\s+to\s+"
    r"(?P<end>\d{4}-\d{2}-\d{2})\s{2,}(?P<company>.+?)\s*$"
)


class BvdPcnImportError(RuntimeError):
    """Safe source-contract failure without raw provider payload details."""

    def __init__(self, category: str) -> None:
        super().__init__("BVD PCN import failed validation.")
        self.category = category


@dataclass(frozen=True)
class BvdPcnPriceRow:
    supplier_site_id: str
    site_name: str
    city: str
    region_code: str
    cost: str
    freight: str
    base_price: str
    fet: str
    pft: str
    pct: str
    local_tax: str
    fuel_price: str
    sales_tax: str
    in_tax_price: str
    qst: str
    retail_price: str
    contracted_price: str
    savings: str


@dataclass(frozen=True)
class BvdPcnDocument:
    currency: str
    effective_start: date
    effective_end: date
    company_name: str
    rows: tuple[BvdPcnPriceRow, ...]


def parse_bvd_pcn_pdf(content: bytes, *, filename: str) -> BvdPcnDocument:
    """Parse one BVD PCN PDF while preserving provider-authored decimal text."""

    currency = _currency_from_filename(filename)
    try:
        reader = PdfReader(BytesIO(content))
        pages = [page.extract_text(extraction_mode="layout") or "" for page in reader.pages]
    except Exception as exc:  # pypdf raises several parser-specific exceptions.
        raise BvdPcnImportError("source_contract_error") from exc

    if not pages or not any(page.strip() for page in pages):
        raise BvdPcnImportError("source_contract_error")

    return parse_bvd_pcn_layout_text("\n\f\n".join(pages), currency=currency)


def parse_bvd_pcn_layout_text(text: str, *, currency: str) -> BvdPcnDocument:
    """Parse certified pypdf layout text; exposed separately for deterministic tests."""

    normalized_currency = str(currency or "").strip().upper()
    if normalized_currency not in {"CAD", "USD"}:
        raise BvdPcnImportError("currency_contract_error")

    metadata = _METADATA_RE.search(text)
    if metadata is None:
        raise BvdPcnImportError("source_contract_error")
    try:
        effective_start = date.fromisoformat(metadata.group("start"))
        effective_end = date.fromisoformat(metadata.group("end"))
    except ValueError as exc:
        raise BvdPcnImportError("source_contract_error") from exc
    if effective_end < effective_start:
        raise BvdPcnImportError("source_contract_error")

    company_name = _clean(metadata.group("company"))
    if not company_name:
        raise BvdPcnImportError("source_contract_error")

    parsed_rows: list[list[str]] = []
    for page_text in text.split("\n\f\n"):
        _parse_layout_page(page_text, parsed_rows)

    if not parsed_rows:
        raise BvdPcnImportError("source_contract_error")

    rows = tuple(_normalize_row(values) for values in parsed_rows)
    if len({row.supplier_site_id for row in rows}) != len(rows):
        raise BvdPcnImportError("duplicate_site_error")

    return BvdPcnDocument(
        currency=normalized_currency,
        effective_start=effective_start,
        effective_end=effective_end,
        company_name=company_name,
        rows=rows,
    )


def import_bvd_pcn_pdf(
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
    """Persist immutable BVD PCN evidence with exact-file replay protection."""

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
            currency=None,
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
        currency = _currency_from_filename(source_filename)
        run.currency = currency
        document = parse_bvd_pcn_pdf(content, filename=source_filename)
        if _company_key(document.company_name) != _company_key(expected_company_name):
            raise BvdPcnImportError("company_identity_mismatch")

        run.company_name = document.company_name
        run.effective_start = document.effective_start
        run.effective_end = document.effective_end
        run.records_read = len(document.rows)

        # A failed retry never retains partial rows: parsing and company validation
        # happen before evidence insertion, and prior evidence from this run is cleared.
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
                    effective_start=document.effective_start,
                    effective_end=document.effective_end,
                    supplier_site_id=row.supplier_site_id,
                    site_name=row.site_name,
                    city=row.city,
                    region_code=row.region_code,
                    cost=row.cost,
                    freight=row.freight,
                    base_price=row.base_price,
                    fet=row.fet,
                    pft=row.pft,
                    pct=row.pct,
                    local_tax=row.local_tax,
                    fuel_price=row.fuel_price,
                    sales_tax=row.sales_tax,
                    in_tax_price=row.in_tax_price,
                    qst=row.qst,
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
    except BvdPcnImportError as exc:
        db.rollback()
        # Re-load the run because rollback expires or removes the pending state.
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


def _parse_layout_page(page_text: str, parsed_rows: list[list[str]]) -> None:
    header_line: str | None = None
    name_start = city_start = prov_start = -1
    current: list[str] | None = None

    for line in page_text.splitlines():
        if line.strip().startswith("Site") and "Savings" in line:
            columns = tuple(re.split(r"\s{2,}", line.strip()))
            if columns != _EXPECTED_COLUMNS:
                raise BvdPcnImportError("source_contract_error")
            header_line = line
            name_start = line.find("Name")
            city_start = line.find("City")
            prov_start = line.find("Prov")
            if not (0 <= name_start < city_start < prov_start):
                raise BvdPcnImportError("source_contract_error")
            current = None
            continue

        if header_line is None:
            continue
        if "RETAIL PRICES ARE SUBJECT TO CHANGE AT ANY TIME" in line:
            header_line = None
            current = None
            continue
        if not line.strip():
            continue

        if _ROW_RE.match(line):
            values = re.split(r"\s{2,}", line.strip())
            if len(values) != len(_EXPECTED_COLUMNS):
                raise BvdPcnImportError("source_contract_error")
            current = values
            parsed_rows.append(current)
            continue

        if current is None:
            continue

        stripped = line.strip()
        leading = len(line) - len(line.lstrip())
        if name_start <= leading < city_start:
            current[1] = _clean(f"{current[1]} {stripped}")
        elif city_start <= leading < prov_start:
            current[2] = _clean(f"{current[2]} {stripped}")
        elif stripped and stripped != "Price" and not re.fullmatch(r"\d+\s*/\s*\d+", stripped):
            raise BvdPcnImportError("source_contract_error")


def _normalize_row(values: list[str]) -> BvdPcnPriceRow:
    supplier_site_id, site_name, city, region_code = (_clean(value) for value in values[:4])
    if not supplier_site_id.isdigit() or not site_name or not city or not region_code:
        raise BvdPcnImportError("source_contract_error")

    decimals = [_decimal_text(value) for value in values[4:]]
    return BvdPcnPriceRow(
        supplier_site_id=supplier_site_id,
        site_name=site_name,
        city=city,
        region_code=region_code.upper(),
        cost=decimals[0],
        freight=decimals[1],
        base_price=decimals[2],
        fet=decimals[3],
        pft=decimals[4],
        pct=decimals[5],
        local_tax=decimals[6],
        fuel_price=decimals[7],
        sales_tax=decimals[8],
        in_tax_price=decimals[9],
        qst=decimals[10],
        retail_price=decimals[11],
        contracted_price=decimals[12],
        savings=decimals[13],
    )


def _decimal_text(value: str) -> str:
    text = _clean(value)
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise BvdPcnImportError("source_contract_error") from exc
    if not number.is_finite():
        raise BvdPcnImportError("source_contract_error")
    return text


def _currency_from_filename(filename: str) -> str:
    match = _FILENAME_RE.match(str(filename or "").strip())
    if match is None:
        raise BvdPcnImportError("filename_contract_error")
    return match.group(1).upper()


def _company_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _result(run: FuelPriceImportRun, *, status: str, replayed: bool) -> dict[str, object]:
    return {
        "status": status,
        "supplier": run.supplier,
        "source_kind": run.source_kind,
        "source_found": True,
        "replayed": replayed,
        "currency": run.currency,
        "effective_start": run.effective_start.isoformat() if run.effective_start else None,
        "effective_end": run.effective_end.isoformat() if run.effective_end else None,
        "records_read": run.records_read,
        "records_inserted": run.records_inserted,
        "error_category": run.error_category,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }
