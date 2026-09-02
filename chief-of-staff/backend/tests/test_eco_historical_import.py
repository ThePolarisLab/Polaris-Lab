from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.fuel import eco_historical_import as module
from app.fuel.eco_outlook_import import EcoPriceOutlookImportError, ECO_PRICE_SENDER
from app.services.eco_price_report import EcoPriceImportError
from app.security.models import AuthenticatedPrincipal, Permission
from app.security.dependencies import get_principal
from app.api import fuel


DAY = datetime.now(timezone.utc).date() - timedelta(days=10)
COMPANY = "Mor Logistics Manitoba Limited"


class Source:
    def __init__(self):
        self.message = dict(id="canonical", parentFolderId="inbox",
            subject=f"USD Pricing for {COMPANY} — {DAY}",
            sender={"emailAddress": {"address": ECO_PRICE_SENDER}},
            hasAttachments=True, receivedDateTime=f"{DAY}T13:00:00Z")
        self.attachments = {"value": [dict(id="attachment", name=f"USD_Pricing_u873_{DAY}.pdf",
            contentType="application/pdf", isInline=False)]}
        self.reads = []

    def list_folders(self):
        return {"value": [{"id": "inbox", "displayName": "Inbox"}]}

    def get_message(self, message_id):
        self.reads.append(message_id)
        return self.message

    def list_attachments(self, message_id):
        assert message_id == "canonical"
        return self.attachments

    def get_attachment_content(self, message_id, attachment_id):
        assert (message_id, attachment_id) == ("canonical", "attachment")
        return b"pdf"


@pytest.fixture
def setup(monkeypatch):
    source = Source()
    calls = []
    document = SimpleNamespace(currency="USD", effective_date=DAY, company_name=COMPANY)
    monkeypatch.setattr(module, "parse_eco_price_pdf", lambda *a, **kw: document)
    def persist(db, org, **kwargs):
        calls.append((org, kwargs))
        return {"status": "import_success", "records_inserted": 350}
    monkeypatch.setattr(module, "import_eco_price_pdf", persist)
    return source, calls, document


def run(source, **kwargs):
    return module.import_historical_eco_price_outlook(object(), "org-1",
        connector=source, expected_company_name=COMPANY, currency="USD",
        effective_date=kwargs.get("effective_date", DAY), message_id=kwargs.get("message_id", "selected"))


def test_explicit_source_and_provenance(setup):
    source, calls, _ = setup
    assert run(source)["status"] == "import_success"
    assert source.reads == ["selected"]
    assert calls[0][0] == "org-1"
    assert calls[0][1]["source_message_id"] == "canonical"
    assert calls[0][1]["source_attachment_id"] == "attachment"
    assert calls[0][1]["source_received_at"] is not None


@pytest.mark.parametrize("mutation", ["sender", "folder", "subject_date", "currency", "company",
    "missing_received", "attachment_date", "multiple", "pagination", "pdf_date", "pdf_currency", "pdf_company"])
def test_mismatch_never_persists(setup, mutation):
    source, calls, document = setup
    if mutation == "sender": source.message["sender"]["emailAddress"]["address"] = "spoof@example.com"
    if mutation == "folder": source.message["parentFolderId"] = "other"
    if mutation == "subject_date": source.message["subject"] = source.message["subject"].replace(str(DAY), str(DAY-timedelta(days=1)))
    if mutation == "currency": source.message["subject"] = source.message["subject"].replace("USD", "CAD")
    if mutation == "company": source.message["subject"] = source.message["subject"].replace(COMPANY, "Other")
    if mutation == "missing_received": source.message["receivedDateTime"] = None
    if mutation == "attachment_date": source.attachments["value"][0]["name"] = "USD_Pricing_u873_2000-01-01.pdf"
    if mutation == "multiple": source.attachments["value"] *= 2
    if mutation == "pagination": source.attachments["@odata.nextLink"] = "next"
    if mutation == "pdf_date": document.effective_date = DAY-timedelta(days=1)
    if mutation == "pdf_currency": document.currency = "CAD"
    if mutation == "pdf_company": document.company_name = "Other"
    assert run(source)["status"] == "import_failed"
    assert calls == []


@pytest.mark.parametrize("days", [-1, 91])
def test_date_bounds_before_mailbox_reads(setup, days):
    source, calls, _ = setup
    with pytest.raises(EcoPriceOutlookImportError):
        run(source, effective_date=datetime.now(timezone.utc).date()-timedelta(days=days))
    assert not calls and not source.reads


