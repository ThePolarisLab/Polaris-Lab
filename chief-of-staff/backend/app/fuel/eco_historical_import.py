"""Explicit, single-message historical Eco price import; no mailbox writes."""

from datetime import date, datetime, timezone

from app.connectors.outlook import OutlookConnectorError
from app.fuel.eco_outlook_import import (
    EcoPriceOutlookImportError, _configured_folders, _message_candidate,
    _normalize_currency, _company_key, _safe_response,
)
from app.services.eco_price_report import (
    EcoPriceImportError, import_eco_price_pdf, parse_eco_price_pdf,
)


def import_historical_eco_price_outlook(
    db, organization_id, *, connector, expected_company_name,
    currency: str, effective_date: date, message_id: str,
):
    """Validate an explicitly selected message and PDF before any evidence write."""
    currency = _normalize_currency(currency)
    age = (datetime.now(timezone.utc).date() - effective_date).days
    if not 0 <= age <= 90:
        raise EcoPriceOutlookImportError("historical_date_out_of_range")
    if not message_id or len(message_id) > 2048 or any(c.isspace() for c in message_id):
        raise EcoPriceOutlookImportError("invalid_message_id")
    try:
        folders = {f["id"] for f in _configured_folders(connector)}
        message = connector.get_message(message_id)
        if not isinstance(message, dict) or message.get("parentFolderId") not in folders:
            raise EcoPriceOutlookImportError("source_folder_mismatch")
        # Graph may return a canonical ID spelling different from the caller's.
        # Use the fetched ID for all subsequent reads and persisted provenance.
        candidate = _message_candidate(
            connector, message, currency=currency,
            expected_company_name=expected_company_name,
            require_complete_attachments=True,
        )
        if candidate is None or candidate.received_at is None:
            raise EcoPriceOutlookImportError("source_contract_error")
        if candidate.subject_effective_date != effective_date.isoformat():
            raise EcoPriceOutlookImportError("effective_date_mismatch")
        content = connector.get_attachment_content(candidate.message_id, candidate.attachment_id)
        document = parse_eco_price_pdf(content, filename=candidate.attachment_filename)
        if document.effective_date != effective_date or document.currency != currency:
            raise EcoPriceOutlookImportError("source_contract_error")
        if _company_key(document.company_name) != _company_key(expected_company_name):
            raise EcoPriceOutlookImportError("company_mismatch")
        result = import_eco_price_pdf(
            db, organization_id, content=content,
            source_filename=candidate.attachment_filename,
            expected_company_name=expected_company_name,
            source_message_id=candidate.message_id,
            source_attachment_id=candidate.attachment_id,
            source_received_at=candidate.received_at,
        )
        return {
            **result, "source": "outlook_eco_price", "source_found": True,
            "requested_currency": currency,
            "requested_effective_date": effective_date.isoformat(),
            "outlook_read_only": True, "supplier_api_called": False,
            "secrets_exposed": False,
        }
    except (EcoPriceOutlookImportError, EcoPriceImportError) as exc:
        return {**_safe_response("import_failed", currency=currency, source_found=True),
                "error_category": exc.category}
    except OutlookConnectorError:
        return {**_safe_response("import_failed", currency=currency, source_found=False),
                "error_category": "outlook_connector_error"}
