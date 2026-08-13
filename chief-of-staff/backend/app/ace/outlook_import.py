"""Manual Outlook ACE In-Bond Bills of Lading import pipeline."""

from __future__ import annotations

import logging
import os
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from app.ace.service import AceImportValidationError, import_rows
from app.connectors.outlook import OutlookConnector, OutlookConnectorError
from app.models.ace import AceImportRun

ACE_REPORT_SUBJECT = "MOR ACE Daily In-Bond Report"
ACE_REPORT_WORKSHEET = "Report 1"
ACE_HEADER_ROW = 4
SAFE_FEED_ERROR = "ACE Outlook report import failed validation."
logger = logging.getLogger(__name__)

RAW_HEADERS = (
    "In-Bond Number",
    "Bill of Lading Number",
    "In-Bond Type Code",
    "In-Bond Type Description",
    "In-Bond Source Type Description",
    "In-Bond Record Status Name",
    "In-Bond Carrier Code",
    "In-Bond Carrier Name",
    "Manifest Carrier Code",
    "Manifest Carrier Name",
    "QP Filer Code",
    "QP Filer Name",
    "Shipper Name",
    "Consignee Name",
    "Origination Port Name",
    "In-Bond Create Date",
    "In-Bond Arrival Date",
    "Destination Port Name",
    "Export Date",
    "Days Late",
    "Days Overdue for Export",
    "Late In-Transit Indicator",
    "Overdue for Export Indicator",
    "Transfer of Liability Date/Time",
)

HEADER_TO_FIELD = {
    "In-Bond Number": "inbond_number",
    "Bill of Lading Number": "bill_of_lading_number",
    "In-Bond Type Code": "inbond_type_code",
    "In-Bond Type Description": "inbond_type_description",
    "In-Bond Source Type Description": "source_type_description",
    "In-Bond Record Status Name": "record_status",
    "In-Bond Carrier Code": "inbond_carrier_code",
    "In-Bond Carrier Name": "inbond_carrier_name",
    "Manifest Carrier Code": "manifest_carrier_code",
    "Manifest Carrier Name": "manifest_carrier_name",
    "QP Filer Code": "qp_filer_code",
    "QP Filer Name": "qp_filer_name",
    "Shipper Name": "shipper_name",
    "Consignee Name": "consignee_name",
    "Origination Port Name": "origination_port_name",
    "In-Bond Create Date": "create_date",
    "In-Bond Arrival Date": "arrival_date",
    "Destination Port Name": "destination_port_name",
    "Export Date": "export_date",
    "Days Late": "days_late",
    "Days Overdue for Export": "days_overdue_for_export",
    "Late In-Transit Indicator": "late_in_transit",
    "Overdue for Export Indicator": "overdue_for_export",
    "Transfer of Liability Date/Time": "transfer_of_liability_at",
}

DATE_HEADERS = {"In-Bond Create Date", "In-Bond Arrival Date", "Export Date"}
DATETIME_HEADERS = {"Transfer of Liability Date/Time"}
INTEGER_HEADERS = {"Days Late", "Days Overdue for Export"}
BOOLEAN_HEADERS = {"Late In-Transit Indicator", "Overdue for Export Indicator"}


class AceOutlookImportError(RuntimeError):
    def __init__(self, category: str, message: str = SAFE_FEED_ERROR) -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class AceOutlookCandidate:
    message_id: str
    received_at: datetime | None
    attachment_id: str
    attachment_filename: str | None


