"""Manual, default-off production Motive vehicle-utilization ingestion route."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.motive.vehicle_utilization_production_ingestion import (
    PRODUCTION_HORIZON_DAYS,
    PRODUCTION_INGESTION_ENABLED_ENV_VAR,
    PRODUCTION_MAX_PROVIDER_CALLS,
    PRODUCTION_TIME_ZONE,
    RESOURCE,
    MotiveVehicleUtilizationProductionIngestionError,
    production_ingestion_enabled,
    run_vehicle_utilization_production_ingestion,
)
from app.organizations.models import Organization
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/motive", tags=["motive"])


class VehicleUtilizationProductionIngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: bool = False


def _db() -> Session:
    with SessionLocal() as session:
        yield session


def _organization(session: Session, organization_id: str) -> Organization:
    organization = session.query(Organization).filter(Organization.id == organization_id).one_or_none()
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_base_failure("organization_not_found", "Organization was not found."),
        )
    return organization


def _base_failure(error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "resource": RESOURCE,
        "run_mode": "production_recent_window_ingestion",
        "error_code": error_code,
        "message": message,
        "horizon_days": PRODUCTION_HORIZON_DAYS,
        "request_timezone": PRODUCTION_TIME_ZONE,
        "provider_calls_attempted": 0,
        "provider_calls_completed": 0,
        "checkpoint_advanced": False,
        "sync_history_written": False,
        "scheduled_ingestion_enabled": False,
        "secrets_exposed": False,
    }


def _error_status(exc: MotiveVehicleUtilizationProductionIngestionError) -> int:
    if exc.code == "production_ingestion_disabled":
        return status.HTTP_503_SERVICE_UNAVAILABLE
    if exc.code in {"production_vehicle_limit_exceeded", "production_run_already_in_progress"}:
        return status.HTTP_409_CONFLICT
    if exc.code in {"no_eligible_vehicles", "invalid_stored_vehicle_identity", "duplicate_stored_vehicle_identity"}:
        return status.HTTP_409_CONFLICT
    return status.HTTP_500_INTERNAL_SERVER_ERROR


@router.post("/sync/vehicle-utilization")
def sync_motive_vehicle_utilization_production(
    response: Response,
    body: VehicleUtilizationProductionIngestionRequest = VehicleUtilizationProductionIngestionRequest(),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Run exactly one bounded manual production-ingestion attempt.

    The caller cannot choose dates, timezone, units, horizon, vehicles,
    pagination, retries, or organization. No scheduler is wired to this route.
    """
    if not production_ingestion_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_base_failure(
                "production_ingestion_disabled",
                "Motive vehicle-utilization production ingestion is disabled.",
            ),
        )
    if body.confirm is not True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_base_failure(
                "confirmation_required",
                "Motive vehicle-utilization production ingestion requires an explicit confirm: true request body.",
            ),
        )

    organization = _organization(session, principal.organization_id)
    try:
        result = run_vehicle_utilization_production_ingestion(
            session,
            organization_id=principal.organization_id,
            organization_slug=organization.slug,
        ).as_dict()
    except MotiveVehicleUtilizationProductionIngestionError as exc:
        logger.info(
            "MOTIVE VEHICLE UTILIZATION PRODUCTION INGESTION REJECTED",
            extra={
                "motive_operation": "production_recent_window_ingestion",
                "organization_id": principal.organization_id,
                "error_code": exc.code,
                "feature_flag": PRODUCTION_INGESTION_ENABLED_ENV_VAR,
                "max_provider_calls": PRODUCTION_MAX_PROVIDER_CALLS,
            },
        )
        raise HTTPException(status_code=_error_status(exc), detail=_base_failure(exc.code, str(exc))) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "MOTIVE VEHICLE UTILIZATION PRODUCTION INGESTION ROUTE UNEXPECTED FAILURE",
            extra={
                "motive_operation": "production_recent_window_ingestion",
                "organization_id": principal.organization_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_base_failure(
                "unexpected_error",
                "Motive vehicle-utilization production ingestion failed unexpectedly.",
            ),
        ) from exc

    if result["status"] == "partial_success":
        response.status_code = status.HTTP_207_MULTI_STATUS
        return result
    if result["status"] == "failed":
        failed_units = result.get("failed_units") or []
        detail = dict(result)
        detail["error_code"] = failed_units[0]["error_code"] if failed_units else "production_ingestion_failed"
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
    return result
