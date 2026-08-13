import os
import zipfile
from datetime import datetime, timezone
from io import BytesIO

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./polaris-ace-outlook-test.db")
os.environ.setdefault("POLARIS_ENV", "test")
os.environ.setdefault("POLARIS_LOCAL_AUTH_SECRET", "test-local-auth-secret-with-enough-length")
os.environ.setdefault("POLARIS_QBO_CLIENT_ID", "client-id")
os.environ.setdefault("POLARIS_QBO_CLIENT_SECRET", "client-secret")
os.environ.setdefault("POLARIS_QBO_REDIRECT_URI", "http://localhost:8000/api/v1/connectors/quickbooks/oauth/callback")
os.environ.setdefault("POLARIS_QBO_OAUTH_STATE_SECRET", "quickbooks-state-secret-with-enough-length")
os.environ.setdefault("POLARIS_QBO_TOKEN_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

from app.ace.outlook_import import ACE_REPORT_SUBJECT, RAW_HEADERS, AceOutlookImportError, import_latest_ace_outlook_report, parse_ace_inbond_workbook
from app.connectors.outlook import OutlookConnector
from app.database.database import Base, SessionLocal, engine
from app.models.ace import AceImportRun, AceInBondEvent, AceInBondMovement
from app.organizations.models import Organization


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal.begin() as session:
        session.add(Organization(id="org-1", slug="org-1", display_name="Org 1"))
        session.add(Organization(id="org-2", slug="org-2", display_name="Org 2"))
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


class FakeAceOutlookConnector:
    def __init__(self, *, messages=None, attachments=None, content=None):
        self.messages = messages or []
        self.attachments = attachments or {}
        self.content = content or {}
        self.message_calls = []
        self.attachment_content_calls = []

    def list_folders(self):
        return {"value": [{"id": "inbox", "displayName": "Inbox"}]}

    def list_messages(self, folder_id, *, url=None, since_iso=None):
        self.message_calls.append({"folder_id": folder_id, "url": url, "since_iso": since_iso})
        return {"value": self.messages}

    def list_attachments(self, message_id):
        return {"value": self.attachments.get(message_id, [])}

    def get_attachment_content(self, message_id, attachment_id):
        self.attachment_content_calls.append((message_id, attachment_id))
        return self.content[(message_id, attachment_id)]


def _message(message_id, *, subject=ACE_REPORT_SUBJECT, received="2026-08-13T12:00:00Z", has_attachments=True):
    return {"id": message_id, "subject": subject, "receivedDateTime": received, "hasAttachments": has_attachments}


def _attachment(attachment_id="attachment-1", *, name="ace-report.xlsx", inline=False):
    return {"id": attachment_id, "name": name, "isInline": inline, "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def _xlsx(rows=None, *, headers=RAW_HEADERS, worksheet="Report 1"):
    rows = rows if rows is not None else [_raw_row()]
    shared = [""] + list(headers)
    shared_index = {value: index for index, value in enumerate(shared)}
    sheet_rows = []
    sheet_rows.append('<row r="4"><c r="A4" t="s"><v>0</v></c>' + "".join(
        f'<c r="{_col(index + 2)}4" t="s"><v>{shared_index[header]}</v></c>' for index, header in enumerate(headers)
    ) + "</row>")
    for offset, row in enumerate(rows, start=5):
        cells = []
        for index, header in enumerate(headers):
            value = row.get(header)
            ref = f"{_col(index + 2)}{offset}"
            if value is None:
                continue
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                text = str(value)
                if text not in shared_index:
                    shared_index[text] = len(shared)
                    shared.append(text)
                cells.append(f'<c r="{ref}" t="s"><v>{shared_index[text]}</v></c>')
        sheet_rows.append(f'<row r="{offset}">{"".join(cells)}</row>')
    shared_xml = '<?xml version="1.0" encoding="UTF-8"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' + "".join(
        f"<si><t>{_xml(value)}</t></si>" for value in shared
    ) + "</sst>"
    sheet_xml = '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(sheet_rows) + "</sheetData></worksheet>"
    workbook_xml = f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{worksheet}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    rels_xml = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    content = BytesIO()
    with zipfile.ZipFile(content, "w") as workbook:
        workbook.writestr("xl/workbook.xml", workbook_xml)
        workbook.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        workbook.writestr("xl/sharedStrings.xml", shared_xml)
        workbook.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return content.getvalue()


def _raw_row(**overrides):
    row = {
        "In-Bond Number": "IB-100",
        "Bill of Lading Number": "BOL-100",
        "In-Bond Type Code": "61",
        "In-Bond Type Description": "Immediate Transportation",
        "In-Bond Source Type Description": "In-Bond Bills of Lading",
        "In-Bond Record Status Name": "Open",
        "In-Bond Carrier Code": "MLVM",
        "In-Bond Carrier Name": "Synthetic In-Bond Carrier",
        "Manifest Carrier Code": "ABCD",
        "Manifest Carrier Name": "Synthetic Manifest Carrier",
        "QP Filer Code": "8MH",
        "QP Filer Name": "Synthetic Filer",
        "Shipper Name": "Synthetic Shipper",
        "Consignee Name": "Synthetic Consignee",
        "Origination Port Name": "Synthetic Origin",
        "In-Bond Create Date": "2026-08-01",
        "In-Bond Arrival Date": "",
        "Destination Port Name": "Synthetic Destination",
        "Export Date": "",
        "Days Late": 0,
        "Days Overdue for Export": 3,
        "Late In-Transit Indicator": "N",
        "Overdue for Export Indicator": "Y",
        "Transfer of Liability Date/Time": "",
    }
    row.update(overrides)
    return row


def _col(index):
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _xml(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def test_workbook_parser_accepts_verified_contract_and_leaves_penalty_unreported():
    rows = parse_ace_inbond_workbook(_xlsx())

    assert rows == [
        {
            "inbond_number": "IB-100",
            "bill_of_lading_number": "BOL-100",
            "inbond_type_code": "61",
            "inbond_type_description": "Immediate Transportation",
            "source_type_description": "In-Bond Bills of Lading",
            "record_status": "Open",
            "inbond_carrier_code": "MLVM",
            "inbond_carrier_name": "Synthetic In-Bond Carrier",
            "manifest_carrier_code": "ABCD",
            "manifest_carrier_name": "Synthetic Manifest Carrier",
            "qp_filer_code": "8MH",
            "qp_filer_name": "Synthetic Filer",
            "shipper_name": "Synthetic Shipper",
            "consignee_name": "Synthetic Consignee",
            "origination_port_name": "Synthetic Origin",
            "create_date": datetime(2026, 8, 1).date(),
            "arrival_date": None,
            "destination_port_name": "Synthetic Destination",
            "export_date": None,
            "days_late": 0,
            "days_overdue_for_export": 3,
            "late_in_transit": "N",
            "overdue_for_export": "Y",
            "transfer_of_liability_at": None,
        }
    ]
    assert "penalty_indicator" not in rows[0]


def test_workbook_parser_rejects_missing_header_wrong_sheet_and_bad_values():
    with pytest.raises(AceOutlookImportError):
        parse_ace_inbond_workbook(_xlsx(headers=RAW_HEADERS[:-1]))
    with pytest.raises(AceOutlookImportError):
        parse_ace_inbond_workbook(_xlsx(worksheet="Other"))
    with pytest.raises(AceOutlookImportError):
        parse_ace_inbond_workbook(_xlsx(rows=[_raw_row(**{"Days Late": "abc"})]))
    with pytest.raises(AceOutlookImportError):
        parse_ace_inbond_workbook(_xlsx(rows=[_raw_row(**{"In-Bond Create Date": "not-a-date"})]))
    with pytest.raises(AceOutlookImportError):
        parse_ace_inbond_workbook(_xlsx(rows=[_raw_row(**{"Late In-Transit Indicator": "maybe"})]))
    with pytest.raises(AceOutlookImportError):
        parse_ace_inbond_workbook(_xlsx(rows=[_raw_row(**{"Bill of Lading Number": ""})]))
    assert parse_ace_inbond_workbook(_xlsx(rows=[])) == []


def test_import_latest_selects_exact_subject_newest_unprocessed_and_sanitizes_response():
    content = _xlsx(rows=[_raw_row(), _raw_row(**{"Bill of Lading Number": "BOL-101"})])
    connector = FakeAceOutlookConnector(
        messages=[
            _message("wrong-subject", subject="Other", received="2026-08-14T12:00:00Z"),
            _message("message-old", received="2026-08-13T12:00:00Z"),
            _message("message-new", received="2026-08-14T12:00:00Z"),
        ],
        attachments={"message-old": [_attachment("old")], "message-new": [_attachment("new")]},
        content={("message-new", "new"): content, ("message-old", "old"): content},
    )

    with SessionLocal() as session:
        session.add(AceImportRun(organization_id="org-1", source_message_id="message-old", status="completed"))
        session.commit()
        result = import_latest_ace_outlook_report(session, "org-1", connector=connector)

    assert result["status"] == "import_success"
    assert result["source_found"] is True
    assert result["records_read"] == 2
    assert result["records_inserted"] == 2
    assert result["exceptions_created"] == 2
    assert result["secrets_exposed"] is False
    serialized = str(result)
    assert "message-new" not in serialized
    assert "ace-report.xlsx" not in serialized
    assert connector.attachment_content_calls == [("message-new", "new")]
    assert connector.message_calls[0]["since_iso"]
    with SessionLocal() as session:
        assert session.query(AceInBondMovement).filter_by(inbond_number="IB-100").count() == 2
        assert session.query(AceInBondEvent).filter_by(event_type="first_seen").count() == 2


def test_import_latest_replay_and_next_day_update_do_not_duplicate_exception_events():
    first_content = _xlsx(rows=[_raw_row()])
    connector = FakeAceOutlookConnector(
        messages=[_message("message-1")],
        attachments={"message-1": [_attachment("attachment-1")]},
        content={("message-1", "attachment-1"): first_content},
    )
    with SessionLocal() as session:
        first = import_latest_ace_outlook_report(session, "org-1", connector=connector)
        replay = import_latest_ace_outlook_report(session, "org-1", connector=connector)

    assert first["status"] == "import_success"
    assert replay["status"] == "already_processed"
    with SessionLocal() as session:
        assert session.query(AceImportRun).filter_by(organization_id="org-1").count() == 1
        assert session.query(AceInBondMovement).count() == 1
        assert session.query(AceInBondEvent).filter_by(event_type="first_seen").count() == 1
        assert session.query(AceInBondEvent).filter_by(event_type="exception_opened").count() == 1

    next_content = _xlsx(rows=[_raw_row(**{"Days Late": 2, "Late In-Transit Indicator": "Y"})])
    next_connector = FakeAceOutlookConnector(
        messages=[_message("message-2")],
        attachments={"message-2": [_attachment("attachment-2")]},
        content={("message-2", "attachment-2"): next_content},
    )
    with SessionLocal() as session:
        update = import_latest_ace_outlook_report(session, "org-1", connector=next_connector)

    assert update["records_updated"] == 1
    with SessionLocal() as session:
        movement = session.query(AceInBondMovement).one()
        assert movement.days_late == 2
        assert movement.late_in_transit is True
        assert session.query(AceInBondEvent).filter_by(event_type="exception_opened").count() == 1


def test_manual_authorization_and_resolution_fields_survive_daily_import():
    first_connector = FakeAceOutlookConnector(
        messages=[_message("message-1")],
        attachments={"message-1": [_attachment("attachment-1")]},
        content={("message-1", "attachment-1"): _xlsx()},
    )
    with SessionLocal() as session:
        import_latest_ace_outlook_report(session, "org-1", connector=first_connector)
        movement = session.query(AceInBondMovement).one()
        movement.authorization_status = "UNAUTHORIZED - NO MOR PERMISSION"
        movement.authorization_notes = "synthetic note"
        movement.evidence_reference = "synthetic evidence"
        movement.resolution_notes = "synthetic resolution"
        session.commit()

    second_connector = FakeAceOutlookConnector(
        messages=[_message("message-2")],
        attachments={"message-2": [_attachment("attachment-2")]},
        content={("message-2", "attachment-2"): _xlsx(rows=[_raw_row(**{"Days Overdue for Export": 4})])},
    )
    with SessionLocal() as session:
        import_latest_ace_outlook_report(session, "org-1", connector=second_connector)
        movement = session.query(AceInBondMovement).one()

    assert movement.authorization_status == "UNAUTHORIZED - NO MOR PERMISSION"
    assert movement.authorization_notes == "synthetic note"
    assert movement.evidence_reference == "synthetic evidence"
    assert movement.resolution_notes == "synthetic resolution"
    assert movement.days_overdue_for_export == 4


def test_source_errors_are_safe_and_cross_org_import_ids_are_isolated():
    connector = FakeAceOutlookConnector(
        messages=[_message("message-1")],
        attachments={"message-1": [_attachment("a"), _attachment("b", name="other.xlsx")]},
        content={},
    )
    with SessionLocal() as session:
        session.add(AceImportRun(organization_id="org-2", source_message_id="message-1", status="completed"))
        session.commit()
        result = import_latest_ace_outlook_report(session, "org-1", connector=connector)

    assert result["status"] == "source_contract_error"
    assert result["source_found"] is True
    assert "message-1" not in str(result)


def test_outlook_attachment_content_request_is_read_only_and_redacted():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = request.headers
        return httpx.Response(200, content=b"xlsx-bytes", request=request)

    connector = OutlookConnector(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    connector.authenticate = lambda: None
    connector._access_token = "safe-access-token"

    assert connector.get_attachment_content("message 1", "attachment 1") == b"xlsx-bytes"
    assert captured["url"] == "https://graph.microsoft.com/v1.0/me/messages/message%201/attachments/attachment%201/$value"
    assert captured["headers"]["Accept"] == "application/octet-stream"
    assert captured["headers"]["Authorization"] == "Bearer safe-access-token"
