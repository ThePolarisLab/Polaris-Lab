from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.api.fuel import router as fuel_router
from app.fuel import invoice_outlook_import as invoice_outlook
from app.services.fuel_invoice import FuelInvoiceImportError


class FakeOutlookConnector:
    def __init__(self, messages, attachments=None, content=None):
        self.messages = messages
        self.attachments = attachments or {}
        self.content = content or {}
        self.content_calls = []
        self.folder_calls = 0

    def list_folders(self):
        self.folder_calls += 1
        return {"value": [{"id": "inbox", "displayName": "Inbox"}]}

    def list_messages(self, folder_id, *, url=None, since_iso=None):
        assert folder_id == "inbox"
        assert url is None
        assert since_iso and since_iso.endswith("Z")
        return {"value": self.messages}

    def list_attachments(self, message_id):
        return {"value": self.attachments.get(message_id, [])}

    def get_attachment_content(self, message_id, attachment_id):
        self.content_calls.append((message_id, attachment_id))
        return self.content[(message_id, attachment_id)]


def _bvd_message(message_id, invoice, received, *, sender=invoice_outlook.BVD_INVOICE_SENDER):
    return {
        "id": message_id,
        "subject": f"BVD Invoice Number {invoice}",
        "receivedDateTime": received,
        "hasAttachments": True,
        "sender": {"emailAddress": {"address": sender}},
    }


def _bvd_attachment(attachment_id, invoice, *, content_type="application/pdf"):
    return {
        "id": attachment_id,
        "name": f"BVD_invoice_{invoice}.pdf",
        "contentType": content_type,
        "isInline": False,
    }


def _eco_message(message_id, currency, received, *, sender=invoice_outlook.ECO_INVOICE_SENDER):
    return {
        "id": message_id,
        "subject": f"Fuel Invoice; 08-23_08-29_{currency}",
        "receivedDateTime": received,
        "hasAttachments": True,
        "from": {"emailAddress": {"address": sender}},
    }


def _eco_attachment(attachment_id, currency, *, company="Mor Logistics Manitoba Limited"):
    return {
        "id": attachment_id,
        "name": f"{company}_08-23_08-29_{currency}.pdf",
        "contentType": "application/pdf",
        "isInline": False,
    }


def test_bvd_skips_newer_express_only_and_imports_newest_valid_fuel(monkeypatch):
    connector = FakeOutlookConnector(
        [
            _bvd_message("express", "988488", "2026-08-24T15:53:43Z"),
            _bvd_message("fuel", "988495", "2026-08-24T15:53:40Z"),
        ],
        attachments={
            "express": [_bvd_attachment("express-a", "988488")],
            "fuel": [_bvd_attachment("fuel-a", "988495")],
        },
        content={
            ("express", "express-a"): b"express-only",
            ("fuel", "fuel-a"): b"fuel-invoice",
        },
    )
    parsed = []
    captured = {}

    def fake_parse(content, filename):
        parsed.append((content, filename))
        if content == b"express-only":
            raise FuelInvoiceImportError("non_fuel_invoice")
        return object()

    def fake_import(db, organization_id, **kwargs):
        captured.update({"db": db, "organization_id": organization_id, **kwargs})
        return {"status": "import_success", "records_read": 12, "records_inserted": 12, "replayed": False}

    monkeypatch.setattr(invoice_outlook, "parse_bvd_invoice_pdf", fake_parse)
    monkeypatch.setattr(invoice_outlook, "import_bvd_invoice_pdf", fake_import)
    db = object()
    result = invoice_outlook.import_latest_bvd_invoice_outlook(
        db,
        "org-1",
        connector=connector,
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
    )

    assert result["status"] == "import_success"
    assert result["outlook_read_only"] is True
    assert result["supplier_api_called"] is False
    assert result["secrets_exposed"] is False
    assert connector.content_calls == [("express", "express-a"), ("fuel", "fuel-a")]
    assert parsed == [
        (b"express-only", "BVD_invoice_988488.pdf"),
        (b"fuel-invoice", "BVD_invoice_988495.pdf"),
    ]
    assert captured["db"] is db
    assert captured["organization_id"] == "org-1"
    assert captured["source_message_id"] == "fuel"
    assert captured["source_attachment_id"] == "fuel-a"
    assert captured["source_received_at"] == datetime(2026, 8, 24, 15, 53, 40, tzinfo=timezone.utc)


