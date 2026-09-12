"""Controlled Motive maintenance-memory sync and tenant-scoped read API."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.assignment_intelligence import _db
from app.connectors.motive import MotiveConnector
from app.motive.maintenance_memory import list_maintenance_memory, persist_maintenance_memory
from app.motive.maintenance_readiness import maintenance_readiness_for_trucks
from app.organizations.models import Organization
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/api/v1/motive/maintenance-memory", tags=["motive-maintenance-memory"])


class MaintenanceMemorySyncRequest(BaseModel):
    confirm: bool = False
    truck_numbers: list[str] = Field(min_length=1, max_length=50)
    as_of_date: date | None = None


@router.post("/sync")
def sync_maintenance_memory(
    body: MaintenanceMemorySyncRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    if body.confirm is not True:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="explicit confirmation required")
    trucks = _normalized_trucks(body.truck_numbers)
    if not trucks:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="at least one truck number is required")

    organization = session.get(Organization, principal.organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization not found")

    reference_date = body.as_of_date or datetime.now(timezone.utc).date()
    maintenance = maintenance_readiness_for_trucks(
        truck_numbers=trucks,
        as_of_date=reference_date,
        connector=MotiveConnector(organization_id=principal.organization_id),
    )
    if maintenance.get("inspection_reports_available") is not True:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Motive inspection reports unavailable")
    if maintenance.get("inspection_reports_window_complete") is not True:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Motive inspection result window incomplete")

    persisted = persist_maintenance_memory(
        session=session,
        organization_id=principal.organization_id,
        organization_slug=organization.slug,
        maintenance=maintenance,
    )
    return {
        "status": "ok",
        "as_of_date": maintenance.get("as_of_date"),
        "truck_count_requested": len(trucks),
        **persisted,
        "scope": "inspection_part_lifecycle_memory",
        "fault_code_durable_memory_enabled": False,
        "autonomous_maintenance_action_performed": False,
    }


@router.get("")
def get_maintenance_memory(
    truck_number: str | None = Query(default=None, min_length=1, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    issues = list_maintenance_memory(
        session=session,
        organization_id=principal.organization_id,
        truck_number=truck_number,
        limit=limit,
    )
    return {
        "issues": issues,
        "count": len(issues),
        "durable_maintenance_history_enabled": True,
        "scope": "inspection_part_lifecycle_memory",
        "provider_call_performed": False,
        "provider_write_performed": False,
    }


def _normalized_trucks(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        truck = str(value or "").strip()
        key = truck.casefold()
        if not truck or key in seen:
            continue
        seen.add(key)
        output.append(truck)
    return output
