from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.database import Base
from app.models.fuel_invoice import FuelInvoiceImportRun, FuelInvoiceLineEvidence
from app.organizations.models import Organization
from app.services import bvd_invoice, eco_invoice
from app.services.fuel_invoice import (
    FuelInvoiceDocument,
    FuelInvoiceImportError,
    FuelInvoiceLine,
    import_fuel_invoice_pdf,
    normalize_unit,
)


BVD_LAYOUT = """
Invoice                              Client info
Number  Invoice Date  Start Date  End Date  Due Date  MOR LOGISTICS MANITOBA LIMITED
988495  2026-08-24  2026-08-17  2026-08-23  2026-08-25  MB, Canada
Fuel Card Transactions
Transactions for card  2428274
Auth Code  Driver Name  Unit #  Date  Site #  Site Name  Site City  Prov/ST  Prod  QTY  Retail  Billed  Pre Tax AMT  HST  GST  PST  QST  Disc Rate  Disc AMT  Final AMT  CUR
A229544912-TA  M2220  2026-08-17 16:22:52  55012  BVD WINNIPEG  Winnipeg  MB  TA  607.40  2.1590  1.9660  1,137.30  0.00  56.86  0.00  0.00  0.1930  117.22  1,194.16  CN
A229554572-TF  M2220  2026-08-17 16:26:27  55012  BVD WINNIPEG  Winnipeg  MB  TF  114.00  2.1590  1.9660  213.45  0.00  10.67  0.00  0.00  0.1930  22.00  224.12  CN
A229544956-DF  M2220  2026-08-17 16:22:57  55012  BVD WINNIPEG  Winnipeg  MB  DF  33.70  1.5390  1.5390  46.31  0.00  2.32  3.24  0.00  0.0000  0.00  51.87  CN
"""

ECO_USD_LAYOUT = """
From:  To:  Start Date: 2026-08-23
End Date: 2026-08-29
12270145 Canada Limited  Mor Logistics Manitoba Limited  Invoice #: U9165021
A3, 25 Newkirk Crt,  7 Lake Bend Rd, Winnipeg MB R3Y 0M6  Currency: USD
Transactions for Unit: 2201
***97895  u873 D1  2026-08-24  TA EXPRESS GRAND FORKS  ULSD  5.6590  0.6130  111.5  111.5  0.00  562.88
2201  03:01  GRAND FORKS  ND  0.00  5.0460  68.38  562.88  562.88  0.00  USD
***40547  SINGH  2026-08-24  MONEYCODE - SINGH  MC  95.0000  0.0000  1.0  1.0  0.00  95.00
101  21:03  UNKNOWN  ND  0.00  95.0000  0.00  95.00  95.00  0.00  USD
"""

ECO_CAD_LAYOUT = """
From:  To:  Start Date: 2026-08-23
End Date: 2026-08-29
12270145 Canada Limited  Mor Logistics Manitoba Limited  Invoice #: C9193095
A3, 25 Newkirk Crt,  7 Lake Bend Rd, Winnipeg MB R3Y 0M6  Currency: CAD
Transactions for Unit: 2221
***07893  u873 D1  2026-08-27  ESSO MISSISSAUGA PEARSON  ULSR  1.8520  27.2  27.2  0.00  56.94
2221  15:39  MISSISSAUGA  ON  6.55  2.0928  50.39  56.94  0.00  CAD
***07893  u873 D1  2026-08-27  ESSO MISSISSAUGA PEARSON  DEFD  1.3665  9.7  9.7  0.00  15.03
2221  15:43  MISSISSAUGA  ON  1.73  1.5441  13.30  15.03  0.00  CAD
"""


class _Page:
    def __init__(self, text: str):
        self.text = text

    def extract_text(self, extraction_mode=None):
        assert extraction_mode == "layout"
        return self.text


class _Reader:
    def __init__(self, text: str):
        self.pages = [_Page(text)]


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add(Organization(id="org-1", slug="mor", display_name="MOR Logistics", legal_name="MOR LOGISTICS MANITOBA LIMITED"))
    db.add(Organization(id="org-2", slug="other", display_name="Other", legal_name="OTHER CARRIER LTD"))
    db.commit()
    return db


def test_bvd_parser_preserves_billed_price_and_known_categories(monkeypatch) -> None:
    monkeypatch.setattr(bvd_invoice, "PdfReader", lambda _: _Reader(BVD_LAYOUT))
    document = bvd_invoice.parse_bvd_invoice_pdf(b"provider", "BVD_invoice_988495.pdf")

    assert document.invoice_number == "988495"
    assert document.currency == "CAD"
    assert document.company_name == "MOR LOGISTICS MANITOBA LIMITED"
    assert document.period_start == date(2026, 8, 17)
    assert document.period_end == date(2026, 8, 23)
    assert [line.category for line in document.lines] == ["TRUCK_FUEL", "REEFER_FUEL", "DEF"]
    assert document.lines[0].quantity == "607.40"
    assert document.lines[0].retail_price == "2.1590"
    assert document.lines[0].billed_price == "1.9660"
    assert document.lines[0].discount_per_unit == "0.1930"
    assert document.lines[0].card_number == "2428274"


def test_bvd_express_only_invoice_is_not_misclassified_as_fuel(monkeypatch) -> None:
    monkeypatch.setattr(bvd_invoice, "PdfReader", lambda _: _Reader("Invoice\nExpress Codes\nGrand Totals"))
    with pytest.raises(FuelInvoiceImportError) as exc_info:
        bvd_invoice.parse_bvd_invoice_pdf(b"provider", "BVD_invoice_988488.pdf")
    assert exc_info.value.category == "non_fuel_invoice"


