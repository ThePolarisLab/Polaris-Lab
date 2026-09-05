"""Read-only, evidence-backed supplier price comparison. No provider calls."""

from collections import Counter
from datetime import timedelta
from decimal import Decimal, InvalidOperation, localcontext

from sqlalchemy.orm import Session

from app.models.fuel import FuelPriceEvidence, FuelPriceImportRun
from app.models.fuel_invoice import FuelInvoiceImportRun, FuelInvoiceLineEvidence


POLICY_VERSION = "supplier-price-preview-v3"
MAX_INVOICE_LINES = 1000
MAX_QUOTE_ROWS = 20000
MAX_PRICE_RUNS = 500

# Evidence-backed Eco naming differences between invoice U9165021 and the
# supplier's 2026-08-23 through 2026-08-29 USD rate sheets. Keep this explicit:
# punctuation is otherwise significant and no fuzzy station matching is used.
ECO_STATION_NAME_ALIASES = {
    "ta express fairview": "ta express - fairview",
    "ta express grand forks": "ta express - grand forks",
}


class PricePreviewError(ValueError):
    """Bounded, sanitized read-model failure."""


def _key(value):
    # Do not remove punctuation, rewrite cities, or collapse station brands.
    return " ".join(str(value or "").split()).casefold()


def _decimal(value):
    try:
        result = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        raise PricePreviewError("invalid_numeric_evidence")
    if not result.is_finite() or result < 0 or len(result.as_tuple().digits) > 40 or abs(result.as_tuple().exponent) > 20:
        raise PricePreviewError("invalid_numeric_evidence")
    return result


def _station(line, quote):
    if line.supplier_site_id:
        # When a source ID exists, never fall back to a fuzzy name match.
        return (
            _key(line.supplier_site_id) == _key(quote.supplier_site_id)
            and bool(line.region_code)
            and _key(line.region_code) == _key(quote.region_code)
        )
    if line.supplier != "eco" or not all((line.site_name, line.site_city, line.region_code)):
        return False
    # Eco Location may be a station name or just a city. Only an exact full
    # station-name match or an explicit evidence-backed alias qualifies; a
    # city-only or fuzzy match is not enough.
    name = quote.site_name or quote.location_name
    invoice_name = _key(line.site_name)
    expected_quote_name = ECO_STATION_NAME_ALIASES.get(invoice_name, invoice_name)
    return (
        expected_quote_name == _key(name)
        and (not quote.city or _key(line.site_city) == _key(quote.city))
        and _key(line.region_code) == _key(quote.region_code)
    )


def _product(line, quote):
    # MOR's approved supplier policy uses the published ULSD quote for both
    # truck diesel and reefer diesel. Preserve the invoice product/category;
    # this only selects the applicable supplier quote for comparison.
    expected_by_supplier = {
        "bvd": {"TA": "ULSD", "TF": "ULSD"},
        "eco": {"ULSR": "ULSD"},
    }
    expected = expected_by_supplier.get(line.supplier, {}).get(line.product_code, line.product_code)
    return bool(quote.product_code) and _key(quote.product_code) == _key(expected)