def test_pdf_failure_sanitized(setup, monkeypatch):
    source, calls, _ = setup
    def invalid(*a, **kw): raise EcoPriceImportError("source_contract_error")
    monkeypatch.setattr(module, "parse_eco_price_pdf", invalid)
    assert run(source)["error_category"] == "source_contract_error"
    assert not calls


def test_replay_result_preserved(setup, monkeypatch):
    monkeypatch.setattr(module, "import_eco_price_pdf", lambda *a, **kw: {
        "status": "idempotent_replay", "replayed": True, "records_inserted": 350})
    assert run(setup[0])["replayed"] is True


def test_api_requires_write_and_uses_principal_tenant(monkeypatch):
    app = FastAPI()
    app.include_router(fuel.router)
    app.dependency_overrides[fuel._db] = lambda: object()
    calls = []
    monkeypatch.setattr(fuel, "OutlookCredentialStore", lambda org: calls.append(org))
    monkeypatch.setattr(fuel, "OutlookConnector", lambda **kw: object())
    monkeypatch.setattr(fuel, "_organization_company_name", lambda db, org: COMPANY)
    monkeypatch.setattr(fuel, "import_historical_eco_price_outlook", lambda db, org, **kw: {"org": org})
    body = dict(message_id="selected", currency="USD", effective_date=str(DAY))
    with TestClient(app) as client:
        url = "/api/v1/fuel/eco/prices/import-outlook-selected"
        assert client.post(url, json=body).status_code == 401
        principal = AuthenticatedPrincipal("id", "org-1", "m", "viewer", frozenset({Permission.ORGANIZATION_READ}), "test", "id")
        app.dependency_overrides[get_principal] = lambda: principal
        assert client.post(url, json=body).status_code == 403
        assert not calls
        principal = replace(principal, permissions=frozenset({Permission.ORGANIZATION_WRITE}))
        assert client.post(url, json=body).json() == {"org": "org-1"}
        assert calls == ["org-1"]
        assert client.post(url, json={**body, "effective_date": "invalid"}).status_code == 422
        assert client.post(url, json={**body, "currency": "EUR"}).status_code == 422


def test_connector_reads_encoded_mailbox_message(monkeypatch):
    from app.connectors.outlook import OutlookConnector
    connector = object.__new__(OutlookConnector)
    calls = []
    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"id": "canonical"}
    monkeypatch.setattr(connector, "_request_json", request)
    assert connector.get_message("a/b?c")["id"] == "canonical"
    assert calls[0][0:2] == ("GET", "/me/messages/a%2Fb%3Fc")
    assert "parentFolderId" in calls[0][2]["params"]["$select"]


def test_real_persistence_replay_and_tenant_isolation(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.database.database import Base
    from app.organizations.models import Organization
    from app.models.fuel import FuelPriceEvidence, FuelPriceImportRun
    from app.services import eco_price_report as service
    document = service.EcoPriceDocument(currency="USD", effective_date=DAY, company_name=COMPANY,
        rows=(service.EcoPriceRow(brand="TA", supplier_site_id="123", location_name="TA STATION",
            region_code="ND", product_code="ULSD", contracted_price="5"),))
    monkeypatch.setattr(module, "parse_eco_price_pdf", lambda *a, **kw: document)
    monkeypatch.setattr(service, "parse_eco_price_pdf", lambda *a, **kw: document)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Organization(id=o, slug=o, display_name=o, legal_name=COMPANY) for o in ("org-1", "org-2")])
        db.commit()
        def execute(org):
            return module.import_historical_eco_price_outlook(db, org, connector=Source(),
                expected_company_name=COMPANY, currency="USD", effective_date=DAY, message_id="selected")
        assert execute("org-1")["status"] == "import_success"
        assert execute("org-1")["status"] == "idempotent_replay"
        assert db.query(FuelPriceEvidence).count() == 1
        assert execute("org-2")["status"] == "import_success"
        assert db.query(FuelPriceEvidence).count() == 2
        saved = db.query(FuelPriceImportRun).filter_by(organization_id="org-1").one()
        assert saved.source_message_id == "canonical" and saved.source_attachment_id == "attachment"
        assert saved.effective_start == DAY and saved.records_inserted == 1
    engine.dispose()
