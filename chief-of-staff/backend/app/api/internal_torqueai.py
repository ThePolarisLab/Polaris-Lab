"""Machine-only TorqueAI scheduled dispatch synchronization trigger."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.connectors.torqueai import TORQUEAI_API_TOKEN_ENV, TORQUEAI_BASE_URL_ENV
from app.connectors.torqueai_scheduler import (
    TorqueAIScheduledSyncError,
    run_scheduled_torqueai_dispatch_sync,
)
from app.database.database import SessionLocal
from app.security.job_auth import JobAuthenticationError, verify_job_signature

router = APIRouter(prefix="/api/v1/internal/torqueai", tags=["internal-torqueai"])
TORQUEAI_SYNC_TRIGGER_SECRET_ENV_VAR = "POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _torqueai_configuration_diagnostic() -> dict[str, object]:
    """Return configuration-shape booleans without exposing credentials or calling TorqueAI."""
    raw_token = os.getenv(TORQUEAI_API_TOKEN_ENV)
    token = raw_token if isinstance(raw_token, str) else ""
    stripped_token = token.strip()

    raw_base_url = os.getenv(TORQUEAI_BASE_URL_ENV)
    base_url = raw_base_url if isinstance(raw_base_url, str) else ""
    stripped_base_url = base_url.strip().rstrip("/")
    parsed = urlsplit(stripped_base_url) if stripped_base_url else None
    base_url_https_origin = bool(
        parsed
        and parsed.scheme.lower() == "https"
        and parsed.netloc
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and parsed.path in {"", "/"}
    )

    token_has_wrapping_quotes = bool(
        len(stripped_token) >= 2
        and stripped_token[0] == stripped_token[-1]
        and stripped_token[0] in {"'", '"'}
    )

    return {
        "status": "ok",
        "provider": "torqueai",
        "token_configured": bool(stripped_token),
        "token_has_bearer_prefix": stripped_token.casefold().startswith("bearer "),
        "token_has_wrapping_quotes": token_has_wrapping_quotes,
        "token_has_outer_whitespace": bool(token) and token != stripped_token,
        "token_has_line_break": "\n" in token or "\r" in token,
        "base_url_configured": bool(base_url.strip()),
        "base_url_https_origin": base_url_https_origin,
        "provider_called": False,
        "scheduler_called": False,
        "dispatch_claimed": False,
        "raw_dispatches_returned": False,
        "secrets_exposed": False,
    }


@router.post("/config-diagnostic")
async def diagnose_torqueai_configuration(
    request: Request,
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="machine authentication failed",
        ) from exc

    if body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TorqueAI configuration diagnostic request body must be empty",
        )

    return _torqueai_configuration_diagnostic()


@router.post("/dispatches/scheduled-sync")
async def run_scheduled_torqueai_dispatches(
    request: Request,
    response: Response,
    x_polaris_job_timestamp: str | None = Header(default=None, alias="X-Polaris-Job-Timestamp"),
    x_polaris_job_signature: str | None = Header(default=None, alias="X-Polaris-Job-Signature"),
    db: Session = Depends(get_db),
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="machine authentication failed",
        ) from exc

    if body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scheduled TorqueAI dispatch request body must be empty",
        )

    try:
        trigger_timestamp = int(x_polaris_job_timestamp or "")
        result = run_scheduled_torqueai_dispatch_sync(
            db,
            trigger_timestamp=trigger_timestamp,
        ).as_dict()
    except (ValueError, TorqueAIScheduledSyncError) as exc:
        error_code = exc.code if isinstance(exc, TorqueAIScheduledSyncError) else "invalid_trigger_timestamp"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "failed",
                "error_code": error_code,
                "secrets_exposed": False,
            },
        ) from exc

    if result["status"] == "failed":
        response.status_code = status.HTTP_502_BAD_GATEWAY
    return result
