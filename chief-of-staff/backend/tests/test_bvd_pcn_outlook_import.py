from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.api.fuel import router as fuel_router
from app.fuel import outlook_import as fuel_outlook


class FakeOutlookConnector:
    def __init__(self, messages, attachments=None, content=b"provider-pdf"):
        self.messages = messages
        self.attachments = attachments or {}
        self.content = content
        self.content_calls = []

    def list_folders(self):
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


def _message(message_id: str, filename: str, received: str, *, sender: str = fuel_outlook.BVD_PCN_SENDER):
    currency = filename.split("-")[1]
    return {
        "id": message_id,
        "subject": f"BVD PCN {filename} EFFECTIVE 2026-08-31",
        "receivedDateTime": received,
        "hasAttachments": True,
        "from": {"emailAddress": {"address": sender}},
        "currency": currency,
    }


def _attachment(attachment_id: str, filename: str):
    return {
        "id": attachment_id,
        "name": filename,
        "contentType": "application/pdf",
        "isInline": False,
    }


def test_import_latest_bvd_pcn_outlook_selects_newest_trusted_currency(monkeypatch):
    old_name = "pcn-cad-1111111-5076.pdf"
    new_name = "pcn-cad-2222222-5076.pdf"
    messages = [
        _message("old", old_name, "2026-08-30T10:00:00Z"),
        _message("new", new_name, "2026-08-30T13:22:01Z"),
        _message("usd", "pcn-usd-3333333-5076.pdf", "2026-08-30T18:50:18Z"),
    ]
    connector = FakeOutlookConnector(
        messages,
        attachments={
            "old": [_attachment("old-a", old_name)],
            "new": [_attachment("new-a", new_name)],
            "usd": [_attachment("usd-a", "pcn-usd-3333333-5076.pdf")],
        },
    )
    captured = {}

    def fake_import(db, organization_id, **kwargs):
        captured.update({"db": db, "organization_id": organization_id, **kwargs})
        return {
            "status": "import_success",
            "supplier": "bvd",
            "source_kind": "pcn_pdf",
            "source_found": True,
            "replayed": False,
            "currency": "CAD",
            "effective_start": "2026-08-31",
            "effective_end": "2026-09-01",
            "records_read": 92,
            "records_inserted": 92,
            "error_category": None,
            "completed_at": "2026-08-31T01:00:00+00:00",
        }

    monkeypatch.setattr(fuel_outlook, "import_bvd_pcn_pdf", fake_import)
    db = object()
    result = fuel_outlook.import_latest_bvd_pcn_outlook(
        db,
        "org-1",
        connector=connector,
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
        currency="cad",
    )

    assert result["status"] == "import_success"
    assert result["records_inserted"] == 92
    assert result["requested_currency"] == "CAD"
    assert result["outlook_read_only"] is True
    assert result["supplier_api_called"] is False
    assert result["secrets_exposed"] is False
    assert connector.content_calls == [("new", "new-a")]
    assert captured["db"] is db
    assert captured["organization_id"] == "org-1"
    assert captured["source_filename"] == new_name
    assert captured["source_message_id"] == "new"
    assert captured["source_attachment_id"] == "new-a"
    assert captured["expected_company_name"] == "MOR LOGISTICS MANITOBA LIMITED"
    assert captured["content"] == b"provider-pdf"
    assert captured["source_received_at"] == datetime(2026, 8, 30, 13, 22, 1, tzinfo=timezone.utc)


def test_wrong_sender_is_not_a_trusted_bvd_source(monkeypatch):
    filename = "pcn-cad-1111111-5076.pdf"
    connector = FakeOutlookConnector(
        [_message("forwarded", filename, "2026-08-30T13:22:01Z", sender="someone@example.com")],
        attachments={"forwarded": [_attachment("a", filename)]},
    )

    def should_not_import(*args, **kwargs):
        raise AssertionError("untrusted sender must not reach the fuel importer")

    monkeypatch.setattr(fuel_outlook, "import_bvd_pcn_pdf", should_not_import)
    result = fuel_outlook.import_latest_bvd_pcn_outlook(
        object(),
        "org-1",
        connector=connector,
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
        currency="CAD",
    )

    assert result["status"] == "no_source_found"
    assert result["source_found"] is False
    assert connector.content_calls == []


def test_official_message_requires_exactly_one_matching_pdf(monkeypatch):
    filename = "pcn-cad-1111111-5076.pdf"
    connector = FakeOutlookConnector(
        [_message("m1", filename, "2026-08-30T13:22:01Z")],
        attachments={
            "m1": [
                _attachment("a1", filename),
                _attachment("a2", filename),
            ]
        },
    )

    def should_not_import(*args, **kwargs):
        raise AssertionError("ambiguous attachment source must fail closed")

    monkeypatch.setattr(fuel_outlook, "import_bvd_pcn_pdf", should_not_import)
    result = fuel_outlook.import_latest_bvd_pcn_outlook(
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


def test_currency_filter_does_not_cross_import_cad_and_usd(monkeypatch):
    cad_name = "pcn-cad-1111111-5076.pdf"
    usd_name = "pcn-usd-2222222-5076.pdf"
    connector = FakeOutlookConnector(
        [
            _message("cad", cad_name, "2026-08-30T13:22:01Z"),
            _message("usd", usd_name, "2026-08-30T18:50:18Z"),
        ],
        attachments={
            "cad": [_attachment("cad-a", cad_name)],
            "usd": [_attachment("usd-a", usd_name)],
        },
    )
    captured = {}

    def fake_import(db, organization_id, **kwargs):
        captured.update(kwargs)
        return {"status": "idempotent_replay", "replayed": True, "records_read": 92, "records_inserted": 92}

    monkeypatch.setattr(fuel_outlook, "import_bvd_pcn_pdf", fake_import)
    result = fuel_outlook.import_latest_bvd_pcn_outlook(
        object(),
        "org-1",
        connector=connector,
        expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
        currency="USD",
    )

    assert captured["source_filename"] == usd_name
    assert connector.content_calls == [("usd", "usd-a")]
    assert result["requested_currency"] == "USD"
    assert result["replayed"] is True


def test_invalid_currency_fails_before_outlook_access():
    connector = FakeOutlookConnector([])
    with pytest.raises(fuel_outlook.BvdPcnOutlookImportError) as exc_info:
        fuel_outlook.import_latest_bvd_pcn_outlook(
            object(),
            "org-1",
            connector=connector,
            expected_company_name="MOR LOGISTICS MANITOBA LIMITED",
            currency="EUR",
        )
    assert exc_info.value.category == "currency_contract_error"


def test_fuel_router_exposes_only_manual_post_import_for_this_slice():
    routes = {route.path: route for route in fuel_router.routes}
    path = "/api/v1/fuel/bvd/pcn/import-outlook-latest"
    assert path in routes
    assert routes[path].methods == {"POST"}
