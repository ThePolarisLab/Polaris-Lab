from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.api.fuel import router as fuel_router
from app.fuel import eco_outlook_import as eco_outlook


class FakeOutlookConnector:
    def __init__(self, messages, attachments=None, content=b"provider-pdf"):
        self.messages = messages
        self.attachments = attachments or {}
        self.content = content
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
        return self.content


def _message(
    message_id: str,
    currency: str,
    effective: str,
    received: str,
    *,
    company: str = "Mor Logistics Manitoba Limited",
    sender: str = eco_outlook.ECO_PRICE_SENDER,
):
    return {
        "id": message_id,
        "subject": f"{currency} Pricing for {company} — {effective}",
        "receivedDateTime": received,
        "hasAttachments": True,
        "sender": {"emailAddress": {"address": sender}},
    }


def _attachment(attachment_id: str, currency: str, effective: str, account: str = "u873"):
    return {
        "id": attachment_id,
        "name": f"{currency}_Pricing_{account}_{effective}.pdf",
        "contentType": "application/pdf",
        "isInline": False,
    }


def test_import_latest_eco_price_outlook_selects_newest_trusted_currency(monkeypatch):
    messages = [
        _message("old", "USD", "2026-08-29", "2026-08-29T13:37:00Z"),
        _message("new", "USD", "2026-08-30", "2026-08-30T13:37:35Z"),
        _message("cad", "CAD", "2026-08-28", "2026-08-28T13:38:00Z"),
    ]
    connector = FakeOutlookConnector(
        messages,
        attachments={
            "old": [_attachment("old-a", "USD", "2026-08-29")],
            "new": [_attachment("new-a", "USD", "2026-08-30")],
            "cad": [_attachment("cad-a", "CAD", "2026-08-28")],
        },
    )
    captured = {}

    def fake_import(db, organization_id, **kwargs):
        captured.update({"db": db, "organization_id": organization_id, **kwargs})
        return {
            "status": "import_success",
            "supplier": "eco",
            "source_kind": "price_report_pdf",
            "currency": "USD",
            "effective_start": "2026-08-30",
            "effective_end": "2026-08-30",
            "records_read": 350,
            "records_inserted": 350,
            "replayed": False,
            "error_category": None,
        }

    monkeypatch.setattr(eco_outlook, "import_eco_price_pdf", fake_import)
    db = object()
    result = eco_outlook.import_latest_eco_price_outlook(
        db,
        "org-1",
        connector=connector,
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
        currency="usd",
    )

    assert result["status"] == "import_success"
    assert result["records_inserted"] == 350
    assert result["requested_currency"] == "USD"
    assert result["subject_effective_date"] == "2026-08-30"
    assert result["source"] == "outlook_eco_price"
    assert result["outlook_read_only"] is True
    assert result["supplier_api_called"] is False
    assert result["secrets_exposed"] is False
    assert connector.content_calls == [("new", "new-a")]
    assert captured["db"] is db
    assert captured["organization_id"] == "org-1"
    assert captured["source_filename"] == "USD_Pricing_u873_2026-08-30.pdf"
    assert captured["source_message_id"] == "new"
    assert captured["source_attachment_id"] == "new-a"
    assert captured["expected_company_name"] == "MOR LOGISTICS MANITOBA LIMITED"
    assert captured["content"] == b"provider-pdf"
    assert captured["source_received_at"] == datetime(2026, 8, 30, 13, 37, 35, tzinfo=timezone.utc)


def test_wrong_sender_is_not_a_trusted_eco_source(monkeypatch):
    connector = FakeOutlookConnector(
        [_message("forwarded", "CAD", "2026-08-28", "2026-08-28T13:38:00Z", sender="someone@example.com")],
        attachments={"forwarded": [_attachment("a", "CAD", "2026-08-28")]},
    )

    def should_not_import(*args, **kwargs):
        raise AssertionError("untrusted sender must not reach the Eco importer")

    monkeypatch.setattr(eco_outlook, "import_eco_price_pdf", should_not_import)
    result = eco_outlook.import_latest_eco_price_outlook(
        object(),
        "org-1",
        connector=connector,
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
        currency="CAD",
    )

    assert result["status"] == "no_source_found"
    assert result["source_found"] is False
    assert connector.content_calls == []