def _compare(line, quote, run, day, lag):
    result = {
        "quote_evidence_id": quote.id,
        "quote_import_run_id": run.id,
        "quote_source_sha256": run.source_sha256,
        "quote_source_filename": run.source_filename,
        "quote_effective_start": quote.effective_start.isoformat(),
        "quote_effective_end": quote.effective_end.isoformat(),
        "selected_effective_date": day.isoformat(),
        "fallback_days": lag,
        "fallback_notice": "Exact effective-date quote unavailable; prior-date quote used." if lag else None,
        "quote_price": quote.contracted_price,
        "quote_price_field": "Total Price" if line.supplier == "eco" and line.currency == "CAD" else "Your Price",
    }
    try:
        with localcontext() as ctx:
            ctx.prec = 100
            quote_price = _decimal(quote.contracted_price)
            billed = _decimal(line.billed_price)
            quantity = _decimal(line.quantity)
            if line.supplier == "eco" and line.currency == "CAD":
                anomaly = (
                    _decimal(quote.eco_total_price) != quote_price
                    or _decimal(quote.eco_price) + _decimal(quote.eco_gst_hst) != quote_price
                )
            elif quote.retail_price is not None and quote.savings is not None:
                anomaly = _decimal(quote.retail_price) - _decimal(quote.savings) != quote_price
            else:
                anomaly = False
            if anomaly:
                return dict(result, status="unresolved", reason="quote_arithmetic_anomaly")
            delta = billed - quote_price
            return dict(
                result,
                status=("fallback_difference" if delta else "fallback_match") if lag else ("price_difference" if delta else "match"),
                reason=None,
                rate_difference=format(delta, "f"),
                analytical_impact=format(quantity * delta, "f"),
                impact_definition="invoice quantity × (invoice billed price − supplier quote)",
            )
    except PricePreviewError as exc:
        return dict(result, status="unresolved", reason=str(exc))


def _line_result(line, quotes, runs):
    base = {
        "invoice_line_id": line.id, "line_number": line.line_number,
        "category": line.category, "product_code": line.product_code,
        "currency": line.currency, "invoice_billed_price": line.billed_price,
        "invoice_quantity": line.quantity,
        "transaction_date": line.transaction_at.date().isoformat() if line.transaction_at else None,
        "date_basis": "supplier-reported transaction calendar date; no timezone conversion",
        "price_basis": {"CAD": "CAD/litre", "USD": "USD/gallon"}.get(line.currency),
    }
    if line.category in {"MONEY_CODE", "OTHER"}:
        return dict(base, status="not_applicable", reason="non_fuel_category")
    valid_codes = {"bvd": {"TA": "TRUCK_FUEL", "TF": "REEFER_FUEL", "DF": "DEF"}, "eco": {"ULSD": "TRUCK_FUEL", "ULSR": "REEFER_FUEL", "DEFD": "DEF"}}
    if valid_codes.get(line.supplier, {}).get(line.product_code) != line.category:
        return dict(base, status="unresolved", reason="unsupported_product")
    if line.category == "DEF":
        # BVD and Eco do not publish DEF rates. The invoice rate is therefore
        # the approved price basis, while quantity remains a separate evidence
        # gate requiring both the fuel receipt and the Motive fuel entry.
        return dict(
            base,
            status="not_applicable",
            reason="supplier_def_rate_not_published",
            price_verification_basis="invoice_billed_price_by_policy",
            quantity_verification_status="pending_receipt_and_motive",
            quantity_required_evidence=["fuel_receipt", "motive_fuel_entry"],
        )
    if not line.transaction_at or line.currency not in {"CAD", "USD"}:
        return dict(base, status="unresolved", reason="missing_date_or_currency")
    if not line.region_code or (not line.supplier_site_id and not all((line.site_name, line.site_city))):
        return dict(base, status="unresolved", reason="missing_station_identity")
    date = line.transaction_at.date()
    reason = "no_rate_sheet_imported"
    station_quotes = [q for q in quotes if _station(line, q)]
    for lag in range(8):
        day = date - timedelta(days=lag)
        active_runs = {rid: r for rid, r in runs.items() if r.effective_start <= day <= r.effective_end}
        stations = [q for q in station_quotes if q.import_run_id in active_runs and q.effective_start <= day <= q.effective_end]
        candidates = [q for q in stations if _product(line, q)]
        if active_runs and reason == "no_rate_sheet_imported":
            reason = "location_missing_from_rate_sheet"
        if stations:
            reason = "product_quote_unavailable"
        if len(candidates) > 1:
            return dict(base, status="unresolved", reason="ambiguous_quote", candidate_count=len(candidates))
        if candidates:
            chosen = candidates[0]
            return dict(base, **_compare(line, chosen, active_runs[chosen.import_run_id], day, lag))
    return dict(base, status="unresolved", reason=reason,
                resolution="Provide the missing supplier rate list or approved manual rate evidence; no rate is invented.")


