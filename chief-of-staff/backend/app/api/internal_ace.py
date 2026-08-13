"""Machine-only ACE scheduled feed trigger."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.ace.feed_runner import AceFeedConfigurationError, resolve_configured_organization, run_ace_daily_import
from app.database.database import SessionLocal
from app.security.job_auth import JobAuthenticationError, verify_job_signature

router = APIRouter(prefix="/api/v1/internal/ace", tags=["internal-ace"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/daily-feed/run")
async def run_scheduled_ace_daily_feed(
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
        )
    except JobAuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="machine authentication failed") from exc

    try:
        organization = resolve_configured_organization(db)
    except AceFeedConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    result = run_ace_daily_import(db, organization.id, mode="scheduled")
    if result.exit_code != 0:
        response.status_code = status.HTTP_502_BAD_GATEWAY
    return {
        "status": result.status,
        "source_found": result.source_found,
        "replayed": result.replayed,
        "records_read": result.records_read,
        "records_inserted": result.records_inserted,
        "records_updated": result.records_updated,
        "exceptions_created": result.exceptions_created,
        "secrets_exposed": False,
    }
