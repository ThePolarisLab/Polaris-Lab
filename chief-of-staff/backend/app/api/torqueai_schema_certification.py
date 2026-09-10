"""Privacy-safe live TorqueAI nested-schema certification endpoint."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.connectors.torqueai import TorqueAIConnector, TorqueAIConnectorError, TorqueAIDispatchPage
from app.connectors.torqueai_schema import dispatch_schema_paths, json_type_name
from app.database.database import SessionLocal
from app.organizations.models import Organization
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/api/v1/connectors/torqueai", tags=["connectors", "torqueai"])


def _db() -> Session:
    with SessionLocal() as session:
        yield session


@router.get("/schema-certification")
def certify_torqueai_nested_schema(
    certification_date: date = Query(..., alias="date"),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Observe provider key paths/types only; never return provider values."""
    organization = session.get(Organization, principal.organization_id)
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "status": "failed",
                "provider": "torqueai",
                "error_code": "organization_scope_missing",
                "secrets_exposed": False,
            },
        )

    connector = TorqueAIConnector(organization_slug=organization.slug)
    try:
        page = connector.fetch_dispatches(
            date_from=certification_date,
            date_to=certification_date,
            page=1,
            limit=100,
        )
    except TorqueAIConnectorError as exc:
        raise _http_error(exc) from exc

    return _metadata(page)


def _metadata(page: TorqueAIDispatchPage) -> dict[str, Any]:
    sample = page.data[0] if page.data else None
    top_level_types = (
        {str(key): json_type_name(value) for key, value in sorted(sample.items())}
        if sample is not None
        else {}
    )
    return {
        "status": "certified_schema_observed",
        "provider": "torqueai",
        "operation": "external_dispatch_page_schema_only",
        "http_status": 200,
        "request": {
            "from": page.date_from.isoformat(),
            "to": page.date_to.isoformat(),
            "page": 1,
            "limit": 100,
        },
        "total_count": page.total_count,
        "rows_returned": len(page.data),
        "sample_record_field_types": top_level_types,
        "observed_schema_paths": dispatch_schema_paths(page.data),
        "schema_values_returned": False,
        "raw_dispatches_returned": False,
        "tenant_scope_validated": True,
        "secrets_exposed": False,
    }


def _http_error(exc: TorqueAIConnectorError) -> HTTPException:
    if exc.code == "organization_scope_mismatch":
        response_status = status.HTTP_403_FORBIDDEN
    elif exc.code in {"organization_not_configured", "token_missing", "base_url_missing", "invalid_base_url"}:
        response_status = status.HTTP_503_SERVICE_UNAVAILABLE
    elif exc.code == "invalid_request":
        response_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        response_status = status.HTTP_502_BAD_GATEWAY
    return HTTPException(
        status_code=response_status,
        detail={
            "status": "failed",
            "provider": "torqueai",
            "error_code": exc.code,
            "provider_http_status": exc.http_status,
            "retryable": False,
            "raw_dispatches_returned": False,
            "secrets_exposed": False,
        },
    )
