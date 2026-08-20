"""Disabled-by-default scheduled Motive vehicle-utilization trigger service.

This module is only a scheduler wrapper around the already-certified production
vehicle-utilization orchestrator. It never selects dates, vehicles, units,
pagination, retries, or provider credentials itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.motive import MotiveSyncCheckpoint
from app.motive.vehicle_utilization_production_ingestion import (
    PRODUCTION_TIME_ZONE,
    MotiveVehicleUtilizationProductionIngestionError,
    production_ingestion_enabled,
    production_scheduler_enabled,
    run_vehicle_utilization_production_ingestion,
)
from app.organizations.models import Organization, OrganizationStatus

SCHEDULED_ORGANIZATION_ENV_VAR = "POLARIS_MOTIVE_UTILIZATION_SCHEDULED_ORGANIZATION_SLUG"
CONTROLLED_VALIDATION_WINDOW_ENABLED_ENV_VAR = (
    "MOTIVE_VEHICLE_UTILIZATION_SCHEDULER_CONTROLLED_VALIDATION_WINDOW_ENABLED"
)
SCHEDULER_DISPATCH_RESOURCE = "vehicle_utilization_scheduler_dispatch"
SCHEDULER_MODE = "scheduled_production_ingestion"
SCHEDULE_HOUR = 6
SCHEDULE_MINUTE_MIN = 10
SCHEDULE_MINUTE_MAX = 24
CONTROLLED_VALIDATION_START_HOUR = 11
CONTROLLED_VALIDATION_END_HOUR = 23


class MotiveVehicleUtilizationSchedulerError(RuntimeError):
    """Sanitized scheduler configuration or persistence failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ScheduledVehicleUtilizationResult:
    status: str
    scheduler_mode: str
    request_timezone: str
    local_schedule_date: str
    dispatch_claimed: bool
    scheduler_enabled: bool
    production_result: dict[str, object] | None = None
    error_code: str | None = None
    secrets_exposed: bool = False

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status,
            "scheduler_mode": self.scheduler_mode,
            "request_timezone": self.request_timezone,
            "local_schedule_date": self.local_schedule_date,
            "dispatch_claimed": self.dispatch_claimed,
            "scheduler_enabled": self.scheduler_enabled,
            "secrets_exposed": False,
        }
        if self.production_result is not None:
            payload["production_result"] = self.production_result
        if self.error_code is not None:
            payload["error_code"] = self.error_code
        return payload


def resolve_scheduled_organization(session: Session) -> Organization:
    slug = str(os.getenv(SCHEDULED_ORGANIZATION_ENV_VAR) or "").strip()
    if not slug:
        raise MotiveVehicleUtilizationSchedulerError(
            "missing_organization_configuration",
            "Motive vehicle-utilization scheduled organization is not configured.",
        )
    organization = (
        session.query(Organization)
        .filter(Organization.slug == slug, Organization.status == OrganizationStatus.ACTIVE.value)
        .one_or_none()
    )
    if organization is None:
        raise MotiveVehicleUtilizationSchedulerError(
            "organization_not_found",
            "Motive vehicle-utilization scheduled organization was not found.",
        )
    return organization


def scheduler_local_now(*, now: datetime | None = None) -> datetime:
    zone = ZoneInfo(PRODUCTION_TIME_ZONE)
    if now is None:
        return datetime.now(zone)
    if now.tzinfo is None:
        raise MotiveVehicleUtilizationSchedulerError(
            "invalid_scheduler_time",
            "Scheduler time must be timezone-aware.",
        )
    return now.astimezone(zone)


