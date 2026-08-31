"""Read-only Outlook source selection for Eco Petroleum fuel-price evidence."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.outlook import OutlookConnector, OutlookConnectorError
from app.services.eco_price_report import import_eco_price_pdf


ECO_PRICE_SENDER = "no-reply@pricing.ecopetroleum.ca"
SAFE_OUTLOOK_ERROR = "Eco price Outlook import failed validation."
_SUBJECT_RE = re.compile(
    r"^(?P<currency>CAD|USD) Pricing for (?P<company>.+?) — (?P<effective>\d{4}-\d{2}-\d{2})$",
    re.IGNORECASE,
)
_ATTACHMENT_RE = re.compile(
    r"^(?P<currency>CAD|USD)_Pricing_[A-Za-z0-9._-]+_(?P<effective>\d{4}-\d{2}-\d{2})\.pdf$",
    re.IGNORECASE,
)


class EcoPriceOutlookImportError(RuntimeError):
    """Safe source-selection failure without message or attachment content."""

    def __init__(self, category: str) -> None:
        super().__init__(SAFE_OUTLOOK_ERROR)
        self.category = category


@dataclass(frozen=True)
class EcoPriceOutlookCandidate:
    message_id: str
    received_at: datetime | None
    attachment_id: str
    attachment_filename: str
    currency: str
    subject_effective_date: str


def import_latest_eco_price_outlook(
    db: Session,
    organization_id: str,
    *,
    connector: OutlookConnector,
    expected_company_name: str,
    currency: str,
) -> dict[str, Any]:
    """Import the newest trusted Eco price-report email for one requested currency."""

    target_currency = _normalize_currency(currency)
    try:
        candidate = _select_latest_candidate(
            connector=connector,
            currency=target_currency,
            expected_company_name=expected_company_name,
        )
        if candidate is None:
            return _safe_response("no_source_found", currency=target_currency, source_found=False)

        content = connector.get_attachment_content(candidate.message_id, candidate.attachment_id)
        result = import_eco_price_pdf(
            db,
            organization_id,
            content=content,
            source_filename=candidate.attachment_filename,
            expected_company_name=expected_company_name,
            source_message_id=candidate.message_id,
            source_attachment_id=candidate.attachment_id,
            source_received_at=candidate.received_at,
        )
        return {
            **result,
            "source": "outlook_eco_price",
            "source_found": True,
            "requested_currency": target_currency,
            "subject_effective_date": candidate.subject_effective_date,
            "outlook_read_only": True,
            "supplier_api_called": False,
            "secrets_exposed": False,
        }
    except EcoPriceOutlookImportError as exc:
        return _safe_response(exc.category, currency=target_currency, source_found=True)
    except OutlookConnectorError:
        return _safe_response("outlook_connector_error", currency=target_currency, source_found=False)


def _select_latest_candidate(
    *,
    connector: OutlookConnector,
    currency: str,
    expected_company_name: str,
) -> EcoPriceOutlookCandidate | None:
    folders = _configured_folders(connector)
    if not folders:
        return None

    since = (datetime.now(timezone.utc) - timedelta(days=_lookback_days())).replace(microsecond=0)
    since_iso = since.isoformat().replace("+00:00", "Z")
    candidates: list[EcoPriceOutlookCandidate] = []

    for folder in folders:
        next_url: str | None = None
        pages = 0
        while pages < _max_pages():
            payload = connector.list_messages(
                folder["id"],
                url=next_url,
                since_iso=since_iso if next_url is None else None,
            )
            pages += 1
            for message in payload.get("value") or []:
                if not isinstance(message, dict):
                    continue
                candidate = _message_candidate(
                    connector,
                    message,
                    currency=currency,
                    expected_company_name=expected_company_name,
                )
                if candidate is not None:
                    candidates.append(candidate)

            next_link = payload.get("@odata.nextLink")
            if not isinstance(next_link, str) or not next_link:
                break
            next_url = next_link

    if not candidates:
        return None
    candidates.sort(
        key=lambda item: item.received_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return candidates[0]


def _configured_folders(connector: OutlookConnector) -> list[dict[str, str]]:
    wanted = {
        _norm(value)
        for value in os.getenv("POLARIS_FUEL_ECO_OUTLOOK_FOLDERS", "Inbox").split(",")
        if value.strip()
    }
    payload = connector.list_folders()
    return [
        {"id": str(item.get("id") or ""), "display_name": str(item.get("displayName") or "")}
        for item in payload.get("value") or []
        if isinstance(item, dict)
        and str(item.get("id") or "")
        and _norm(str(item.get("displayName") or "")) in wanted
    ]


def _message_candidate(
    connector: OutlookConnector,
    message: dict[str, Any],
    *,
    currency: str,
    expected_company_name: str,
) -> EcoPriceOutlookCandidate | None:
    subject = _clean(message.get("subject"))
    match = _SUBJECT_RE.fullmatch(subject)
    if match is None or match.group("currency").upper() != currency:
        return None
    if _company_key(match.group("company")) != _company_key(expected_company_name):
        return None
    if _sender_address(message) != ECO_PRICE_SENDER:
        return None
    if not bool(message.get("hasAttachments")):
        raise EcoPriceOutlookImportError("source_contract_error")

    message_id = str(message.get("id") or "").strip()
    if not message_id:
        raise EcoPriceOutlookImportError("source_contract_error")

    effective = match.group("effective")
    attachment_payload = connector.list_attachments(message_id)
    matches = []
    for item in attachment_payload.get("value") or []:
        if not isinstance(item, dict) or bool(item.get("isInline")):
            continue
        filename = str(item.get("name") or "").strip()
        attachment_match = _ATTACHMENT_RE.fullmatch(filename)
        if attachment_match is None:
            continue
        if attachment_match.group("currency").upper() != currency:
            continue
        if attachment_match.group("effective") != effective:
            continue
        if str(item.get("contentType") or "").casefold() not in {"application/pdf", "application/octet-stream"}:
            continue
        matches.append(item)

    if len(matches) != 1:
        raise EcoPriceOutlookImportError("source_contract_error")

    attachment_id = str(matches[0].get("id") or "").strip()
    attachment_filename = str(matches[0].get("name") or "").strip()
    if not attachment_id or not attachment_filename:
        raise EcoPriceOutlookImportError("source_contract_error")

    return EcoPriceOutlookCandidate(
        message_id=message_id,
        received_at=_parse_dt(message.get("receivedDateTime")),
        attachment_id=attachment_id,
        attachment_filename=attachment_filename,
        currency=currency,
        subject_effective_date=effective,
    )


def _sender_address(message: dict[str, Any]) -> str:
    sender = message.get("from") or message.get("sender") or {}
    if not isinstance(sender, dict):
        return ""
    email_address = sender.get("emailAddress") or {}
    if not isinstance(email_address, dict):
        return ""
    return str(email_address.get("address") or "").strip().casefold()


def _parse_dt(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EcoPriceOutlookImportError("source_contract_error") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _normalize_currency(value: str) -> str:
    currency = str(value or "").strip().upper()
    if currency not in {"CAD", "USD"}:
        raise EcoPriceOutlookImportError("currency_contract_error")
    return currency


def _lookback_days() -> int:
    return _positive_int_env("POLARIS_FUEL_ECO_OUTLOOK_LOOKBACK_DAYS", default=7, maximum=31)


def _max_pages() -> int:
    return _positive_int_env("POLARIS_FUEL_ECO_OUTLOOK_MAX_PAGES", default=10, maximum=50)


def _positive_int_env(name: str, *, default: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < 1:
        return default
    return min(value, maximum)


def _company_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _norm(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _safe_response(status: str, *, currency: str, source_found: bool) -> dict[str, Any]:
    return {
        "status": status,
        "supplier": "eco",
        "source": "outlook_eco_price",
        "source_found": source_found,
        "requested_currency": currency,
        "records_read": 0,
        "records_inserted": 0,
        "replayed": False,
        "outlook_read_only": True,
        "supplier_api_called": False,
        "secrets_exposed": False,
    }
