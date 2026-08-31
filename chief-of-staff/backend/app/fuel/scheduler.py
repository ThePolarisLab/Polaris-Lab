"""Disabled-by-default scheduled BVD PCN price ingestion."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.connectors.outlook import OutlookConnector
from app.connectors.outlook_credentials import OutlookCredentialStore
from app.fuel.outlook_import import import_latest_bvd_pcn_outlook
from app.organizations.models import Organization, OrganizationStatus

SCHEDULED_IMPORT_ENABLED_ENV_VAR = "POLARIS_FUEL_BVD_SCHEDULED_IMPORT_ENABLED"
SCHEDULED_ORGANIZATION_ENV_VAR = "POLARIS_FUEL_BVD_SCHEDULED_ORGANIZATION_SLUG"
_SAFE_RESULT_STATUSES = {"import_success", "idempotent_replay", "no_source_found"}


class FuelScheduledImportError(RuntimeError):
    """Sanitized scheduler configuration or tenant-resolution failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def scheduled_import_enabled() -> bool:
    return str(os.getenv(SCHEDULED_IMPORT_ENABLED_ENV_VAR) or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def resolve_scheduled_organization(session: Session) -> Organization:
    slug = str(os.getenv(SCHEDULED_ORGANIZATION_ENV_VAR) or "").strip()
    if not slug:
        raise FuelScheduledImportError(
            "missing_organization_configuration",
            "Fuel scheduled organization is not configured.",
        )
    try:
        organization = (
            session.query(Organization)
            .filter(
                Organization.slug == slug,
                Organization.status == OrganizationStatus.ACTIVE.value,
            )
            .one_or_none()
        )
    except SQLAlchemyError as exc:
        session.rollback()
        raise FuelScheduledImportError(
            "organization_lookup_failed",
            "Fuel scheduled organization lookup failed.",
        ) from exc
    if organization is None:
        raise FuelScheduledImportError(
            "organization_not_found",
            "Fuel scheduled organization was not found.",
        )
    return organization


def run_scheduled_bvd_pcn_import(session: Session) -> dict[str, Any]:
    """Read the latest trusted BVD CAD/USD PCNs through Outlook once per trigger."""

    if not scheduled_import_enabled():
        return {
            "status": "disabled",
            "supplier": "bvd",
            "scheduler_enabled": False,
            "tenant_scope_validated": False,
            "outlook_read_only": True,
            "supplier_api_called": False,
            "secrets_exposed": False,
            "currencies": {},
        }

    organization = resolve_scheduled_organization(session)
    expected_company_name = organization.legal_name or organization.display_name
    if not expected_company_name:
        raise FuelScheduledImportError(
            "organization_identity_missing",
            "Fuel scheduled organization identity is incomplete.",
        )

    connector = OutlookConnector(
        credential_store=OutlookCredentialStore(organization.id)
    )
    results: dict[str, dict[str, Any]] = {}
    for currency in ("CAD", "USD"):
        results[currency] = import_latest_bvd_pcn_outlook(
            session,
            organization.id,
            connector=connector,
            expected_company_name=expected_company_name,
            currency=currency,
        )

    statuses = {currency: str(result.get("status") or "unknown") for currency, result in results.items()}
    failed = any(status not in _SAFE_RESULT_STATUSES for status in statuses.values())
    sources_found = any(bool(result.get("source_found")) for result in results.values())

    if failed:
        overall_status = "failed"
    elif not sources_found:
        overall_status = "no_source_found"
    else:
        overall_status = "executed"

    safe_currency_results = {
        currency: {
            "status": str(result.get("status") or "unknown"),
            "source_found": bool(result.get("source_found")),
            "replayed": bool(result.get("replayed")),
            "effective_start": result.get("effective_start"),
            "effective_end": result.get("effective_end"),
            "records_read": int(result.get("records_read") or 0),
            "records_inserted": int(result.get("records_inserted") or 0),
            "error_category": result.get("error_category"),
        }
        for currency, result in results.items()
    }

    return {
        "status": overall_status,
        "supplier": "bvd",
        "scheduler_enabled": True,
        "tenant_scope_validated": True,
        "outlook_read_only": True,
        "supplier_api_called": False,
        "secrets_exposed": False,
        "currencies": safe_currency_results,
    }
