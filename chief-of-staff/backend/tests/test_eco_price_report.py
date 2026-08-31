from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.database import Base
from app.models.fuel import FuelPriceEvidence, FuelPriceImportRun
from app.organizations.models import Organization
from app.services import eco_price_report
from app.services.eco_price_report import (
    EcoPriceDocument,
    EcoPriceImportError,
    EcoPriceRow,
    import_eco_price_pdf,
    parse_eco_price_text,
)


USD_TEXT = """
This document is intended solely for Mor Logistics Manitoba Limited.
EcoPetroleum
Fuel Price Report
Mor Logistics Manitoba Limited
USD | 2026-08-24
Brand
Site
Location
State
Product
Retail
Your Price
Savings
Effective Date
TA / Petro
6948
TA EXPRESS - GRAND FORKS
ND
ULSD
5.659
5.0459
0.6131
2026-08-24
"""

CAD_TEXT = """
This document is intended solely for Mor Logistics Manitoba Limited.
EcoPetroleum
Fuel Price Report
Mor Logistics Manitoba Limited
CAD | 2026-08-25
Brand
Site
Location
Province
Product
Price
GST/HST
Total Price
Effective Date
Esso Commercial
546210
MISSISSAUGA
ON
ULSD
1.852
0.2408
2.0928
2026-08-25
"""


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add(Organization(id="org-1", slug="mor", display_name="MOR Logistics", legal_name="MOR LOGISTICS MANITOBA LIMITED"))
    db.add(Organization(id="org-2", slug="other", display_name="Other", legal_name="OTHER CARRIER LTD"))
    db.commit()
    return db


def _usd_row(site: str = "6948") -> EcoPriceRow:
    return EcoPriceRow(
        brand="TA / Petro",
        supplier_site_id=site,
        location_name="TA EXPRESS - GRAND FORKS",
        region_code="ND",
        product_code="ULSD",
        retail_price="5.659",
        contracted_price="5.0459",
        savings="0.6131",
    )


def _document(*rows: EcoPriceRow, currency: str = "USD") -> EcoPriceDocument:
    return EcoPriceDocument(
        currency=currency,
        effective_date=date(2026, 8, 24),
        company_name="Mor Logistics Manitoba Limited",
        rows=tuple(rows or (_usd_row(),)),
    )


def test_usd_parser_uses_provider_your_price_as_contracted_price() -> None:
    document = parse_eco_price_text(USD_TEXT, expected_currency="USD")

    assert document.currency == "USD"
    assert document.effective_date == date(2026, 8, 24)
    assert document.company_name == "Mor Logistics Manitoba Limited"
    assert len(document.rows) == 1
    row = document.rows[0]
    assert row.brand == "TA / Petro"
    assert row.supplier_site_id == "6948"
    assert row.location_name == "TA EXPRESS - GRAND FORKS"
    assert row.product_code == "ULSD"
    assert row.retail_price == "5.659"
    assert row.contracted_price == "5.0459"
    assert row.savings == "0.6131"
    assert row.eco_total_price is None


def test_cad_parser_preserves_price_tax_and_uses_total_price_for_invoice_comparison() -> None:
    document = parse_eco_price_text(CAD_TEXT, expected_currency="CAD")

    assert document.currency == "CAD"
    assert document.effective_date == date(2026, 8, 25)
    row = document.rows[0]
    assert row.brand == "Esso Commercial"
    assert row.supplier_site_id == "546210"
    assert row.location_name == "MISSISSAUGA"
    assert row.eco_price == "1.852"
    assert row.eco_gst_hst == "0.2408"
    assert row.eco_total_price == "2.0928"
    assert row.contracted_price == "2.0928"
    assert row.retail_price is None
    assert row.savings is None


def test_parser_fails_closed_when_row_effective_date_differs_from_report() -> None:
    bad = CAD_TEXT.replace("2026-08-25\n", "2026-08-25\n", 1).rsplit("2026-08-25", 1)[0] + "2026-08-24\n"
    try:
        parse_eco_price_text(bad, expected_currency="CAD")
    except EcoPriceImportError as exc:
        assert exc.category == "effective_date_mismatch"
    else:
        raise AssertionError("mixed effective dates must fail closed")


def test_import_persists_eco_evidence_and_exact_file_replay_is_idempotent(monkeypatch) -> None:
    db = _session()
    monkeypatch.setattr(
        eco_price_report,
        "parse_eco_price_pdf",
        lambda content, *, filename: _document(_usd_row("6948"), _usd_row("6999")),
    )

    first = import_eco_price_pdf(
        db,
        "org-1",
        content=b"same-eco-file",
        source_filename="USD_Pricing_u873_2026-08-24.pdf",
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
        source_message_id="message-1",
        source_attachment_id="attachment-1",
    )
    second = import_eco_price_pdf(
        db,
        "org-1",
        content=b"same-eco-file",
        source_filename="USD_Pricing_u873_2026-08-24.pdf",
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
    )

    assert first["status"] == "import_success"
    assert first["records_inserted"] == 2
    assert second["status"] == "idempotent_replay"
    assert second["replayed"] is True
    assert db.query(FuelPriceImportRun).filter_by(organization_id="org-1", supplier="eco").count() == 1
    rows = db.query(FuelPriceEvidence).filter_by(organization_id="org-1", supplier="eco").all()
    assert len(rows) == 2
    assert rows[0].brand == "TA / Petro"
    assert rows[0].location_name == "TA EXPRESS - GRAND FORKS"
    assert rows[0].contracted_price == "5.0459"
    assert rows[0].cost is None
    assert rows[0].freight is None


def test_same_eco_file_hash_is_tenant_scoped(monkeypatch) -> None:
    db = _session()
    monkeypatch.setattr(eco_price_report, "parse_eco_price_pdf", lambda content, *, filename: _document())

    first = import_eco_price_pdf(
        db,
        "org-1",
        content=b"shared-bytes",
        source_filename="USD_Pricing_u873_2026-08-24.pdf",
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
    )
    second = import_eco_price_pdf(
        db,
        "org-2",
        content=b"shared-bytes",
        source_filename="USD_Pricing_u873_2026-08-24.pdf",
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
    )

    assert first["status"] == "import_success"
    assert second["status"] == "import_success"
    assert db.query(FuelPriceImportRun).filter_by(supplier="eco").count() == 2


def test_company_identity_mismatch_fails_without_evidence(monkeypatch) -> None:
    db = _session()
    monkeypatch.setattr(eco_price_report, "parse_eco_price_pdf", lambda content, *, filename: _document())

    result = import_eco_price_pdf(
        db,
        "org-1",
        content=b"wrong-company-file",
        source_filename="USD_Pricing_u873_2026-08-24.pdf",
        expected_company_name="OTHER CARRIER LTD",
    )

    assert result["status"] == "import_failed"
    assert result["error_category"] == "company_identity_mismatch"
    assert db.query(FuelPriceEvidence).filter_by(organization_id="org-1", supplier="eco").count() == 0
