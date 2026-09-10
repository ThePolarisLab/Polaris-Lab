"""Machine-only Motive scheduled and certification endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.motive.assignment_signal_certification import certify_assignment_signal_schema
from app.motive.vehicle_utilization_scheduler import (
    MotiveVehicleUtilizationSchedulerError,
    run_scheduled_vehicle_utilization,
)
from app.security.job_auth import JobAuthenticationError, verify_job_signature

router = APIRouter(prefix="/api/v1/internal/motive", tags=["internal-motive"])
MOTIVE_CRON_SECRET_ENV_VAR = "POLARIS_MOTIVE_UTILIZATION_CRON_TRIGGER_SECRET"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _verify_empty_machine_request(
    *,
    request: Request,
    body: bytes,
    timestamp_header: str | None,
    signature_header: str | None,
    body_error_detail: str,
) -> None:
    try:
        verify_job_signature(
            method=request.method,
            path=request.url.path,
            body=body,
            timestamp=timestamp_header,
            signature=signature_header,
            secret_env=MOTIVE_CRON_SECRET_ENV_VAR,
        )
    except JobAuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="machine authentication failed") from exc
    if body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=body_error_detail)


@router.post("/vehicle-utilization/run")
async def run_scheduled_motive_vehicle_utilization(
    request: Request,
    response: Response,
    x_polaris_job_timestamp: str | None = Header(default=None, alias="X-Polaris-Job-Timestamp"),
    x_polaris_job_signature: str | None = Header(default=None, alias="X-Polaris-Job-Signature"),
    db: Session = Depends(get_db),
):
    body = await request.body()
    _verify_empty_machine_request(
        request=request,
        body=body,
        timestamp_header=x_polaris_job_timestamp,
        signature_header=x_polaris_job_signature,
        body_error_detail="scheduled Motive vehicle-utilization request body must be empty",
    )

    try:
        result = run_scheduled_vehicle_utilization(db).as_dict()
    except MotiveVehicleUtilizationSchedulerError as exc:
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


@router.post("/assignment-signal-certification")
async def certify_motive_assignment_signals(
    request: Request,
    certification_date: date = Query(..., alias="date"),
    x_polaris_job_timestamp: str | None = Header(default=None, alias="X-Polaris-Job-Timestamp"),
    x_polaris_job_signature: str | None = Header(default=None, alias="X-Polaris-Job-Signature"),
    db: Session = Depends(get_db),
):
    """Observe only schema/type structure for HOS and one vehicle-location sample."""
    body = await request.body()
    _verify_empty_machine_request(
        request=request,
        body=body,
        timestamp_header=x_polaris_job_timestamp,
        signature_header=x_polaris_job_signature,
        body_error_detail="Motive assignment-signal certification request body must be empty",
    )
    try:
        return certify_assignment_signal_schema(db, certification_date=certification_date)
    except MotiveVehicleUtilizationSchedulerError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "failed", "error_code": exc.code, "secrets_exposed": False},
        ) from exc