def test_subject_company_must_match_authenticated_organization(monkeypatch):
    connector = FakeOutlookConnector(
        [_message("other", "CAD", "2026-08-28", "2026-08-28T13:38:00Z", company="Another Carrier Ltd")],
        attachments={"other": [_attachment("a", "CAD", "2026-08-28")]},
    )

    def should_not_import(*args, **kwargs):
        raise AssertionError("another company's report must not reach the Eco importer")

    monkeypatch.setattr(eco_outlook, "import_eco_price_pdf", should_not_import)
    result = eco_outlook.import_latest_eco_price_outlook(
        object(),
        "org-1",
        connector=connector,
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
        currency="CAD",
    )

    assert result["status"] == "no_source_found"
    assert connector.content_calls == []


def test_official_message_requires_exactly_one_matching_pdf(monkeypatch):
    connector = FakeOutlookConnector(
        [_message("m1", "CAD", "2026-08-28", "2026-08-28T13:38:00Z")],
        attachments={
            "m1": [
                _attachment("a1", "CAD", "2026-08-28"),
                _attachment("a2", "CAD", "2026-08-28", account="backup"),
            ]
        },
    )

    def should_not_import(*args, **kwargs):
        raise AssertionError("ambiguous attachment source must fail closed")

    monkeypatch.setattr(eco_outlook, "import_eco_price_pdf", should_not_import)
    result = eco_outlook.import_latest_eco_price_outlook(
        object(),
        "org-1",
        connector=connector,
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
        currency="CAD",
    )

    assert result["status"] == "source_contract_error"
    assert result["source_found"] is True
    assert connector.content_calls == []
    assert result["secrets_exposed"] is False


def test_attachment_currency_and_date_must_match_subject(monkeypatch):
    connector = FakeOutlookConnector(
        [_message("m1", "USD", "2026-08-30", "2026-08-30T13:37:35Z")],
        attachments={"m1": [_attachment("a1", "CAD", "2026-08-28")]},
    )

    def should_not_import(*args, **kwargs):
        raise AssertionError("mismatched attachment must fail before provider parsing")

    monkeypatch.setattr(eco_outlook, "import_eco_price_pdf", should_not_import)
    result = eco_outlook.import_latest_eco_price_outlook(
        object(),
        "org-1",
        connector=connector,
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
        currency="USD",
    )

    assert result["status"] == "source_contract_error"
    assert connector.content_calls == []


def test_currency_filter_does_not_cross_import_cad_and_usd(monkeypatch):
    connector = FakeOutlookConnector(
        [
            _message("cad", "CAD", "2026-08-28", "2026-08-28T13:38:00Z"),
            _message("usd", "USD", "2026-08-30", "2026-08-30T13:37:35Z"),
        ],
        attachments={
            "cad": [_attachment("cad-a", "CAD", "2026-08-28")],
            "usd": [_attachment("usd-a", "USD", "2026-08-30")],
        },
    )
    captured = {}

    def fake_import(db, organization_id, **kwargs):
        captured.update(kwargs)
        return {"status": "idempotent_replay", "replayed": True, "records_read": 67, "records_inserted": 67}

    monkeypatch.setattr(eco_outlook, "import_eco_price_pdf", fake_import)
    result = eco_outlook.import_latest_eco_price_outlook(
        object(),
        "org-1",
        connector=connector,
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
        currency="CAD",
    )

    assert captured["source_filename"] == "CAD_Pricing_u873_2026-08-28.pdf"
    assert connector.content_calls == [("cad", "cad-a")]
    assert result["requested_currency"] == "CAD"
    assert result["replayed"] is True


def test_invalid_currency_fails_before_outlook_access():
    connector = FakeOutlookConnector([])
    with pytest.raises(eco_outlook.EcoPriceOutlookImportError) as exc_info:
        eco_outlook.import_latest_eco_price_outlook(
            object(),
            "org-1",
            connector=connector,
            expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
            currency="EUR",
        )
    assert exc_info.value.category == "currency_contract_error"
    assert connector.folder_calls == 0


def test_fuel_router_exposes_manual_eco_price_import_post():
    routes = {route.path: route for route in fuel_router.routes}
    path = "/api/v1/fuel/eco/prices/import-outlook-latest"
    assert path in routes
    assert routes[path].methods == {"POST"}
