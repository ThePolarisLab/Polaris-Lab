"""Machine-authenticated, read-only TorqueAI nested schema certification."""

from __future__ import annotations

from datetime import date
import os

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from app.connectors.torqueai import (
    TORQUEAI_ORGANIZATION_SLUG_ENV,
    TorqueAIConnector,
    TorqueAIConnectorError,
)
from app.connectors.torqueai_schema import dispatch_schema_paths
from app.security.job_auth import JobAuthenticationError, verify_job_signature

router = APIRouter(prefix="/api/v1/internal/torqueai", tags=["internal-torqueai"])
TORQUEAI_SYNC_TRIGGER_SECRET_ENV_VAR = "POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET"


@router.post("/schema-certification")
async def certify_torqueai_schema_machine(
    request: Request,
    certification_date: date = Query(..., alias="date"),
    x_polaris_job_timestamp: str | None = Header(default=None, alias="X-Polaris-Job-Timestamp"),
    x_polaris_job_signature: str | None = Header(default=None, alias="X-Polaris-Job-Signature"),
):
    body = await request.body()
    try:
        verify_job_signature(
            method=request.method,
            path=request.url.path,
            body=body,
            timestamp=x_polaris_job_timestamp,
            signature=x_polaris_job_signature,
            secret_env=TORQUEAI_SYNC_TRIGGER_SECRET_ENV_VAR,
        )
    except JobAuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="machine authentication failed") from exc

    if body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="TorqueAI schema certification body must be empty")

    organization_slug = str(os.getenv(TORQUEAI_ORGANIZATION_SLUG_ENV) or "").strip()

    try:
        connector = TorqueAIConnector(organization_slug=organization_slug)
        page = connector.fetch_dispatches(
            date_from=certification_date,
            date_to=certification_date,
            page=1,
            limit=100,
        )
    except TorqueAIConnectorError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "status": "failed",
                "provider": "torqueai",
                "error_code": exc.code,
                "provider_http_status": exc.http_status,
                "raw_dispatches_returned": False,
                "secrets_exposed": False,
            },
        ) from exc

    return {
        "status": "certified_response_observed",
        "provider": "torqueai",
        "operation": "external_dispatch_nested_schema",
        "request": {
            "from": certification_date.isoformat(),
            "to": certification_date.isoformat(),
            "page": 1,
            "limit": 100,
        },
        "rows_returned": len(page.data),
        "total_count": page.total_count,
        "observed_schema_paths": dispatch_schema_paths(page.data),
        "schema_values_returned": False,
        "raw_dispatches_returned": False,
        "secrets_exposed": False,
    }
