"""BVD Petroleum fuel-invoice parsing against the certified provider layout."""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
import re

from pypdf import PdfReader

from app.services.fuel_invoice import (
    FuelInvoiceDocument,
    FuelInvoiceImportError,
    FuelInvoiceLine,
    validate_decimal_text,
)


SUPPLIER = "bvd"
_FILENAME_RE = re.compile(r"^BVD_invoice_(?P<invoice>\d+)\.pdf$", re.IGNORECASE)
_BVD_CATEGORY = {
    "TA": "TRUCK_FUEL",
    "TF": "REEFER_FUEL",
    "DF": "DEF",
}
_CURRENCY = {"CN": "CAD", "US": "USD", "CAD": "CAD", "USD": "USD"}


def parse_bvd_invoice_pdf(content: bytes, filename: str) -> FuelInvoiceDocument:
    """Parse a BVD fuel invoice while rejecting non-fuel Express-only invoices."""

    file_match = _FILENAME_RE.fullmatch(str(filename or "").strip())
    if file_match is None:
        raise FuelInvoiceImportError("source_contract_error")
    try:
        reader = PdfReader(BytesIO(content))
        pages = [page.extract_text(extraction_mode="layout") or "" for page in reader.pages]
    except Exception as exc:
        raise FuelInvoiceImportError("source_contract_error") from exc
    if not pages or not any(page.strip() for page in pages):
        raise FuelInvoiceImportError("source_contract_error")

    text = "\n".join(pages)
    if "Fuel Card Transactions" not in text:
        if "Express Codes" in text:
            raise FuelInvoiceImportError("non_fuel_invoice")
        raise FuelInvoiceImportError("source_contract_error")

    company_name, invoice_number, invoice_date, period_start, period_end, due_date = _header(pages[0])
    if invoice_number != file_match.group("invoice"):
        raise FuelInvoiceImportError("invoice_identity_mismatch")

    lines: list[FuelInvoiceLine] = []
    card_number: str | None = None
    currencies: set[str] = set()

    for page_text in pages:
        for raw_line in page_text.splitlines():
            parts = _columns(raw_line)
            if len(parts) == 2 and parts[0] == "Transactions for card":
                card_number = parts[1]
                continue
            if len(parts) not in {20, 21}:
                continue
            if not re.fullmatch(r"[A-Za-z0-9]+-[A-Za-z0-9]+", parts[0]):
                continue

            if len(parts) == 21:
                (
                    auth_code,
                    driver_name,
                    unit_raw,
                    transaction_text,
                    site_id,
                    site_name,
                    site_city,
                    region_code,
                    product_code,
                    quantity,
                    retail_price,
                    billed_price,
                    pre_tax_amount,
                    hst,
                    gst,
                    pst,
                    qst,
                    discount_rate,
                    discount_amount,
                    final_amount,
                    currency_code,
                ) = parts
            else:
                (
                    auth_code,
                    unit_raw,
                    transaction_text,
                    site_id,
                    site_name,
                    site_city,
                    region_code,
                    product_code,
                    quantity,
                    retail_price,
                    billed_price,
                    pre_tax_amount,
                    hst,
                    gst,
                    pst,
                    qst,
                    discount_rate,
                    discount_amount,
                    final_amount,
                    currency_code,
                ) = parts
                driver_name = None

            try:
                transaction_at = datetime.fromisoformat(transaction_text)
            except ValueError as exc:
                raise FuelInvoiceImportError("source_contract_error") from exc
            currency = _CURRENCY.get(currency_code.upper())
            if currency is None:
                raise FuelInvoiceImportError("currency_contract_error")
            currencies.add(currency)
            code = product_code.upper()
            lines.append(
                FuelInvoiceLine(
                    provider_transaction_id=auth_code,
                    card_number=card_number,
                    driver_name=driver_name,
                    unit_raw=unit_raw,
                    transaction_at=transaction_at,
                    supplier_site_id=site_id,
                    site_name=site_name,
                    site_city=site_city,
                    region_code=region_code.upper(),
                    product_code=code,
                    category=_BVD_CATEGORY.get(code, "OTHER"),
                    quantity=validate_decimal_text(quantity),
                    retail_price=validate_decimal_text(retail_price),
                    billed_price=validate_decimal_text(billed_price),
                    hst=validate_decimal_text(hst),
                    gst=validate_decimal_text(gst),
                    pst=validate_decimal_text(pst),
                    qst=validate_decimal_text(qst),
                    discount_per_unit=validate_decimal_text(discount_rate),
                    discount_amount=validate_decimal_text(discount_amount),
                    pre_tax_amount=validate_decimal_text(pre_tax_amount),
                    final_amount=validate_decimal_text(final_amount),
                )
            )

    if not lines or len(currencies) != 1:
        raise FuelInvoiceImportError("source_contract_error")

    return FuelInvoiceDocument(
        supplier=SUPPLIER,
        invoice_number=invoice_number,
        currency=next(iter(currencies)),
        company_name=company_name,
        invoice_date=invoice_date,
        period_start=period_start,
        period_end=period_end,
        due_date=due_date,
        lines=tuple(lines),
    )


def _header(page_text: str) -> tuple[str, str, date, date, date, date]:
    company_name: str | None = None
    invoice_number: str | None = None
    parsed_dates: tuple[date, date, date, date] | None = None

    for raw_line in page_text.splitlines()[:24]:
        parts = _columns(raw_line)
        if len(parts) >= 6 and parts[:5] == ["Number", "Invoice Date", "Start Date", "End Date", "Due Date"]:
            company_name = parts[5]
            continue
        if (
            len(parts) >= 5
            and parts[0].isdigit()
            and all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", item) for item in parts[1:5])
        ):
            try:
                parsed_dates = tuple(date.fromisoformat(item) for item in parts[1:5])  # type: ignore[assignment]
            except ValueError as exc:
                raise FuelInvoiceImportError("source_contract_error") from exc
            invoice_number = parts[0]

    if not company_name or not invoice_number or parsed_dates is None:
        raise FuelInvoiceImportError("source_contract_error")
    invoice_date, period_start, period_end, due_date = parsed_dates
    return company_name, invoice_number, invoice_date, period_start, period_end, due_date


def _columns(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s{2,}", text) if part.strip()]