def import_latest_ace_outlook_report(
    db: Session,
    organization_id: str,
    *,
    connector: OutlookConnector,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    try:
        candidate_result = _select_latest_candidate(db, organization_id, connector=connector)
        if candidate_result["status"] != "source_found":
            return _safe_response(candidate_result["status"], started_at=started, source_found=candidate_result["source_found"])

        candidate: AceOutlookCandidate = candidate_result["candidate"]
        content = connector.get_attachment_content(candidate.message_id, candidate.attachment_id)
        rows = parse_ace_inbond_workbook(content)
        result = import_rows(
            db,
            organization_id,
            source_message_id=candidate.message_id,
            source_filename=candidate.attachment_filename,
            source_received_at=candidate.received_at,
            rows=rows,
        )
        if result.get("status") == "failed":
            status = "import_failed"
        elif result.get("status") == "idempotent_replay":
            status = "already_processed"
        else:
            status = "import_success"
        logger.info(
            "ACE Outlook report import completed",
            extra={
                "operation": "ace_outlook_import",
                "organization_id": organization_id,
                "source_found": True,
                "replayed": status == "already_processed",
                "records_read": result.get("records_read", 0),
                "records_inserted": result.get("inserted", 0),
                "records_updated": result.get("updated", 0),
                "exceptions_created": result.get("exceptions_created", 0),
                "status_category": status,
            },
        )
        return _safe_response(
            status,
            started_at=started,
            source_found=True,
            replayed=status == "already_processed",
            records_read=result.get("records_read", 0),
            records_inserted=result.get("inserted", 0),
            records_updated=result.get("updated", 0),
            exceptions_created=result.get("exceptions_created", 0),
            import_status=result.get("status"),
            completed_at=result.get("completed_at"),
        )
    except (AceOutlookImportError, AceImportValidationError) as exc:
        logger.info(
            "ACE Outlook report import rejected",
            extra={
                "operation": "ace_outlook_import",
                "organization_id": organization_id,
                "source_found": True,
                "status_category": getattr(exc, "category", "source_contract_error"),
            },
        )
        return _safe_response(getattr(exc, "category", "source_contract_error"), started_at=started, source_found=True)
    except OutlookConnectorError:
        logger.info(
            "ACE Outlook report import connector failure",
            extra={"operation": "ace_outlook_import", "organization_id": organization_id, "status_category": "import_failed"},
        )
        return _safe_response("import_failed", started_at=started, source_found=False)


def parse_ace_inbond_workbook(content: bytes) -> list[dict[str, Any]]:
    try:
        with zipfile.ZipFile(BytesIO(content)) as workbook:
            shared_strings = _shared_strings(workbook)
            sheet_path = _worksheet_path(workbook, ACE_REPORT_WORKSHEET)
            cells = _worksheet_cells(workbook, sheet_path, shared_strings)
    except (KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise AceOutlookImportError("source_contract_error") from exc

    header_values = [_clean_text(cells.get((ACE_HEADER_ROW, column))) for column in range(2, 2 + len(RAW_HEADERS))]
    if tuple(header_values) != RAW_HEADERS:
        raise AceOutlookImportError("source_contract_error")

    rows: list[dict[str, Any]] = []
    for row_number in sorted({row for row, column in cells if row > ACE_HEADER_ROW and column >= 2}):
        values = {header: cells.get((row_number, index + 2)) for index, header in enumerate(RAW_HEADERS)}
        if all(_blank(value) for value in values.values()):
            continue
        rows.append(_normalize_raw_row(values))
    return rows


def _normalize_raw_row(values: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for header, field in HEADER_TO_FIELD.items():
        value = values.get(header)
        if header in DATE_HEADERS:
            row[field] = _coerce_date(value, header)
        elif header in DATETIME_HEADERS:
            row[field] = _coerce_datetime(value, header)
        elif header in INTEGER_HEADERS:
            row[field] = _coerce_int(value, header)
        elif header in BOOLEAN_HEADERS:
            row[field] = _coerce_indicator(value, header)
        else:
            row[field] = _clean_text(value)
    if not row.get("inbond_number") or not row.get("bill_of_lading_number"):
        raise AceOutlookImportError("source_contract_error")
    return row


def _select_latest_candidate(db: Session, organization_id: str, *, connector: OutlookConnector) -> dict[str, Any]:
    folders = _configured_folders(connector)
    if not folders:
        return {"status": "no_source_found", "source_found": False}
    since = (datetime.now(timezone.utc) - timedelta(days=_lookback_days())).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    processed = {
        source_message_id
        for (source_message_id,) in db.query(AceImportRun.source_message_id)
        .filter(AceImportRun.organization_id == organization_id, AceImportRun.status == "completed")
        .all()
    }
    candidates: list[AceOutlookCandidate] = []
    processed_match_found = False
    for folder in folders:
        next_url: str | None = None
        pages = 0
        while pages < _max_pages():
            payload = connector.list_messages(folder["id"], url=next_url, since_iso=since if next_url is None else None)
            pages += 1
            for message in payload.get("value") or []:
                if _clean_text(message.get("subject")) != ACE_REPORT_SUBJECT:
                    continue
                message_id = str(message.get("id") or "")
                if message_id in processed:
                    processed_match_found = True
                    continue
                candidate = _message_candidate(connector, message)
                if candidate is None:
                    continue
                candidates.append(candidate)
            next_link = payload.get("@odata.nextLink")
            if not isinstance(next_link, str) or not next_link:
                break
            next_url = next_link

    if candidates:
        candidates.sort(key=lambda item: item.received_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return {"status": "source_found", "source_found": True, "candidate": candidates[0]}
    if processed_match_found:
        return {"status": "already_processed", "source_found": True}
    return {"status": "no_source_found", "source_found": False}


def _configured_folders(connector: OutlookConnector) -> list[dict[str, str]]:
    wanted = {_norm(value) for value in os.getenv("POLARIS_ACE_OUTLOOK_FOLDERS", "Inbox").split(",") if value.strip()}
    payload = connector.list_folders()
    return [
        {"id": str(item.get("id") or ""), "display_name": str(item.get("displayName") or "")}
        for item in payload.get("value") or []
        if isinstance(item, dict) and str(item.get("id") or "") and _norm(str(item.get("displayName") or "")) in wanted
    ]


def _message_candidate(connector: OutlookConnector, message: dict[str, Any]) -> AceOutlookCandidate | None:
    if _clean_text(message.get("subject")) != ACE_REPORT_SUBJECT:
        return None
    if not bool(message.get("hasAttachments")):
        raise AceOutlookImportError("source_contract_error")
    message_id = str(message.get("id") or "")
    if not message_id:
        return None
    payload = connector.list_attachments(message_id)
    matches = [
        item for item in payload.get("value") or []
        if isinstance(item, dict) and not item.get("isInline") and str(item.get("name") or "").casefold().endswith(".xlsx")
    ]
    if len(matches) > 1:
        raise AceOutlookImportError("source_contract_error")
    if not matches:
        raise AceOutlookImportError("source_contract_error")
    attachment = matches[0]
    attachment_id = str(attachment.get("id") or "")
    if not attachment_id:
        raise AceOutlookImportError("source_contract_error")
    return AceOutlookCandidate(
        message_id=message_id,
        received_at=_parse_dt(message.get("receivedDateTime")),
        attachment_id=attachment_id,
        attachment_filename=_clean_text(attachment.get("name")),
    )


def _worksheet_path(workbook: zipfile.ZipFile, sheet_name: str) -> str:
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    root = ET.fromstring(workbook.read("xl/workbook.xml"))
    rels = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels if "Id" in rel.attrib and "Target" in rel.attrib}
    for sheet in root.findall("main:sheets/main:sheet", ns):
        if sheet.attrib.get("name") != sheet_name:
            continue
        rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rel_targets.get(rel_id or "")
        if not target:
            break
        return str(PurePosixPath("xl") / target.lstrip("/"))
    raise AceOutlookImportError("source_contract_error")


def _shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    values: list[str] = []
    for item in root.findall("main:si", ns):
        parts = [node.text or "" for node in item.findall(".//main:t", ns)]
        values.append("".join(parts))
    return values


def _worksheet_cells(workbook: zipfile.ZipFile, path: str, shared_strings: list[str]) -> dict[tuple[int, int], Any]:
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ET.fromstring(workbook.read(path))
    cells: dict[tuple[int, int], Any] = {}
    for cell in root.findall(".//main:c", ns):
        ref = cell.attrib.get("r", "")
        row, column = _cell_ref(ref)
        if row <= 0 or column <= 0:
            continue
        cells[(row, column)] = _cell_value(cell, shared_strings)
    return cells


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> Any:
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", ns))
    value_node = cell.find("main:v", ns)
    if value_node is None or value_node.text is None:
        return None
    value = value_node.text
    if cell_type == "s":
        try:
            return shared_strings[int(value)]
        except (ValueError, IndexError) as exc:
            raise AceOutlookImportError("source_contract_error") from exc
    if cell_type == "b":
        return value == "1"
    try:
        number = float(value)
    except ValueError:
        return value
    return int(number) if number.is_integer() else number


def _cell_ref(ref: str) -> tuple[int, int]:
    letters = "".join(char for char in ref if char.isalpha())
    digits = "".join(char for char in ref if char.isdigit())
    if not letters or not digits:
        return 0, 0
    column = 0
    for char in letters.upper():
        column = column * 26 + (ord(char) - ord("A") + 1)
    return int(digits), column


def _coerce_date(value: Any, field_name: str) -> date | None:
    if _blank(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _excel_datetime(float(value)).date()
    text = _clean_text(value)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text or "", fmt).date()
        except ValueError:
            continue
    raise AceOutlookImportError("source_contract_error")


def _coerce_datetime(value: Any, field_name: str) -> datetime | None:
    if _blank(value):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _excel_datetime(float(value))
    text = _clean_text(value) or ""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y %I:%M %p", "%m/%d/%y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise AceOutlookImportError("source_contract_error")


def _coerce_int(value: Any, field_name: str) -> int:
    if _blank(value):
        return 0
    if isinstance(value, bool):
        raise AceOutlookImportError("source_contract_error")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = _clean_text(value)
    try:
        return int(text or "")
    except ValueError as exc:
        raise AceOutlookImportError("source_contract_error") from exc


def _coerce_indicator(value: Any, field_name: str) -> str:
    text = _clean_text(value)
    if text in {"Y", "N"}:
        return text
    raise AceOutlookImportError("source_contract_error")


def _excel_datetime(value: float) -> datetime:
    return datetime(1899, 12, 30) + timedelta(days=value)


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _safe_response(
    status: str,
    *,
    started_at: datetime,
    source_found: bool,
    replayed: bool = False,
    records_read: int = 0,
    records_inserted: int = 0,
    records_updated: int = 0,
    exceptions_created: int = 0,
    import_status: str | None = None,
    completed_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "source_found": source_found,
        "replayed": replayed or status == "already_processed",
        "records_read": records_read,
        "records_inserted": records_inserted,
        "records_updated": records_updated,
        "records_unchanged": 0,
        "exceptions_created": exceptions_created,
        "import_status": import_status or status,
        "started_at": started_at,
        "completed_at": completed_at,
        "secrets_exposed": False,
    }


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _lookback_days() -> int:
    return max(1, min(int(os.getenv("POLARIS_ACE_OUTLOOK_LOOKBACK_DAYS", "14")), 90))


def _max_pages() -> int:
    return max(1, min(int(os.getenv("POLARIS_ACE_OUTLOOK_MAX_PAGES", "5")), 20))
