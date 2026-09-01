"""Read-only Outlook selection for trusted BVD and Eco fuel invoices."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.connectors.outlook import OutlookConnector, OutlookConnectorError
from app.services.bvd_invoice import parse_bvd_invoice_pdf
from app.services.fuel_invoice import FuelInvoiceImportError
from app.services.fuel_invoice_importers import import_bvd_invoice_pdf, import_eco_invoice_pdf


BVD_INVOICE_SENDER = "applications@bvdpetroleum.com"
ECO_INVOICE_SENDER = "billing@ecopetroleum.ca"

_BVD_SUBJECT_RE = re.compile(r"^BVD Invoice Number (?P<invoice>\d+)$", re.IGNORECASE)
_BVD_ATTACHMENT_RE = re.compile(r"^BVD_invoice_(?P<invoice>\d+)\.pdf$", re.IGNORECASE)
_ECO_SUBJECT_RE = re.compile(
    r"^Fuel Invoice; (?P<start>\d{2}-\d{2})_(?P<end>\d{2}-\d{2})_(?P<currency>CAD|USD)$",
    re.IGNORECASE,
)
_ECO_ATTACHMENT_RE = re.compile(
    r"^(?P<company>.+)_(?P<start>\d{2}-\d{2})_(?P<end>\d{2}-\d{2})_(?P<currency>CAD|USD)\.pdf$",
    re.IGNORECASE,
)


class FuelInvoiceOutlookImportError(RuntimeError):
    """Safe invoice source-selection failure without provider content."""

    def __init__(self, category: str) -> None:
        super().__init__("Fuel invoice Outlook import failed validation.")
        self.category = category


@dataclass(frozen=True)
class InvoiceCandidate:
    message_id: str
    received_at: datetime | None
    attachment_id: str
    attachment_filename: str
    currency: str | None = None


def import_latest_bvd_invoice_outlook(
    db: Session,
    organization_id: str,
    *,
    connector: OutlookConnector,
    expected_company_name: str,
) -> dict[str, Any]:
    """Import the newest valid BVD fuel invoice, skipping Express-only invoices."""

    try:
        candidates = _bvd_candidates(connector)
        for candidate in candidates:
            content = connector.get_attachment_content(candidate.message_id, candidate.attachment_id)
            try:
                parse_bvd_invoice_pdf(content, candidate.attachment_filename)
            except FuelInvoiceImportError as exc:
                if exc.category == "non_fuel_invoice":
                    continue
                return _safe_response("bvd", exc.category, source_found=True)

            result = import_bvd_invoice_pdf(
                db,
                organization_id,
                content=content,
                source_filename=candidate.attachment_filename,
                expected_company_name=expected_company_name,
                source_message_id=candidate.message_id,
                source_attachment_id=candidate.attachment_id,
                source_received_at=candidate.received_at,
            )
            return _success_response(result, supplier="bvd")
        return _safe_response("bvd", "no_source_found", source_found=False)
    except FuelInvoiceOutlookImportError as exc:
        return _safe_response("bvd", exc.category, source_found=True)
    except OutlookConnectorError:
        return _safe_response("bvd", "outlook_connector_error", source_found=False)


def import_latest_eco_invoice_outlook(
    db: Session,
    organization_id: str,
    *,
    connector: OutlookConnector,
    expected_company_name: str,
    currency: str,
) -> dict[str, Any]:
    """Import the newest trusted Eco weekly invoice for one currency."""

    target_currency = _normalize_currency(currency)
    try:
        candidates = _eco_candidates(
            connector,
            currency=target_currency,
            expected_company_name=expected_company_name,
        )
        if not candidates:
            return _safe_response("eco", "no_source_found", source_found=False, currency=target_currency)
        candidate = candidates[0]
        content = connector.get_attachment_content(candidate.message_id, candidate.attachment_id)
        result = import_eco_invoice_pdf(
            db,
            organization_id,
            content=content,
            source_filename=candidate.attachment_filename,
            expected_company_name=expected_company_name,
            source_message_id=candidate.message_id,
            source_attachment_id=candidate.attachment_id,
            source_received_at=candidate.received_at,
        )
        return _success_response(result, supplier="eco", currency=target_currency)
    except FuelInvoiceOutlookImportError as exc:
        return _safe_response("eco", exc.category, source_found=True, currency=target_currency)
    except OutlookConnectorError:
        return _safe_response("eco", "outlook_connector_error", source_found=False, currency=target_currency)


def _bvd_candidates(connector: OutlookConnector) -> list[InvoiceCandidate]:
    def candidate(message: dict[str, Any]) -> InvoiceCandidate | None:
        match = _BVD_SUBJECT_RE.fullmatch(_clean(message.get("subject")))
        if match is None or _sender_address(message) != BVD_INVOICE_SENDER:
            return None
        attachment = _one_pdf_attachment(
            connector,
            message,
            matcher=lambda name: (
                (found := _BVD_ATTACHMENT_RE.fullmatch(name)) is not None
                and found.group("invoice") == match.group("invoice")
            ),
        )
        return _candidate_from(message, attachment)

    return _collect_candidates(connector, folder_env="POLARIS_FUEL_BVD_INVOICE_OUTLOOK_FOLDERS", build=candidate)


def _eco_candidates(
    connector: OutlookConnector,
    *,
    currency: str,
    expected_company_name: str,
) -> list[InvoiceCandidate]:
    def candidate(message: dict[str, Any]) -> InvoiceCandidate | None:
        match = _ECO_SUBJECT_RE.fullmatch(_clean(message.get("subject")))
        if (
            match is None
            or match.group("currency").upper() != currency
            or _sender_address(message) != ECO_INVOICE_SENDER
        ):
            return None

        def matches(name: str) -> bool:
            found = _ECO_ATTACHMENT_RE.fullmatch(name)
            return bool(
                found
                and found.group("currency").upper() == currency
                and found.group("start") == match.group("start")
                and found.group("end") == match.group("end")
                and _company_key(found.group("company")) == _company_key(expected_company_name)
            )

        attachment = _one_pdf_attachment(connector, message, matcher=matches)
        return _candidate_from(message, attachment, currency=currency)

    return _collect_candidates(connector, folder_env="POLARIS_FUEL_ECO_INVOICE_OUTLOOK_FOLDERS", build=candidate)


def _collect_candidates(
    connector: OutlookConnector,
    *,
    folder_env: str,
    build: Callable[[dict[str, Any]], InvoiceCandidate | None],
) -> list[InvoiceCandidate]:
    folders = _configured_folders(connector, folder_env)
    if not folders:
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=_lookback_days())).replace(microsecond=0)
    since_iso = since.isoformat().replace("+00:00", "Z")
    candidates: list[InvoiceCandidate] = []
    for folder_id in folders:
        next_url: str | None = None
        pages = 0
        while pages < _max_pages():
            payload = connector.list_messages(
                folder_id,
                url=next_url,
                since_iso=since_iso if next_url is None else None,
            )
            pages += 1
            for message in payload.get("value") or []:
                if isinstance(message, dict):
                    item = build(message)
                    if item is not None:
                        candidates.append(item)
            next_link = payload.get("@odata.nextLink")
            if not isinstance(next_link, str) or not next_link:
                break
            next_url = next_link
    candidates.sort(key=_received_sort_key, reverse=True)
    return candidates


def _one_pdf_attachment(
    connector: OutlookConnector,
    message: dict[str, Any],
    *,
    matcher: Callable[[str], bool],
) -> dict[str, Any]:
    if not bool(message.get("hasAttachments")) or not str(message.get("id") or "").strip():
        raise FuelInvoiceOutlookImportError("source_contract_error")
    message_id = str(message["id"]).strip()
    payload = connector.list_attachments(message_id)
    matches = [
        item
        for item in payload.get("value") or []
        if isinstance(item, dict)
        and not bool(item.get("isInline"))
        and str(item.get("contentType") or "").casefold() in {"application/pdf", "application/octet-stream"}
        and matcher(str(item.get("name") or "").strip())
    ]
    if len(matches) != 1:
        raise FuelInvoiceOutlookImportError("source_contract_error")
    return matches[0]


def _candidate_from(
    message: dict[str, Any],
    attachment: dict[str, Any],
    *,
    currency: str | None = None,
) -> InvoiceCandidate:
    message_id = str(message.get("id") or "").strip()
    attachment_id = str(attachment.get("id") or "").strip()
    filename = str(attachment.get("name") or "").strip()
    if not message_id or not attachment_id or not filename:
        raise FuelInvoiceOutlookImportError("source_contract_error")
    return InvoiceCandidate(
        message_id=message_id,
        received_at=_parse_dt(message.get("receivedDateTime")),
        attachment_id=attachment_id,
        attachment_filename=filename,
        currency=currency,
    )


def _configured_folders(connector: OutlookConnector, env_name: str) -> list[str]:
    wanted = {_norm(value) for value in os.getenv(env_name, "Inbox").split(",") if value.strip()}
    return [
        str(item.get("id"))
        for item in connector.list_folders().get("value") or []
        if isinstance(item, dict)
        and str(item.get("id") or "")
        and _norm(str(item.get("displayName") or "")) in wanted
    ]


def _sender_address(message: dict[str, Any]) -> str:
    sender = message.get("from") or message.get("sender") or {}
    email = sender.get("emailAddress") if isinstance(sender, dict) else {}
    return str(email.get("address") or "").strip().casefold() if isinstance(email, dict) else ""


def _parse_dt(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FuelInvoiceOutlookImportError("source_contract_error") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _received_sort_key(candidate: InvoiceCandidate) -> datetime:
    return candidate.received_at or datetime.min.replace(tzinfo=timezone.utc)


def _normalize_currency(value: str) -> str:
    currency = str(value or "").strip().upper()
    if currency not in {"CAD", "USD"}:
        raise FuelInvoiceOutlookImportError("currency_contract_error")
    return currency


def _lookback_days() -> int:
    return _positive_int_env("POLARIS_FUEL_INVOICE_OUTLOOK_LOOKBACK_DAYS", 14, 60)


def _max_pages() -> int:
    return _positive_int_env("POLARIS_FUEL_INVOICE_OUTLOOK_MAX_PAGES", 10, 50)


def _positive_int_env(name: str, default: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return min(value, maximum) if value > 0 else default


def _company_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _norm(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _success_response(
    result: dict[str, object],
    *,
    supplier: str,
    currency: str | None = None,
) -> dict[str, Any]:
    return {
        **result,
        "source": f"outlook_{supplier}_invoice",
        "source_found": True,
        "requested_currency": currency,
        "outlook_read_only": True,
        "supplier_api_called": False,
        "secrets_exposed": False,
    }


def _safe_response(
    supplier: str,
    status: str,
    *,
    source_found: bool,
    currency: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "supplier": supplier,
        "source": f"outlook_{supplier}_invoice",
        "source_found": source_found,
        "requested_currency": currency,
        "records_read": 0,
        "records_inserted": 0,
        "replayed": False,
        "outlook_read_only": True,
        "supplier_api_called": False,
        "secrets_exposed": False,
    }
