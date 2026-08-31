from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.database import Base
from app.models.fuel import FuelPriceEvidence, FuelPriceImportRun
from app.organizations.models import Organization
from app.services import bvd_pcn
from app.services.bvd_pcn import (
    BvdPcnDocument,
    BvdPcnImportError,
    BvdPcnPriceRow,
    import_bvd_pcn_pdf,
    parse_bvd_pcn_layout_text,
)


HEADER = (
    "Site      Name                             City                    Prov    Cost      Freight    Base        "
    "FET     PFT        PCT     Local    Fuel       SalesTax     InTax       QST        Retail    Your       Savings"
)
SECOND_HEADER = (
    "                                                                                                Price                                           "
    "Price                   Price                  Price     Price"
)
ROW_ONE = (
    "90001     BVD TEST NORTH                   TEST NORTH              MB      1.724     0.0084     1.7324      "
    "0       0.125      0       0        1.8574     0.0929       1.9503      0          2.169     1.9503     0.2187"
)
ROW_TWO = (
    "90002     BVD TEST LONG ROAD               TEST CITY               ON      1.808     0.0077     1.8157      "
    "0       0.09       0       0        1.9057     0.2477       2.1534      0          2.359     2.1534     0.2056"
)
LAYOUT_TEXT = "\n".join(
    [
        "                           Effective Date                                                                                                   Company Name:",
        "                    2026-08-31 to 2026-09-01                                                                                     MOR LOGISTICS MANITOBA LIMITED",
        "",
        HEADER,
        SECOND_HEADER,
        "",
        ROW_ONE,
        "",
        ROW_TWO,
        "                                           EXTENSION",
        "RETAIL PRICES ARE SUBJECT TO CHANGE AT ANY TIME",
    ]
)

USD_HEADER = (
    "Site      Name                City                               State     Prod      Cost        Federal Tax      "
    "State Tax     Sales Tax      Freight     Other        Total Cost     Retail Price     Your Price      Savings"
)
USD_ROW_ONE = (
    "1277      LOVES #368          Clanton                            AL        ULSD      4.4456      0.2483           "
    "0.3175        0              0.1187      0.02         5.15           5.779            5.15            0.629"
)
USD_ROW_TWO = (
    "8313      LOVES #877          Cullman                            AL        ULSD      4.4229      0.2483           "
    "0.3175        0              0.065       0.01         5.064          5.749            5.064           0.685"
)
USD_LAYOUT_TEXT = "\n".join(
    [
        "                           Effective Date                                                                                                     Company Name:",
        "                            2026-08-31                                                                                              MOR LOGISTICS MANITOBA LIMITED",
        "",
        USD_HEADER,
        "",
        USD_ROW_ONE,
        "",
        USD_ROW_TWO,
        "RETAIL PRICES ARE SUBJECT TO CHANGE AT ANY TIME",
    ]
)


def _row(site: str = "90001") -> BvdPcnPriceRow:
    return BvdPcnPriceRow(
        supplier_site_id=site,
        site_name="BVD TEST NORTH",
        city="TEST NORTH",
        region_code="MB",
        cost="1.724",
        freight="0.0084",
        base_price="1.7324",
        fet="0",
        pft="0.125",
        pct="0",
        local_tax="0",
        fuel_price="1.8574",
        sales_tax="0.0929",
        in_tax_price="1.9503",
        qst="0",
        retail_price="2.169",
        contracted_price="1.9503",
        savings="0.2187",
    )


def _usd_row(site: str = "1277") -> BvdPcnPriceRow:
    return BvdPcnPriceRow(
        supplier_site_id=site,
        site_name="LOVES #368",
        city="Clanton",
        region_code="AL",
        product_code="ULSD",
        cost="4.4456",
        federal_tax="0.2483",
        state_tax="0.3175",
        sales_tax="0",
        freight="0.1187",
        other_cost="0.02",
        total_cost="5.15",
        retail_price="5.779",
        contracted_price="5.15",
        savings="0.629",
    )


