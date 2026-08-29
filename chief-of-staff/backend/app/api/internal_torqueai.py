"""Machine-only TorqueAI scheduled dispatch synchronization trigger."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

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
