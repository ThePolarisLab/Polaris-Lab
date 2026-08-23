"""Read-only Motive fleet KPI API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.motive.vehicle_utilization_kpi import vehicle_utilization_kpi
from app.motive.vehicle_utilization_kpi_history import (
    DEFAULT_HISTORY_DAYS,
    MAX_HISTORY_DAYS,
    vehicle_utilization_kpi_history,
)
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission


router = APIRouter(prefix="/api/v1/motive/fleet", tags=["motive"])


def _db() -> Session:
    with SessionLocal() as session:
        yield session


@router.get("/vehicle-utilization-kpi")
def read_vehicle_utilization_kpi(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Read the first certified Motive business KPI from durable rows only."""
    return vehicle_utilization_kpi(session, principal.organization_id)


@router.get("/vehicle-utilization-kpi/history")
def read_vehicle_utilization_kpi_history(
    days: int = Query(DEFAULT_HISTORY_DAYS, ge=1, le=MAX_HISTORY_DAYS),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, object]:
    """Read bounded aggregate KPI history with zero provider calls and zero writes."""
    return vehicle_utilization_kpi_history(
        session,
        principal.organization_id,
        days=days,
    )
