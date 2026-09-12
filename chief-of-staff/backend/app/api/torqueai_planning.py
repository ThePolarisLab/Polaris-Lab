"""Read-only operational planning views over durable TorqueAI dispatch data."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission
from app.services.pickup_planning import query_pickup_plan

router = APIRouter(prefix="/api/v1/torqueai/planning", tags=["torqueai-planning"])


def _db() -> Session:
    with SessionLocal() as session:
        yield session


@router.get("/pickups")
def pickup_plan(
    target_date: date = Query(..., alias="date"),
    province: str = Query(..., max_length=120),
    city: str | None = Query(None, max_length=255),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Summarize certified pickups for one date/location from durable data only."""
    return query_pickup_plan(
        target_date=target_date, province=province, city=city,
        principal=principal, session=session,
    )