def preview_invoice_prices(session: Session, organization_id: str, invoice_run_id: int):
    """Compare one completed tenant-owned invoice to bounded persisted quotes."""
    with session.no_autoflush:
        invoice = session.query(FuelInvoiceImportRun).filter_by(id=invoice_run_id, organization_id=organization_id).one_or_none()
        if invoice is None:
            raise PricePreviewError("invoice_not_found")
        if invoice.status != "completed" or invoice.error_category or not invoice.completed_at:
            raise PricePreviewError("invoice_not_completed")
        lines = session.query(FuelInvoiceLineEvidence).filter_by(
            organization_id=organization_id, import_run_id=invoice.id,
        ).order_by(FuelInvoiceLineEvidence.line_number).limit(MAX_INVOICE_LINES + 1).all()
        if len(lines) > MAX_INVOICE_LINES:
            raise PricePreviewError("invoice_limit_exceeded")
        if not lines or len(lines) != invoice.records_inserted or len(lines) != invoice.records_read:
            raise PricePreviewError("invoice_evidence_incomplete")
        if any(
            l.supplier != invoice.supplier or l.currency != invoice.currency
            or l.source_sha256 != invoice.source_sha256 or l.invoice_number != invoice.invoice_number
            or l.line_number != i for i, l in enumerate(lines, 1)
        ):
            raise PricePreviewError("invoice_evidence_inconsistent")
        dates = [l.transaction_at.date() for l in lines if l.transaction_at]
        runs = []
        quotes = []
        if dates:
            runs = session.query(FuelPriceImportRun).filter(
                FuelPriceImportRun.organization_id == organization_id,
                FuelPriceImportRun.supplier == invoice.supplier,
                FuelPriceImportRun.currency == invoice.currency,
                FuelPriceImportRun.company_name == invoice.company_name,
                FuelPriceImportRun.status == "completed",
                FuelPriceImportRun.error_category.is_(None),
                FuelPriceImportRun.completed_at.is_not(None),
                FuelPriceImportRun.effective_start <= max(dates),
                FuelPriceImportRun.effective_end >= min(dates) - timedelta(days=7),
            ).order_by(FuelPriceImportRun.id).limit(MAX_PRICE_RUNS + 1).all()
            if len(runs) > MAX_PRICE_RUNS:
                raise PricePreviewError("quote_limit_exceeded")
            if runs:
                quotes = session.query(FuelPriceEvidence).filter(
                    FuelPriceEvidence.organization_id == organization_id,
                    FuelPriceEvidence.import_run_id.in_([r.id for r in runs]),
                ).order_by(FuelPriceEvidence.id).limit(MAX_QUOTE_ROWS + 1).all()
                if len(quotes) > MAX_QUOTE_ROWS:
                    raise PricePreviewError("quote_limit_exceeded")
        by_id = {r.id: r for r in runs}
        counts = Counter(q.import_run_id for q in quotes)
        for run in runs:
            if counts[run.id] != run.records_inserted or counts[run.id] != run.records_read:
                raise PricePreviewError("quote_evidence_incomplete")
        for q in quotes:
            run = by_id[q.import_run_id]
            if (q.source_sha256 != run.source_sha256 or q.supplier != invoice.supplier
                or q.currency != invoice.currency or q.company_name != invoice.company_name
                or q.effective_start != run.effective_start or q.effective_end != run.effective_end):
                raise PricePreviewError("quote_evidence_inconsistent")
        results = [_line_result(line, quotes, by_id) for line in lines]
        return {
            "policy_version": POLICY_VERSION, "read_only": True,
            "invoice_run_id": invoice.id, "invoice_number": invoice.invoice_number,
            "invoice_source_sha256": invoice.source_sha256, "invoice_source_filename": invoice.source_filename,
            "currency": invoice.currency, "line_count": len(results),
            "summary": dict(Counter(r["status"] for r in results)), "lines": results,
            "scope": "supplier price only; not accounting adjustments or Motive reconciliation",
            "missing_sheet_definition": "No completed matching rate sheet is stored; mailbox receipt has not been checked.",
        }
