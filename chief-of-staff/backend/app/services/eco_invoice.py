"""Eco Petroleum fuel-invoice parsing against the certified CAD/USD layouts."""

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


SUPPLIER = "eco"
_FILENAME_RE = re.compile(
    r"^.+_(?P<start>\d{2}-\d{2})_(?P<end>\d{2}-\d{2})_(?P<currency>CAD|USD)\.pdf$",
    re.IGNORECASE,
)
_ECO_CATEGORY = {
    "ULSD": "TRUCK_FUEL",
    "ULSR": "REEFER_FUEL",
    "DEFD": "DEF",
    "MC": "MONEY_CODE",
}


def parse_eco_invoice_pdf(content: bytes, filename: str) -> FuelInvoiceDocument:
    """Parse one Eco CAD/USD weekly fuel invoice preserving provider values."""

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
    company_name, invoice_number, period_start, period_end, currency = _header(pages[0], text)
    if currency != file_match.group("currency").upper():
        raise FuelInvoiceImportError("currency_contract_error")
    if period_start.strftime("%m-%d") != file_match.group("start"):
        raise FuelInvoiceImportError("period_contract_error")
    if period_end.strftime("%m-%d") != file_match.group("end"):
        raise FuelInvoiceImportError("period_contract_error")

    lines: list[FuelInvoiceLine] = []
    # A transaction can straddle pages; remove only the repeated table headers.
    raw_lines = [
        line.strip()
        for page_text in pages
        for line in page_text.splitlines()
        if line.strip() and not _is_table_header(line.strip())
    ]
    index = 0
    while index < len(raw_lines):
        upper = _columns(raw_lines[index])
        if not raw_lines[index].startswith("***"):
            index += 1
            continue
        # The certified USD money-code layout may omit the driver cell.
        if (
            currency == "USD"
            and len(upper) == 10
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", upper[1])
            and upper[3] == "MC"
        ):
            upper.insert(1, None)
        if not _is_transaction_upper(upper) or index + 1 >= len(raw_lines):
            raise FuelInvoiceImportError("source_contract_error")
        lower = _columns(raw_lines[index + 1])
        # MC is non-location evidence. Preserve both absent cells as NULL,
        # never shift financial fields or invent a city/state for these rows.
        if currency == "USD" and upper[4] == "MC" and len(lower) == 9:
            lower[2:2] = [None, None]

        if currency == "USD":
            if len(upper) != 11 or len(lower) != 11:
                raise FuelInvoiceImportError("source_contract_error")
            (
                card_number,
                driver_name,
                transaction_date,
                site_name,
                product_code,
                retail_price,
                savings_ppu,
                quantity,
                _total_quantity,
                transaction_fee,
                final_amount,
            ) = upper
            (
                unit_raw,
                transaction_time,
                site_city,
                region_code,
                sales_tax,
                billed_price,
                discount_amount,
                pre_tax_amount,
                total_amount,
                cash_amount,
                row_currency,
            ) = lower
            unit_price = None
        else:
            if len(upper) != 10 or len(lower) != 10:
                raise FuelInvoiceImportError("source_contract_error")
            (
                card_number,
                driver_name,
                transaction_date,
                site_name,
                product_code,
                unit_price,
                quantity,
                _total_quantity,
                transaction_fee,
                final_amount,
            ) = upper
            (
                unit_raw,
                transaction_time,
                site_city,
                region_code,
                sales_tax,
                billed_price,
                pre_tax_amount,
                total_amount,
                cash_amount,
                row_currency,
            ) = lower
            retail_price = None
            savings_ppu = None
            discount_amount = None

        if row_currency.upper() != currency:
            raise FuelInvoiceImportError("currency_contract_error")
        try:
            transaction_at = datetime.fromisoformat(f"{transaction_date} {transaction_time}")
        except ValueError as exc:
            raise FuelInvoiceImportError("source_contract_error") from exc
        code = product_code.upper()
        lines.append(
            FuelInvoiceLine(
                provider_transaction_id=None,
                card_number=card_number,
                driver_name=driver_name,
                unit_raw=unit_raw,
                transaction_at=transaction_at,
                supplier_site_id=None,
                site_name=site_name,
                site_city=site_city,
                region_code=region_code.upper() if region_code else None,
                product_code=code,
                category=_ECO_CATEGORY.get(code, "OTHER"),
                quantity=validate_decimal_text(quantity),
                retail_price=validate_decimal_text(retail_price) if retail_price else None,
                unit_price=validate_decimal_text(unit_price) if unit_price else None,
                billed_price=validate_decimal_text(billed_price),
                sales_tax=validate_decimal_text(sales_tax),
                discount_per_unit=validate_decimal_text(savings_ppu) if savings_ppu else None,
                discount_amount=validate_decimal_text(discount_amount) if discount_amount else None,
                transaction_fee=validate_decimal_text(transaction_fee),
                pre_tax_amount=validate_decimal_text(pre_tax_amount),
                total_amount=validate_decimal_text(total_amount),
                final_amount=validate_decimal_text(final_amount),
                cash_amount=validate_decimal_text(cash_amount),
            )
        )
        index += 2

    if not lines:
        raise FuelInvoiceImportError("source_contract_error")

    return FuelInvoiceDocument(
        supplier=SUPPLIER,
        invoice_number=invoice_number,
        currency=currency,
        company_name=company_name,
        invoice_date=None,
        period_start=period_start,
        period_end=period_end,
        due_date=None,
        lines=tuple(lines),
    )


def _header(page_text: str, text: str) -> tuple[str, str, date, date, str]:
    start_match = re.search(r"Start Date:\s*(\d{4}-\d{2}-\d{2})", text)
    end_match = re.search(r"End Date:\s*(\d{4}-\d{2}-\d{2})", text)
    invoice_match = re.search(r"Invoice #:\s*([A-Za-z0-9_-]+)", text)
    currency_match = re.search(r"Currency:\s*(CAD|USD)", text)
    company_name: str | None = None

    for raw_line in page_text.splitlines()[:16]:
        parts = _columns(raw_line)
        if len(parts) >= 3 and parts[2].startswith("Invoice #:"):
            company_name = parts[1]
            break

    if not all((start_match, end_match, invoice_match, currency_match, company_name)):
        raise FuelInvoiceImportError("source_contract_error")
    try:
        period_start = date.fromisoformat(start_match.group(1))
        period_end = date.fromisoformat(end_match.group(1))
    except ValueError as exc:
        raise FuelInvoiceImportError("source_contract_error") from exc
    if period_end < period_start:
        raise FuelInvoiceImportError("period_contract_error")
    return company_name, invoice_match.group(1), period_start, period_end, currency_match.group(1).upper()


def _is_table_header(line: str) -> bool:
    return (
        line.startswith("Card #")
        and "Driver Name" in line
        and line.endswith("Final AMT")
    ) or (
        line.startswith("Vehicle #")
        and "Time(CST)" in line
        and line.endswith("Currency")
    )


def _is_transaction_upper(parts: list[str | None]) -> bool:
    return (
        len(parts) in {10, 11}
        and parts[0].startswith("***")
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[2]) is not None
    )


def _columns(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s{2,}", text) if part.strip()]
