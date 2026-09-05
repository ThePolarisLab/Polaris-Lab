from dataclasses import replace
from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.fuel import _db, router
from app.database.database import Base
from app.fuel.discrepancy_review import (
    DiscrepancyReviewError,
    approve_discrepancy,
    approve_precision_discrepancies,
    reopen_discrepancy,
)
from app.fuel.price_reconciliation import preview_invoice_prices
from app.models.fuel import FuelPriceEvidence, FuelPriceImportRun
from app.models.fuel_invoice import FuelInvoiceImportRun, FuelInvoiceLineEvidence
from app.models.fuel_review import FuelDiscrepancyReviewEvent
from app.organizations.models import Organization
from app.security.dependencies import get_principal
from app.security.models import AuthenticatedPrincipal, Permission


DAY = date(2026, 8, 26)
NOW = datetime(2026, 9, 5, tzinfo=timezone.utc)
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


def make_invoice(db, billed_prices):
    run = FuelInvoiceImportRun(
        organization_id="org-1",
        supplier="eco",
        source_sha256="a" * 64,
        source_filename="invoice.pdf",
        invoice_number="U1",
        currency="USD",
        company_name=COMPANY,
        status="completed",
        completed_at=NOW,
        records_read=len(billed_prices),
        records_inserted=len(billed_prices),
    )
    db.add(run)
    db.flush()
    lines = []
    for number, billed in enumerate(billed_prices, 1):
        line = FuelInvoiceLineEvidence(
            organization_id="org-1",
            import_run_id=run.id,
            supplier="eco",
            source_sha256="a" * 64,
            invoice_number="U1",
            currency="USD",
            line_number=number,
            transaction_at=datetime(2026, 8, 26, 10),
            site_name="TA MORIARTY",
            site_city="MORIARTY",
            region_code="NM",
            product_code="ULSD",
            category="TRUCK_FUEL",
            quantity="100",
            billed_price=billed,
        )
        db.add(line)
        lines.append(line)
    db.commit()
    return run, lines


def make_quote(db, price="5.0000"):
    run = FuelPriceImportRun(
        organization_id="org-1",
        supplier="eco",
        currency="USD",
        company_name=COMPANY,
        source_filename="quote.pdf",
        source_sha256="b" * 64,
        status="completed",
        completed_at=NOW,
        records_read=1,
        records_inserted=1,
        effective_start=DAY,
        effective_end=DAY,
    )
    db.add(run)
    db.flush()
    db.add(FuelPriceEvidence(
        organization_id="org-1",
        import_run_id=run.id,
        supplier="eco",
        currency="USD",
        company_name=COMPANY,
        source_sha256=run.source_sha256,
        effective_start=DAY,
        effective_end=DAY,
        supplier_site_id="test-ta-moriarty",
        location_name="TA MORIARTY",
        region_code="NM",
        product_code="ULSD",
        contracted_price=price,
    ))
    db.commit()


def test_precision_approval_is_separate_and_idempotent(db):
    run, lines = make_invoice(db, ["5.0005"])
    make_quote(db)

    before = preview_invoice_prices(db, "org-1", run.id)["lines"][0]
    assert before["status"] == "price_difference"
    assert before["review"]["disposition"] == "not_reviewed"

    approved = approve_discrepancy(
        db, "org-1", run.id, lines[0].id,
        reviewer_identity_id="owner-1", reviewer_role="owner",
    )
    assert approved["disposition"] == "approved_no_action"
    assert approved["technical_status"] == "price_difference"
    assert approved["technical_status_unchanged"] is True
    assert approved["accounting_side_effects"] is False
    assert db.query(FuelDiscrepancyReviewEvent).count() == 1

    after = preview_invoice_prices(db, "org-1", run.id)["lines"][0]
    assert after["status"] == "price_difference"
    assert after["review"]["disposition"] == "approved_no_action"

    duplicate = approve_discrepancy(
        db, "org-1", run.id, lines[0].id,
        reviewer_identity_id="owner-1", reviewer_role="owner",
    )
    assert duplicate["already_approved"] is True
    assert db.query(FuelDiscrepancyReviewEvent).count() == 1


