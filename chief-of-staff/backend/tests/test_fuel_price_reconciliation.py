from datetime import date, datetime, timedelta, timezone
from dataclasses import replace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.fuel import router, _db
from app.database.database import Base
from app.fuel.price_reconciliation import PricePreviewError, preview_invoice_prices
from app.models.fuel import FuelPriceEvidence, FuelPriceImportRun
from app.models.fuel_invoice import FuelInvoiceImportRun, FuelInvoiceLineEvidence
from app.organizations.models import Organization
from app.security.dependencies import get_principal
from app.security.models import AuthenticatedPrincipal, Permission


DAY = date(2026, 8, 24)
NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)
COMPANY = "MOR LOGISTICS MANITOBA LIMITED"


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([Organization(id=o, slug=o, display_name=o, legal_name=COMPANY) for o in ("org-1", "org-2")])
        session.commit()
        yield session
    engine.dispose()


def invoice(db, **changes):
    run = FuelInvoiceImportRun(organization_id="org-1", supplier="eco", source_sha256="a"*64,
        source_filename="invoice.pdf", invoice_number="U1", currency="USD", company_name=COMPANY,
        status="completed", completed_at=NOW, records_read=1, records_inserted=1)
    db.add(run)
    db.flush()
    fields = dict(organization_id="org-1", import_run_id=run.id, supplier="eco", source_sha256="a"*64,
        invoice_number="U1", currency="USD", line_number=1, transaction_at=datetime(2026, 8, 24, 10),
        site_name="TA GRAND FORKS", site_city="GRAND FORKS", region_code="ND",
        product_code="ULSD", category="TRUCK_FUEL", quantity="100", billed_price="5.0000")
    fields.update(changes)
    line = FuelInvoiceLineEvidence(**fields)
    db.add(line)
    db.commit()
    return run, line


def quote(db, days=0, **changes):
    values = dict(organization_id="org-1", supplier="eco", currency="USD", company_name=COMPANY,
        effective_start=DAY-timedelta(days=days), effective_end=DAY-timedelta(days=days),
        supplier_site_id="123", location_name="TA GRAND FORKS", region_code="ND",
        product_code="ULSD", contracted_price="5.0")
    values.update(changes)
    n = db.query(FuelPriceImportRun).count() + 1
    run = FuelPriceImportRun(organization_id=values["organization_id"], supplier=values["supplier"],
        currency=values["currency"], company_name=values["company_name"], source_filename=f"quote-{n}.pdf",
        source_sha256=str(n)*64, status="completed", completed_at=NOW, records_read=1, records_inserted=1,
        effective_start=values["effective_start"], effective_end=values["effective_end"])
    db.add(run)
    db.flush()
    row = FuelPriceEvidence(import_run_id=run.id, source_sha256=run.source_sha256, **values)
    db.add(row)
    db.commit()
    return run, row


def result(db, run):
    return preview_invoice_prices(db, "org-1", run.id)["lines"][0]


@pytest.mark.parametrize("price,status,delta,impact", [
    ("5", "match", "0.0000", "0.0000"),
    ("4.9999", "price_difference", "0.0001", "0.0100"),
    ("5.0001", "price_difference", "-0.0001", "-0.0100"),
])
def test_exact_decimal_comparison(db, price, status, delta, impact):
    run, _ = invoice(db)
    quote(db, contracted_price=price)
    r = result(db, run)
    assert (r["status"], r["rate_difference"], r["analytical_impact"]) == (status, delta, impact)
    assert r["fallback_days"] == 0
    assert r["quote_source_sha256"]


@pytest.mark.parametrize("lag,expected", [(1, "fallback_match"), (7, "fallback_match"), (8, "unresolved"), (-1, "unresolved")])
def test_lookback_boundaries_and_no_future_quote(db, lag, expected):
    run, _ = invoice(db)
    quote(db, days=lag)
    r = result(db, run)
    assert r["status"] == expected
    if expected == "fallback_match":
        assert r["fallback_days"] == lag
        assert "prior-date quote used" in r["fallback_notice"]


