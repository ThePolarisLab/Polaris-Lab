"""Builder-facing Connector SDK endpoints."""

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorHealth, ConnectorStatus, SyncResult
from app.connectors.motive import MotiveConnector
from app.connectors.outlook import OutlookConnector
from app.connectors.outlook_credentials import OutlookCredentialStore
from app.connectors.quickbooks import QuickBooksConnector
from app.connectors.quickbooks_credentials import QuickBooksCredentialStore
from app.connectors.registry import connector_registry
from app.connectors.torqueai import TorqueAIConnector, TorqueAIConnectorError, TorqueAIDispatchPage
from app.connectors.torqueai_ingestion import TorqueAIDispatchIngestionError, ingest_torqueai_dispatches
from app.database.database import SessionLocal
from app.organizations.models import Organization
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])


def _db() -> Session:
    with SessionLocal() as session:
        yield session


class TorqueAIDispatchIngestRequest(BaseModel):
    date_from: date = Field(alias="from")
    date_to: date = Field(alias="to")


def _tenant_connector(connector: BaseConnector, principal: AuthenticatedPrincipal) -> BaseConnector:
    if connector.name.lower() == "quickbooks":
        return QuickBooksConnector(credential_store=QuickBooksCredentialStore(principal.organization_id))
    if connector.name.lower() == "outlook":
        return OutlookConnector(credential_store=OutlookCredentialStore(principal.organization_id))
    if connector.name.lower() == "motive":
        return MotiveConnector(organization_id=principal.organization_id)
    return connector


def _connector_health(connector: BaseConnector, principal: AuthenticatedPrincipal) -> ConnectorHealth:
    tenant_connector = _tenant_connector(connector, principal)
    if isinstance(tenant_connector, QuickBooksConnector):
        return _quickbooks_passive_health(tenant_connector)
    return tenant_connector.health()


def _quickbooks_passive_health(connector: QuickBooksConnector) -> ConnectorHealth:
    """Build QuickBooks health from durable credential/sync metadata only.

    Opening Connector Center or System Health must not refresh OAuth or call Intuit.
    Live provider verification remains an explicit operator action through /qbo/verification.
    """
    details = connector.safe_status(include_resources=True)
    authorization = str(details.get("authorization_status") or "authorization_required")
    verification = str(details.get("identity_verification_status") or "authorization_required")
    reauthorization_required = bool(details.get("reauthorization_required"))

    if reauthorization_required:
        connector_status = ConnectorStatus.REAUTHORIZATION_REQUIRED
        message = "QuickBooks reauthorization is required."
    elif authorization != "authorized":
        connector_status = ConnectorStatus.AUTHORIZATION_REQUIRED
        message = "QuickBooks authorization is required."
    elif verification == "company_mismatch":
        connector_status = ConnectorStatus.COMPANY_MISMATCH
        message = "QuickBooks company identity does not match the configured organization."
    elif verification == "healthy":
        connector_status = ConnectorStatus.HEALTHY
        company = details.get("verified_company_name") or "the verified company"
        message = f"Connected to {company}."
    else:
        connector_status = ConnectorStatus.CONNECTED_UNVERIFIED
        message = "QuickBooks is authorized; provider verification has not been confirmed."

    return ConnectorHealth(
        name="quickbooks",
        status=connector_status,
        last_sync_at=_safe_datetime(details.get("last_successful_sync_time")),
        message=message,
        details=details,
    )


def _safe_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


@router.get("", response_model=list[ConnectorHealth])
def list_connectors(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
) -> list[ConnectorHealth]:
    return [_connector_health(connector, principal) for connector in connector_registry.list()]