def controlled_validation_window_enabled() -> bool:
    return str(os.getenv(CONTROLLED_VALIDATION_WINDOW_ENABLED_ENV_VAR) or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def inside_schedule_window(*, now: datetime | None = None) -> bool:
    local_now = scheduler_local_now(now=now)
    if controlled_validation_window_enabled():
        return CONTROLLED_VALIDATION_START_HOUR <= local_now.hour <= CONTROLLED_VALIDATION_END_HOUR
    return (
        local_now.hour == SCHEDULE_HOUR
        and SCHEDULE_MINUTE_MIN <= local_now.minute <= SCHEDULE_MINUTE_MAX
    )


def _claim_dispatch_date(
    session: Session,
    *,
    organization_id: str,
    organization_slug: str,
    local_schedule_date: str,
) -> bool:
    """Atomically consume one scheduled dispatch per organization/local date."""
    try:
        row = (
            session.query(MotiveSyncCheckpoint)
            .filter(
                MotiveSyncCheckpoint.organization_id == organization_id,
                MotiveSyncCheckpoint.provider_resource == SCHEDULER_DISPATCH_RESOURCE,
            )
            .with_for_update()
            .one_or_none()
        )
        if row is not None:
            position = row.last_successful_position if isinstance(row.last_successful_position, dict) else {}
            if position.get("claimed_local_date") == local_schedule_date:
                session.rollback()
                return False
            row.organization_slug = organization_slug
            row.provider = "motive"
            row.cursor = None
            row.page_number = None
            row.updated_after_watermark = local_schedule_date
            row.last_successful_position = {
                "claimed_local_date": local_schedule_date,
                "request_timezone": PRODUCTION_TIME_ZONE,
                "scheduler_mode": SCHEDULER_MODE,
            }
            row.checkpoint_status = "claimed"
            row.last_successful_sync_at = scheduler_local_now().astimezone(ZoneInfo("UTC"))
            session.commit()
            return True

        session.add(
            MotiveSyncCheckpoint(
                organization_id=organization_id,
                organization_slug=organization_slug,
                provider="motive",
                provider_resource=SCHEDULER_DISPATCH_RESOURCE,
                cursor=None,
                page_number=None,
                updated_after_watermark=local_schedule_date,
                last_successful_position={
                    "claimed_local_date": local_schedule_date,
                    "request_timezone": PRODUCTION_TIME_ZONE,
                    "scheduler_mode": SCHEDULER_MODE,
                },
                checkpoint_status="claimed",
                last_successful_sync_at=scheduler_local_now().astimezone(ZoneInfo("UTC")),
            )
        )
        session.commit()
        return True
    except IntegrityError:
        session.rollback()
        row = (
            session.query(MotiveSyncCheckpoint)
            .filter(
                MotiveSyncCheckpoint.organization_id == organization_id,
                MotiveSyncCheckpoint.provider_resource == SCHEDULER_DISPATCH_RESOURCE,
            )
            .one_or_none()
        )
        if row is not None:
            position = row.last_successful_position if isinstance(row.last_successful_position, dict) else {}
            if position.get("claimed_local_date") == local_schedule_date:
                return False
        raise MotiveVehicleUtilizationSchedulerError(
            "scheduler_dispatch_claim_failed",
            "Motive vehicle-utilization scheduler dispatch could not be claimed safely.",
        )
    except SQLAlchemyError as exc:
        session.rollback()
        raise MotiveVehicleUtilizationSchedulerError(
            "scheduler_dispatch_claim_failed",
            "Motive vehicle-utilization scheduler dispatch could not be claimed safely.",
        ) from exc


def run_scheduled_vehicle_utilization(
    session: Session,
    *,
    now: datetime | None = None,
) -> ScheduledVehicleUtilizationResult:
    """Run one scheduler-path attempt with zero retry behavior."""
    local_now = scheduler_local_now(now=now)
    local_date = local_now.date().isoformat()

    if not production_scheduler_enabled():
        return ScheduledVehicleUtilizationResult(
            status="disabled",
            scheduler_mode=SCHEDULER_MODE,
            request_timezone=PRODUCTION_TIME_ZONE,
            local_schedule_date=local_date,
            dispatch_claimed=False,
            scheduler_enabled=False,
            error_code="scheduler_disabled",
        )
    if not production_ingestion_enabled():
        return ScheduledVehicleUtilizationResult(
            status="disabled",
            scheduler_mode=SCHEDULER_MODE,
            request_timezone=PRODUCTION_TIME_ZONE,
            local_schedule_date=local_date,
            dispatch_claimed=False,
            scheduler_enabled=True,
            error_code="production_ingestion_disabled",
        )
    if not inside_schedule_window(now=local_now):
        return ScheduledVehicleUtilizationResult(
            status="outside_window",
            scheduler_mode=SCHEDULER_MODE,
            request_timezone=PRODUCTION_TIME_ZONE,
            local_schedule_date=local_date,
            dispatch_claimed=False,
            scheduler_enabled=True,
        )

    organization = resolve_scheduled_organization(session)
    claimed = _claim_dispatch_date(
        session,
        organization_id=organization.id,
        organization_slug=organization.slug,
        local_schedule_date=local_date,
    )
    if not claimed:
        return ScheduledVehicleUtilizationResult(
            status="already_claimed",
            scheduler_mode=SCHEDULER_MODE,
            request_timezone=PRODUCTION_TIME_ZONE,
            local_schedule_date=local_date,
            dispatch_claimed=False,
            scheduler_enabled=True,
        )

    try:
        production_result = run_vehicle_utilization_production_ingestion(
            session,
            organization_id=organization.id,
            organization_slug=organization.slug,
        ).as_dict()
    except MotiveVehicleUtilizationProductionIngestionError as exc:
        return ScheduledVehicleUtilizationResult(
            status="failed",
            scheduler_mode=SCHEDULER_MODE,
            request_timezone=PRODUCTION_TIME_ZONE,
            local_schedule_date=local_date,
            dispatch_claimed=True,
            scheduler_enabled=True,
            error_code=exc.code,
        )

    return ScheduledVehicleUtilizationResult(
        status="executed",
        scheduler_mode=SCHEDULER_MODE,
        request_timezone=PRODUCTION_TIME_ZONE,
        local_schedule_date=local_date,
        dispatch_claimed=True,
        scheduler_enabled=True,
        production_result=production_result,
    )