def test_exact_preferred_over_prior_and_latest_prior_used(db):
    run, _ = invoice(db)
    quote(db, days=7, contracted_price="4")
    quote(db, days=2, contracted_price="4.5")
    assert result(db, run)["quote_price"] == "4.5"
    quote(db, contracted_price="5")
    assert result(db, run)["status"] == "match"


def test_overlapping_quotes_fail_closed(db):
    run, _ = invoice(db)
    quote(db)
    quote(db, days=1, effective_end=DAY)
    assert result(db, run)["reason"] == "ambiguous_quote"


def test_missing_sheet_and_missing_location_are_distinct(db):
    run, _ = invoice(db)
    assert result(db, run)["reason"] == "no_rate_sheet_imported"
    quote(db, location_name="TA OTHER STATION")
    assert result(db, run)["reason"] == "location_missing_from_rate_sheet"


def test_no_city_only_or_fuzzy_match(db):
    run, _ = invoice(db)
    quote(db, location_name="GRAND FORKS")
    quote(db, location_name="TA EXPRESS GRAND FORKS")
    assert result(db, run)["reason"] == "location_missing_from_rate_sheet"


def test_name_case_and_whitespace_normalization(db):
    run, _ = invoice(db, site_name=" ta   GRAND forks ")
    quote(db)
    assert result(db, run)["status"] == "match"


def test_bvd_id_match_and_product_mapping(db):
    run, line = invoice(db)
    run.supplier = line.supplier = "bvd"
    line.product_code = "TA"
    line.supplier_site_id = "123"
    db.commit()
    quote(db, supplier="bvd", site_name="TA GRAND FORKS", city="GRAND FORKS")
    assert result(db, run)["status"] == "match"
    line.supplier_site_id = "999"
    db.commit()
    assert result(db, run)["reason"] == "location_missing_from_rate_sheet"


@pytest.mark.parametrize("category,code", [
    ("MONEY_CODE", "MC"), ("OTHER", "CADV"),
])
def test_nonfuel_is_not_applicable(db, category, code):
    run, _ = invoice(db, category=category, product_code=code)
    quote(db)
    assert result(db, run)["status"] == "not_applicable"


@pytest.mark.parametrize("supplier,code", [("eco", "ULSR"), ("bvd", "TF")])
def test_reefer_fuel_uses_ulsd_quote_without_changing_classification(db, supplier, code):
    run, line = invoice(db, category="REEFER_FUEL", product_code=code)
    run.supplier = line.supplier = supplier
    if supplier == "bvd":
        line.supplier_site_id = "123"
    db.commit()
    quote(db, supplier=supplier, product_code="ULSD")
    r = result(db, run)
    assert r["status"] == "match"
    assert r["category"] == "REEFER_FUEL"
    assert r["product_code"] == code
    assert r["quote_price"] == "5.0"


@pytest.mark.parametrize("supplier,code", [("eco", "DEFD"), ("bvd", "DF")])
def test_def_uses_invoice_price_policy_and_leaves_quantity_pending(db, supplier, code):
    run, line = invoice(db, category="DEF", product_code=code)
    run.supplier = line.supplier = supplier
    db.commit()
    quote(db, supplier=supplier, product_code="ULSD")
    r = result(db, run)
    assert r["status"] == "not_applicable"
    assert r["reason"] == "supplier_def_rate_not_published"
    assert r["price_verification_basis"] == "invoice_billed_price_by_policy"
    assert r["quantity_verification_status"] == "pending_receipt_and_motive"
    assert r["quantity_required_evidence"] == ["fuel_receipt", "motive_fuel_entry"]
    assert "quote_evidence_id" not in r


def test_eco_cad_total_price_not_pretax(db):
    run, line = invoice(db, currency="CAD", billed_price="2.0928")
    run.currency = "CAD"
    db.commit()
    quote(db, currency="CAD", contracted_price="2.0928", eco_price="1.852", eco_gst_hst="0.2408", eco_total_price="2.0928")
    r = result(db, run)
    assert r["status"] == "match"
    assert r["quote_price_field"] == "Total Price"