def test_material_approval_requires_reason_and_snapshots_exact_values(db):
    run, lines = make_invoice(db, ["5.1635"])
    make_quote(db)

    with pytest.raises(DiscrepancyReviewError, match="approval_reason_required"):
        approve_discrepancy(
            db, "org-1", run.id, lines[0].id,
            reviewer_identity_id="owner-1", reviewer_role="owner",
        )

    approved = approve_discrepancy(
        db, "org-1", run.id, lines[0].id,
        reviewer_identity_id="owner-1", reviewer_role="owner",
        reason="Supplier confirmed reefer surcharge is valid.",
    )
    event = db.get(FuelDiscrepancyReviewEvent, approved["review_event_id"])
    assert event.reason == "Supplier confirmed reefer surcharge is valid."
    assert event.invoice_billed_price == "5.1635"
    assert event.quote_price == "5.0000"
    assert event.rate_difference == "0.1635"
    assert event.analytical_impact == "16.3500"


def test_bulk_precision_approval_excludes_material_and_match_lines(db):
    run, lines = make_invoice(db, ["5.0005", "4.9995", "5.0010", "5.0000"])
    make_quote(db)

    result = approve_precision_discrepancies(
        db, "org-1", run.id,
        reviewer_identity_id="owner-1", reviewer_role="owner",
    )
    assert result["approved_count"] == 2
    assert set(result["approved_line_ids"]) == {lines[0].id, lines[1].id}
    assert result["precision_band"] == "0.0005"
    assert result["supplier_rounding_rule_inferred"] is False

    preview = preview_invoice_prices(db, "org-1", run.id)
    assert preview["lines"][0]["review"]["approved"] is True
    assert preview["lines"][1]["review"]["approved"] is True
    assert preview["lines"][2]["review"]["approved"] is False
    assert "review" not in preview["lines"][3]


def test_reopen_appends_history_without_deleting_approval(db):
    run, lines = make_invoice(db, ["5.0005"])
    make_quote(db)
    approve_discrepancy(
        db, "org-1", run.id, lines[0].id,
        reviewer_identity_id="owner-1", reviewer_role="owner",
    )

    reopened = reopen_discrepancy(
        db, "org-1", run.id, lines[0].id,
        reviewer_identity_id="owner-1", reviewer_role="owner",
        reason="Recheck supplier documentation.",
    )
    assert reopened["action"] == "reopened"
    assert reopened["disposition"] == "not_reviewed"
    events = db.query(FuelDiscrepancyReviewEvent).order_by(FuelDiscrepancyReviewEvent.id).all()
    assert [event.action for event in events] == ["approved_no_action", "reopened"]

    line = preview_invoice_prices(db, "org-1", run.id)["lines"][0]
    assert line["status"] == "price_difference"
    assert line["review"]["disposition"] == "not_reviewed"
    assert line["review"]["last_action"] == "reopened"


def test_approval_api_requires_write_permission_and_tenant_scope(db):
    run, lines = make_invoice(db, ["5.0005"])
    make_quote(db)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_db] = lambda: db
    url = f"/api/v1/fuel/invoices/{run.id}/price-reconciliation/{lines[0].id}/approve"

    with TestClient(app) as client:
        principal = AuthenticatedPrincipal("owner-1", "org-1", "m", "owner", frozenset(), "test", "owner-1")
        app.dependency_overrides[get_principal] = lambda: principal
        assert client.post(url, json={}).status_code == 403

        principal = replace(principal, permissions=frozenset({Permission.ORGANIZATION_WRITE}))
        assert client.post(url, json={}).status_code == 200

        principal = replace(principal, organization_id="org-2")
        assert client.post(url, json={}).status_code == 404