def test_eco_usd_parser_uses_billed_price_and_keeps_money_code_separate(monkeypatch) -> None:
    monkeypatch.setattr(eco_invoice, "PdfReader", lambda _: _Reader(ECO_USD_LAYOUT))
    document = eco_invoice.parse_eco_invoice_pdf(
        b"provider",
        "Mor Logistics Manitoba Limited_08-23_08-29_USD.pdf",
    )

    assert document.invoice_number == "U9165021"
    assert document.currency == "USD"
    assert len(document.lines) == 2
    fuel, money_code = document.lines
    assert fuel.category == "TRUCK_FUEL"
    assert fuel.quantity == "111.5"
    assert fuel.retail_price == "5.6590"
    assert fuel.billed_price == "5.0460"
    assert fuel.discount_per_unit == "0.6130"
    assert money_code.category == "MONEY_CODE"
    assert money_code.billed_price == "95.0000"


def test_eco_cad_parser_preserves_unit_price_and_billed_price(monkeypatch) -> None:
    monkeypatch.setattr(eco_invoice, "PdfReader", lambda _: _Reader(ECO_CAD_LAYOUT))
    document = eco_invoice.parse_eco_invoice_pdf(
        b"provider",
        "Mor Logistics Manitoba Limited_08-23_08-29_CAD.pdf",
    )

    assert document.currency == "CAD"
    reefer, def_line = document.lines
    assert reefer.category == "REEFER_FUEL"
    assert reefer.unit_price == "1.8520"
    assert reefer.billed_price == "2.0928"
    assert reefer.sales_tax == "6.55"
    assert def_line.category == "DEF"
    assert def_line.unit_price == "1.3665"
    assert def_line.billed_price == "1.5441"


def test_unit_normalization_applies_only_known_optional_m_rule() -> None:
    assert normalize_unit("2201") == "M2201"
    assert normalize_unit("M2201") == "M2201"
    assert normalize_unit("MR009") == "MR009"
    assert normalize_unit(None) is None


def test_durable_invoice_import_is_tenant_scoped_and_idempotent() -> None:
    db = _session()
    document = FuelInvoiceDocument(
        supplier="eco",
        invoice_number="U9165021",
        currency="USD",
        company_name="MOR LOGISTICS MANITOBA LIMITED",
        invoice_date=None,
        period_start=date(2026, 8, 23),
        period_end=date(2026, 8, 29),
        due_date=None,
        lines=(
            FuelInvoiceLine(
                provider_transaction_id=None,
                card_number="***97895",
                driver_name="u873 D1",
                unit_raw="2201",
                transaction_at=datetime(2026, 8, 24, 3, 1),
                supplier_site_id=None,
                site_name="TA EXPRESS GRAND FORKS",
                site_city="GRAND FORKS",
                region_code="ND",
                product_code="ULSD",
                category="TRUCK_FUEL",
                quantity="111.5",
                retail_price="5.6590",
                billed_price="5.0460",
            ),
        ),
    )
    parser = lambda content, filename: document

    first = import_fuel_invoice_pdf(
        db,
        "org-1",
        supplier="eco",
        content=b"same-invoice",
        source_filename="Mor Logistics Manitoba Limited_08-23_08-29_USD.pdf",
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
        parser=parser,
        source_message_id="m1",
        source_attachment_id="a1",
    )
    replay = import_fuel_invoice_pdf(
        db,
        "org-1",
        supplier="eco",
        content=b"same-invoice",
        source_filename="Mor Logistics Manitoba Limited_08-23_08-29_USD.pdf",
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
        parser=parser,
    )
    other_tenant = import_fuel_invoice_pdf(
        db,
        "org-2",
        supplier="eco",
        content=b"same-invoice",
        source_filename="Mor Logistics Manitoba Limited_08-23_08-29_USD.pdf",
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
        parser=parser,
    )

    assert first["status"] == "import_success"
    assert replay["status"] == "idempotent_replay"
    assert replay["replayed"] is True
    assert other_tenant["status"] == "import_success"
    assert db.query(FuelInvoiceImportRun).filter_by(supplier="eco").count() == 2
    row = db.query(FuelInvoiceLineEvidence).filter_by(organization_id="org-1").one()
    assert row.unit_raw == "2201"
    assert row.unit_normalized == "M2201"
    assert row.billed_price == "5.0460"


def test_company_mismatch_fails_without_invoice_lines() -> None:
    db = _session()
    document = FuelInvoiceDocument(
        supplier="bvd",
        invoice_number="988495",
        currency="CAD",
        company_name="MOR LOGISTICS MANITOBA LIMITED",
        invoice_date=date(2026, 8, 24),
        period_start=date(2026, 8, 17),
        period_end=date(2026, 8, 23),
        due_date=date(2026, 8, 25),
        lines=(
            FuelInvoiceLine(
                provider_transaction_id="A1-TA",
                card_number="1",
                driver_name=None,
                unit_raw="M2201",
                transaction_at=datetime(2026, 8, 17, 10, 0),
                supplier_site_id="55012",
                site_name="BVD WINNIPEG",
                site_city="Winnipeg",
                region_code="MB",
                product_code="TA",
                category="TRUCK_FUEL",
                quantity="100.00",
                billed_price="1.9660",
            ),
        ),
    )
    result = import_fuel_invoice_pdf(
        db,
        "org-1",
        supplier="bvd",
        content=b"wrong-company",
        source_filename="BVD_invoice_988495.pdf",
        expected_company_name="OTHER CARRIER LTD",
        parser=lambda content, filename: document,
    )

    assert result["status"] == "import_failed"
    assert result["error_category"] == "company_identity_mismatch"
    assert db.query(FuelInvoiceLineEvidence).filter_by(organization_id="org-1").count() == 0