def test_provider_arithmetic_anomaly_not_corrected(db):
    run, _ = invoice(db)
    _, q = quote(db, retail_price="6", savings="5", contracted_price="1.5")
    assert result(db, run)["reason"] == "quote_arithmetic_anomaly"
    assert q.contracted_price == "1.5"


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "oops", "-1", "1e9999"])
def test_invalid_numbers_unresolved(db, bad):
    run, _ = invoice(db)
    quote(db, contracted_price=bad)
    assert result(db, run)["reason"] == "invalid_numeric_evidence"


def test_tenant_isolation_and_no_writes(db):
    run, _ = invoice(db)
    quote(db, organization_id="org-2")
    assert result(db, run)["reason"] == "no_rate_sheet_imported"
    with pytest.raises(PricePreviewError, match="invoice_not_found"):
        preview_invoice_prices(db, "org-2", run.id)
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split()[0].upper())
    event.listen(db.bind, "before_cursor_execute", capture)
    result(db, run)
    assert statements and set(statements) == {"SELECT"}


def test_corrupt_quote_provenance_rejected(db):
    run, _ = invoice(db)
    _, q = quote(db)
    q.source_sha256 = "wrong"
    db.commit()
    with pytest.raises(PricePreviewError, match="quote_evidence_inconsistent"):
        result(db, run)


def test_incomplete_invoice_rejected(db):
    run, _ = invoice(db)
    run.records_inserted = 2
    db.commit()
    with pytest.raises(PricePreviewError, match="invoice_evidence_incomplete"):
        result(db, run)


@pytest.mark.parametrize("changes", [
    {"currency": "CAD"}, {"supplier": "bvd"}, {"company_name": "OTHER COMPANY"},
])
def test_unrelated_quotes_are_excluded(db, changes):
    run, _ = invoice(db)
    quote(db, **changes)
    assert result(db, run)["reason"] == "no_rate_sheet_imported"


def test_failed_and_incomplete_price_runs(db):
    run, _ = invoice(db)
    price_run, _ = quote(db)
    price_run.status = "failed"
    db.commit()
    assert result(db, run)["reason"] == "no_rate_sheet_imported"
    price_run.status = "completed"
    price_run.records_read = 2
    db.commit()
    with pytest.raises(PricePreviewError, match="quote_evidence_incomplete"):
        result(db, run)


def test_preview_limits_fail_without_partial_results(db, monkeypatch):
    from app.fuel import price_reconciliation as module
    run, _ = invoice(db)
    quote(db)
    monkeypatch.setattr(module, "MAX_QUOTE_ROWS", 0)
    with pytest.raises(PricePreviewError, match="quote_limit_exceeded"):
        result(db, run)


def test_bvd_unlabelled_product_stays_unresolved(db):
    run, line = invoice(db)
    run.supplier = line.supplier = "bvd"
    line.product_code = "TA"
    line.supplier_site_id = "123"
    db.commit()
    quote(db, supplier="bvd", product_code=None)
    assert result(db, run)["reason"] == "product_quote_unavailable"


def test_api_auth_permission_and_tenant_scope(db):
    run, _ = invoice(db)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_db] = lambda: db
    url = f"/api/v1/fuel/invoices/{run.id}/price-reconciliation"
    with TestClient(app) as client:
        assert client.get(url).status_code == 401
        principal = AuthenticatedPrincipal("id", "org-1", "m", "viewer", frozenset(), "test", "id")
        app.dependency_overrides[get_principal] = lambda: principal
        assert client.get(url).status_code == 403
        principal = replace(principal, permissions=frozenset({Permission.ORGANIZATION_READ}))
        assert client.get(url).status_code == 200
        principal = replace(principal, organization_id="org-2")
        assert client.get(url).status_code == 404