def _document(*rows: BvdPcnPriceRow) -> BvdPcnDocument:
    return BvdPcnDocument(
        currency="CAD",
        effective_start=date(2026, 8, 31),
        effective_end=date(2026, 9, 1),
        company_name="MOR LOGISTICS MANITOBA LIMITED",
        rows=tuple(rows or (_row(),)),
    )


def _usd_document(*rows: BvdPcnPriceRow) -> BvdPcnDocument:
    return BvdPcnDocument(
        currency="USD",
        effective_start=date(2026, 8, 31),
        effective_end=date(2026, 8, 31),
        company_name="MOR LOGISTICS MANITOBA LIMITED",
        rows=tuple(rows or (_usd_row(),)),
    )


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add(Organization(id="org-1", slug="mor", display_name="MOR Logistics", legal_name="MOR LOGISTICS MANITOBA LIMITED"))
    db.add(Organization(id="org-2", slug="other", display_name="Other Carrier", legal_name="OTHER CARRIER LTD"))
    db.commit()
    return db


def test_layout_parser_preserves_provider_values_and_wrapped_city() -> None:
    document = parse_bvd_pcn_layout_text(LAYOUT_TEXT, currency="CAD")

    assert document.currency == "CAD"
    assert document.effective_start == date(2026, 8, 31)
    assert document.effective_end == date(2026, 9, 1)
    assert document.company_name == "MOR LOGISTICS MANITOBA LIMITED"
    assert len(document.rows) == 2
    assert document.rows[0].contracted_price == "1.9503"
    assert document.rows[0].savings == "0.2187"
    assert document.rows[1].city == "TEST CITY EXTENSION"
    assert document.rows[1].sales_tax == "0.2477"
    assert document.rows[0].product_code is None
    assert document.rows[0].federal_tax is None


def test_usd_layout_parser_preserves_real_provider_contract() -> None:
    document = parse_bvd_pcn_layout_text(USD_LAYOUT_TEXT, currency="USD")

    assert document.currency == "USD"
    assert document.effective_start == date(2026, 8, 31)
    assert document.effective_end == date(2026, 8, 31)
    assert document.company_name == "MOR LOGISTICS MANITOBA LIMITED"
    assert len(document.rows) == 2
    first = document.rows[0]
    assert first.supplier_site_id == "1277"
    assert first.product_code == "ULSD"
    assert first.federal_tax == "0.2483"
    assert first.state_tax == "0.3175"
    assert first.sales_tax == "0"
    assert first.freight == "0.1187"
    assert first.other_cost == "0.02"
    assert first.total_cost == "5.15"
    assert first.retail_price == "5.779"
    assert first.contracted_price == "5.15"
    assert first.savings == "0.629"
    assert first.base_price is None
    assert first.qst is None


def test_layout_parser_fails_closed_when_provider_header_drifts() -> None:
    bad = LAYOUT_TEXT.replace("SalesTax", "TaxTotal", 1)
    try:
        parse_bvd_pcn_layout_text(bad, currency="CAD")
    except BvdPcnImportError as exc:
        assert exc.category == "source_contract_error"
    else:
        raise AssertionError("provider header drift must fail closed")


def test_usd_layout_parser_fails_closed_when_provider_header_drifts() -> None:
    bad = USD_LAYOUT_TEXT.replace("Total Cost", "Gross Cost", 1)
    try:
        parse_bvd_pcn_layout_text(bad, currency="USD")
    except BvdPcnImportError as exc:
        assert exc.category == "source_contract_error"
    else:
        raise AssertionError("USD provider header drift must fail closed")