@router.get("/torqueai/certification")
def certify_torqueai_dispatch_connection(
    certification_date: date = Query(..., alias="date"),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    organization = session.get(Organization, principal.organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"status": "failed", "provider": "torqueai", "error_code": "organization_scope_missing", "secrets_exposed": False})
    connector = TorqueAIConnector(organization_slug=organization.slug)
    try:
        page = connector.fetch_dispatches(date_from=certification_date, date_to=certification_date, page=1, limit=100)
    except TorqueAIConnectorError as exc:
        raise _torqueai_certification_http_error(exc) from exc
    return _torqueai_certification_metadata(page)


@router.post("/torqueai/dispatches/ingest")
def ingest_torqueai_dispatch_window(
    payload: TorqueAIDispatchIngestRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    organization = session.get(Organization, principal.organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"status": "failed", "provider": "torqueai", "error_code": "organization_scope_missing", "secrets_exposed": False})
    try:
        return ingest_torqueai_dispatches(
            session,
            organization_id=organization.id,
            organization_slug=organization.slug,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
    except TorqueAIDispatchIngestionError as exc:
        raise _torqueai_ingestion_http_error(exc) from exc


@router.get("/{name}", response_model=ConnectorHealth)
def get_connector(
    name: str,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
) -> ConnectorHealth:
    try:
        connector = connector_registry.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _connector_health(connector, principal)


@router.post("/{name}/sync", response_model=SyncResult)
def sync_connector(
    name: str,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
) -> SyncResult:
    try:
        connector = connector_registry.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _tenant_connector(connector, principal).sync()


def _torqueai_certification_metadata(page: TorqueAIDispatchPage) -> dict[str, Any]:
    sample = page.data[0] if page.data else None
    field_types = ({str(key): _json_type_name(value) for key, value in sorted(sample.items())} if sample is not None else {})
    return {
        "status": "certified_response_observed",
        "provider": "torqueai",
        "operation": "external_dispatch_page",
        "http_status": 200,
        "request": {"from": page.date_from.isoformat(), "to": page.date_to.isoformat(), "page": 1, "limit": 100},
        "total_count": page.total_count,
        "page": page.page,
        "items_per_page": page.items_per_page,
        "rows_returned": len(page.data),
        "pagination_required": page.page * page.items_per_page < page.total_count,
        "sample_record_field_types": field_types,
        "response_contract_valid": True,
        "tenant_scope_validated": True,
        "raw_dispatches_returned": False,
        "secrets_exposed": False,
    }


def _json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _torqueai_certification_http_error(exc: TorqueAIConnectorError) -> HTTPException:
    if exc.code == "organization_scope_mismatch":
        response_status = status.HTTP_403_FORBIDDEN
    elif exc.code in {"organization_not_configured", "token_missing", "base_url_missing", "invalid_base_url"}:
        response_status = status.HTTP_503_SERVICE_UNAVAILABLE
    elif exc.code == "invalid_request":
        response_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        response_status = status.HTTP_502_BAD_GATEWAY
    return HTTPException(status_code=response_status, detail={"status": "failed", "provider": "torqueai", "error_code": exc.code, "provider_http_status": exc.http_status, "retryable": False, "secrets_exposed": False})


def _torqueai_ingestion_http_error(exc: TorqueAIDispatchIngestionError) -> HTTPException:
    if exc.code == "organization_scope_mismatch":
        response_status = status.HTTP_403_FORBIDDEN
    elif exc.code in {"organization_not_configured", "token_missing", "base_url_missing", "invalid_base_url"}:
        response_status = status.HTTP_503_SERVICE_UNAVAILABLE
    elif exc.code in {"invalid_request", "ingestion_bound_exceeded"}:
        response_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif exc.code == "database_write_failed":
        response_status = status.HTTP_500_INTERNAL_SERVER_ERROR
    else:
        response_status = status.HTTP_502_BAD_GATEWAY
    return HTTPException(status_code=response_status, detail={"status": "failed", "provider": "torqueai", "error_code": exc.code, "provider_http_status": exc.provider_http_status, "retryable": False, "raw_dispatches_returned": False, "secrets_exposed": False})
