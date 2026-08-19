"""Controlled seven-day Motive vehicle-utilization validation API.

This router is deliberately separate from the normal Motive sync surface. It
adds no scheduler, checkpoint, sync-history, migration, or Render enablement.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.motive.vehicle_utilization_recent_reconciliation import (
    MotiveVehicleUtilizationRecentReconciliationError,
    recent_reconciliation_enabled,
)
from app.motive.vehicle_utilization_seven_day_reconciliation_validation import (
    RESOURCE,
    SEVEN_DAY_RECONCILIATION_VALIDATION_ENABLED_ENV_VAR,
    SEVEN_DAY_RECONCILIATION_VALIDATION_HORIZON_DAYS,
    SEVEN_DAY_RECONCILIATION_VALIDATION_MAX_PROVIDER_CALLS,
    MotiveVehicleUtilizationSevenDayReconciliationValidationError,
    run_seven_day_vehicle_utilization_reconciliation_live_validation,
    seven_day_reconciliation_validation_enabled,
)
from app.organizations.models import Organization
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/motive", tags=["motive"])


class VehicleUtilizationSevenDayReconciliationValidationRequest(BaseModel):
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
            detail={
                "status": "failed",
                "resource": RESOURCE,
                "error_code": "organization_not_found",
                "message": "Organization was not found.",
                "secrets_exposed": False,
            },
        )
    return organization


def _base_failure(error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "resource": RESOURCE,
        "error_code": error_code,
        "message": message,
        "horizon_days": SEVEN_DAY_RECONCILIATION_VALIDATION_HORIZON_DAYS,
        "provider_calls_attempted": 0,
        "provider_calls_completed": 0,
        "checkpoint_advanced": False,
        "sync_history_written": False,
        "scheduled_ingestion_enabled": False,
        "secrets_exposed": False,
    }


def _validation_error_status(exc: MotiveVehicleUtilizationSevenDayReconciliationValidationError) -> int:
    if exc.code in ("recent_reconciliation_disabled", "seven_day_reconciliation_validation_disabled"):
        return status.HTTP_503_SERVICE_UNAVAILABLE
    if exc.code == "seven_day_validation_vehicle_limit_exceeded":
        return status.HTTP_409_CONFLICT
    return status.HTTP_500_INTERNAL_SERVER_ERROR


@router.post("/verify/vehicle-utilization-recent-reconciliation-seven-day")
def verify_motive_vehicle_utilization_recent_reconciliation_seven_day(
    response: Response,
    body: VehicleUtilizationSevenDayReconciliationValidationRequest = VehicleUtilizationSevenDayReconciliationValidationRequest(),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Run one separately gated, exactly-seven-day staging validation.

    The caller cannot choose dates, horizon, vehicles, batching, pagination,
    retry behavior, or organization. The route requires the authenticated
    tenant, CONNECTOR_WRITE, both feature gates, and explicit confirm=true.
    """
    if not recent_reconciliation_enabled() or not seven_day_reconciliation_validation_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_base_failure(
                "seven_day_reconciliation_validation_disabled",
                "Seven-day Motive utilization reconciliation validation is disabled; both the runner gate and the dedicated seven-day gate must be enabled.",
            ),
        )
    if body.confirm is not True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_base_failure(
                "confirmation_required",
                "Seven-day Motive utilization reconciliation validation requires an explicit confirm: true request body.",
            ),
        )

    organization = _organization(session, principal.organization_id)
    try:
        result = run_seven_day_vehicle_utilization_reconciliation_live_validation(
            session,
            organization_id=principal.organization_id,
            organization_slug=organization.slug,
        )
    except MotiveVehicleUtilizationSevenDayReconciliationValidationError as exc:
        detail = _base_failure(exc.code, str(exc))
        detail.update(exc.sanitized_context)
        raise HTTPException(status_code=_validation_error_status(exc), detail=detail) from exc
    except MotiveVehicleUtilizationRecentReconciliationError as exc:
        http_status = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if exc.code == "recent_reconciliation_disabled"
            else status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        raise HTTPException(status_code=http_status, detail=_base_failure(exc.code, str(exc))) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "MOTIVE VEHICLE UTILIZATION SEVEN DAY RECONCILIATION LIVE VALIDATION UNEXPECTED FAILURE",
            extra={
                "motive_operation": "vehicle_utilization_seven_day_reconciliation_live_validation",
                "organization_id": principal.organization_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_base_failure(
                "unexpected_error",
                "Seven-day Motive utilization reconciliation validation failed unexpectedly.",
            ),
        ) from exc

    if result["status"] == "partial_success":
        response.status_code = status.HTTP_207_MULTI_STATUS
        return result
    if result["status"] == "failed":
        failed_units = result.get("failed_units") or []
        detail = dict(result)
        detail["error_code"] = (
            failed_units[0]["error_code"] if failed_units else "recent_reconciliation_operational_failure"
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)

    logger.info(
        "MOTIVE VEHICLE UTILIZATION SEVEN DAY RECONCILIATION LIVE VALIDATION SUCCESS",
        extra={
            "motive_operation": "vehicle_utilization_seven_day_reconciliation_live_validation",
            "organization_id": principal.organization_id,
            "provider_calls_attempted": result.get("provider_calls_attempted"),
            "provider_calls_completed": result.get("provider_calls_completed"),
            "status": result.get("status"),
            "seven_day_feature_flag": SEVEN_DAY_RECONCILIATION_VALIDATION_ENABLED_ENV_VAR,
            "max_provider_calls": SEVEN_DAY_RECONCILIATION_VALIDATION_MAX_PROVIDER_CALLS,
        },
    )
    return result