def test_import_persists_immutable_evidence_and_deduplicates_exact_file_replay(monkeypatch) -> None:
    db = _session()
    monkeypatch.setattr(bvd_pcn, "parse_bvd_pcn_pdf", lambda content, *, filename: _document(_row("90001"), _row("90002")))

    first = import_bvd_pcn_pdf(
        db,
        "org-1",
        content=b"certified-bvd-pcn",
        source_filename="pcn-cad-test.pdf",
        expected_company_name="MOR Logistics Manitoba Limited",
        source_message_id="message-1",
        source_attachment_id="attachment-1",
    )
    second = import_bvd_pcn_pdf(
        db,
        "org-1",
        content=b"certified-bvd-pcn",
        source_filename="pcn-cad-test.pdf",
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
        source_message_id="message-1-replay",
        source_attachment_id="attachment-1-replay",
    )

    assert first["status"] == "import_success"
    assert first["records_inserted"] == 2
    assert second["status"] == "idempotent_replay"
    assert second["replayed"] is True
    assert db.query(FuelPriceImportRun).filter_by(organization_id="org-1").count() == 1
    assert db.query(FuelPriceEvidence).filter_by(organization_id="org-1").count() == 2

    evidence = db.query(FuelPriceEvidence).filter_by(organization_id="org-1", supplier_site_id="90001").one()
    assert evidence.contracted_price == "1.9503"
    assert evidence.retail_price == "2.169"
    assert evidence.source_sha256


def test_import_persists_usd_source_specific_components_without_cad_relabeling(monkeypatch) -> None:
    db = _session()
    monkeypatch.setattr(bvd_pcn, "parse_bvd_pcn_pdf", lambda content, *, filename: _usd_document(_usd_row()))

    result = import_bvd_pcn_pdf(
        db,
        "org-1",
        content=b"certified-bvd-usd-pcn",
        source_filename="pcn-usd-test.pdf",
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
        source_message_id="usd-message-1",
        source_attachment_id="usd-attachment-1",
    )

    assert result["status"] == "import_success"
    assert result["currency"] == "USD"
    assert result["effective_start"] == "2026-08-31"
    assert result["effective_end"] == "2026-08-31"
    evidence = db.query(FuelPriceEvidence).filter_by(organization_id="org-1", supplier_site_id="1277").one()
    assert evidence.product_code == "ULSD"
    assert evidence.federal_tax == "0.2483"
    assert evidence.state_tax == "0.3175"
    assert evidence.other_cost == "0.02"
    assert evidence.total_cost == "5.15"
    assert evidence.contracted_price == "5.15"
    assert evidence.base_price is None
    assert evidence.fet is None
    assert evidence.pft is None
    assert evidence.pct is None
    assert evidence.local_tax is None
    assert evidence.fuel_price is None
    assert evidence.in_tax_price is None
    assert evidence.qst is None


def test_same_provider_file_hash_is_isolated_by_tenant(monkeypatch) -> None:
    db = _session()
    monkeypatch.setattr(bvd_pcn, "parse_bvd_pcn_pdf", lambda content, *, filename: _document(_row()))

    one = import_bvd_pcn_pdf(
        db,
        "org-1",
        content=b"same-provider-file",
        source_filename="pcn-cad-test.pdf",
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
    )
    monkeypatch.setattr(
        bvd_pcn,
        "parse_bvd_pcn_pdf",
        lambda content, *, filename: BvdPcnDocument(
            currency="CAD",
            effective_start=date(2026, 8, 31),
            effective_end=date(2026, 9, 1),
            company_name="OTHER CARRIER LTD",
            rows=(_row(),),
        ),
    )
    two = import_bvd_pcn_pdf(
        db,
        "org-2",
        content=b"same-provider-file",
        source_filename="pcn-cad-test.pdf",
        expected_company_name="OTHER CARRIER LTD",
    )

    assert one["status"] == "import_success"
    assert two["status"] == "import_success"
    assert db.query(FuelPriceImportRun).count() == 2
    assert db.query(FuelPriceEvidence).count() == 2


def test_company_identity_mismatch_records_sanitized_failure_without_evidence(monkeypatch) -> None:
    db = _session()
    monkeypatch.setattr(bvd_pcn, "parse_bvd_pcn_pdf", lambda content, *, filename: _document(_row()))

    result = import_bvd_pcn_pdf(
        db,
        "org-1",
        content=b"wrong-company-file",
        source_filename="pcn-cad-test.pdf",
        expected_company_name="OTHER CARRIER LTD",
    )

    assert result["status"] == "import_failed"
    assert result["error_category"] == "company_identity_mismatch"
    assert db.query(FuelPriceEvidence).count() == 0
    run = db.query(FuelPriceImportRun).one()
    assert run.status == "failed"
    assert run.error_category == "company_identity_mismatch"