def test_bvd_wrong_sender_is_ignored(monkeypatch):
    connector = FakeOutlookConnector(
        [_bvd_message("bad", "988495", "2026-08-24T15:53:40Z", sender="someone@example.com")],
        attachments={"bad": [_bvd_attachment("a", "988495")]},
    )
    monkeypatch.setattr(
        invoice_outlook,
        "import_bvd_invoice_pdf",
        lambda *args, **kwargs: pytest.fail("untrusted mail must not be imported"),
    )
    result = invoice_outlook.import_latest_bvd_invoice_outlook(
        object(), "org-1", connector=connector, expected_company_name="MOR LOGISTICS MANITOBA LIMITED"
    )
    assert result["status"] == "no_source_found"
    assert connector.content_calls == []


def test_bvd_ambiguous_or_malformed_attachment_fails_closed(monkeypatch):
    connector = FakeOutlookConnector(
        [_bvd_message("m1", "988495", "2026-08-24T15:53:40Z")],
        attachments={
            "m1": [
                _bvd_attachment("a1", "988495"),
                _bvd_attachment("a2", "988495", content_type="application/octet-stream"),
            ]
        },
    )
    monkeypatch.setattr(
        invoice_outlook,
        "import_bvd_invoice_pdf",
        lambda *args, **kwargs: pytest.fail("ambiguous attachments must fail before import"),
    )
    result = invoice_outlook.import_latest_bvd_invoice_outlook(
        object(), "org-1", connector=connector, expected_company_name="MOR LOGISTICS MANITOBA LIMITED"
    )
    assert result["status"] == "source_contract_error"
    assert result["source_found"] is True
    assert connector.content_calls == []


@pytest.mark.parametrize("currency", ["CAD", "USD"])
def test_eco_selects_requested_currency_and_preserves_provenance(monkeypatch, currency):
    other = "USD" if currency == "CAD" else "CAD"
    connector = FakeOutlookConnector(
        [
            _eco_message("wanted", currency, "2026-08-30T21:48:08Z"),
            _eco_message("other", other, "2026-08-30T21:49:08Z"),
        ],
        attachments={
            "wanted": [_eco_attachment("wanted-a", currency)],
            "other": [_eco_attachment("other-a", other)],
        },
        content={("wanted", "wanted-a"): b"eco-invoice"},
    )
    captured = {}

    def fake_import(db, organization_id, **kwargs):
        captured.update({"organization_id": organization_id, **kwargs})
        return {"status": "idempotent_replay", "records_read": 4, "records_inserted": 4, "replayed": True}

    monkeypatch.setattr(invoice_outlook, "import_eco_invoice_pdf", fake_import)
    result = invoice_outlook.import_latest_eco_invoice_outlook(
        object(),
        "org-1",
        connector=connector,
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
        currency=currency.lower(),
    )

    assert result["status"] == "idempotent_replay"
    assert result["requested_currency"] == currency
    assert result["replayed"] is True
    assert connector.content_calls == [("wanted", "wanted-a")]
    assert captured["organization_id"] == "org-1"
    assert captured["source_message_id"] == "wanted"
    assert captured["source_attachment_id"] == "wanted-a"
    assert captured["source_filename"].endswith(f"_{currency}.pdf")


def test_eco_wrong_company_and_sender_are_not_trusted(monkeypatch):
    connector = FakeOutlookConnector(
        [
            _eco_message("company", "CAD", "2026-08-30T21:47:15Z"),
            _eco_message("sender", "CAD", "2026-08-30T21:47:16Z", sender="someone@example.com"),
        ],
        attachments={
            "company": [_eco_attachment("company-a", "CAD", company="Another Carrier Ltd")],
            "sender": [_eco_attachment("sender-a", "CAD")],
        },
    )
    monkeypatch.setattr(
        invoice_outlook,
        "import_eco_invoice_pdf",
        lambda *args, **kwargs: pytest.fail("untrusted mail must not be imported"),
    )
    result = invoice_outlook.import_latest_eco_invoice_outlook(
        object(),
        "org-1",
        connector=connector,
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
        currency="CAD",
    )
    assert result["status"] == "source_contract_error"
    assert connector.content_calls == []


def test_invalid_eco_currency_fails_before_outlook_access():
    connector = FakeOutlookConnector([])
    with pytest.raises(invoice_outlook.FuelInvoiceOutlookImportError) as exc_info:
        invoice_outlook.import_latest_eco_invoice_outlook(
            object(),
            "org-1",
            connector=connector,
            expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
            currency="EUR",
        )
    assert exc_info.value.category == "currency_contract_error"
    assert connector.folder_calls == 0


def test_fuel_router_exposes_manual_invoice_import_posts():
    routes = {route.path: route for route in fuel_router.routes}
    assert routes["/api/v1/fuel/bvd/invoices/import-outlook-latest"].methods == {"POST"}
    assert routes["/api/v1/fuel/eco/invoices/import-outlook-latest"].methods == {"POST"}
