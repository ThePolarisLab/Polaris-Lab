"""Machine-only trigger for scheduled BVD PCN price ingestion."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.fuel.scheduler import FuelScheduledImportError, run_scheduled_bvd_pcn_import
from app.security.job_auth import JobAuthenticationError, verify_job_signature

router = APIRouter(prefix="/api/v1/internal/fuel", tags=["internal-fuel"])
FUEL_BVD_TRIGGER_SECRET_ENV_VAR = "POLARIS_FUEL_BVD_CRON_TRIGGER_SECRET"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/bvd/pcn/scheduled-import")
async def run_scheduled_bvd_pcn(
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
            secret_env=FUEL_BVD_TRIGGER_SECRET_ENV_VAR,
        )
    except JobAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="machine authentication failed",
        ) from exc

    if body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scheduled BVD PCN request body must be empty",
        )

    try:
        result = run_scheduled_bvd_pcn_import(db)
    except FuelScheduledImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "failed",
                "error_code": exc.code,
                "secrets_exposed": False,
            },
        ) from exc

    if result["status"] == "failed":
        response.status_code = status.HTTP_502_BAD_GATEWAY
    return result
