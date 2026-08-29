"""Read-only tenant-scoped access to durable TorqueAI dispatch records."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.torqueai import TorqueAIDispatch
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/api/v1/torqueai", tags=["torqueai"])

TORQUEAI_READ_DEFAULT_LIMIT = 50
TORQUEAI_READ_MAX_LIMIT = 100
TORQUEAI_READ_MAX_RANGE_DAYS = 31


def _db() -> Session:
    with SessionLocal() as session:
        yield session


@router.get("/dispatches")
def list_durable_torqueai_dispatches(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    dispatch_status: str | None = Query(None, alias="status", max_length=120),
    customer: str | None = Query(None, max_length=255),
    dispatcher: str | None = Query(None, max_length=255),
    page: int = Query(1, ge=1),
    limit: int = Query(TORQUEAI_READ_DEFAULT_LIMIT, ge=1, le=TORQUEAI_READ_MAX_LIMIT),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Return minimized durable dispatch rows without contacting TorqueAI."""
    _validate_date_window(date_from, date_to)
    status_value = _normalized_filter(dispatch_status, "status")
    customer_value = _normalized_filter(customer, "customer")
    dispatcher_value = _normalized_filter(dispatcher, "dispatcher")

    query = session.query(TorqueAIDispatch).filter(
        TorqueAIDispatch.organization_id == principal.organization_id
    )

    if date_from is not None and date_to is not None:
        start_text = date_from.isoformat()
        end_exclusive_text = (date_to + timedelta(days=1)).isoformat()
        query = query.filter(
            TorqueAIDispatch.ship_date_text.is_not(None),
            TorqueAIDispatch.ship_date_text >= start_text,
            TorqueAIDispatch.ship_date_text < end_exclusive_text,
        )
    if status_value is not None:
        query = query.filter(func.lower(TorqueAIDispatch.status) == status_value.lower())
    if customer_value is not None:
        query = query.filter(func.lower(TorqueAIDispatch.customer_name) == customer_value.lower())
    if dispatcher_value is not None:
        query = query.filter(func.lower(TorqueAIDispatch.dispatcher_name) == dispatcher_value.lower())

    total_count = query.count()
    rows = (
        query.order_by(TorqueAIDispatch.last_changed_at.desc(), TorqueAIDispatch.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return {
        "status": "success",
        "provider": "torqueai",
        "source": "durable_database",
        "request": {
            "from": date_from.isoformat() if date_from is not None else None,
            "to": date_to.isoformat() if date_to is not None else None,
            "status": status_value,
            "customer": customer_value,
            "dispatcher": dispatcher_value,
            "page": page,
            "limit": limit,
        },
        "total_count": total_count,
        "page": page,
        "limit": limit,
        "rows_returned": len(rows),
        "has_more": page * limit < total_count,
        "data": [_serialize_dispatch(row) for row in rows],
        "provider_called": False,
        "tenant_scope_validated": True,
        "secrets_exposed": False,
    }


def _validate_date_window(date_from: date | None, date_to: date | None) -> None:
    if (date_from is None) != (date_to is None):
        raise HTTPException(status_code=422, detail="TorqueAI durable read requires both from and to when filtering by date")
    if date_from is None or date_to is None:
        return
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="TorqueAI durable read from date must not be after to date")
    if (date_to - date_from).days + 1 > TORQUEAI_READ_MAX_RANGE_DAYS:
        raise HTTPException(status_code=422, detail="TorqueAI durable read range must not exceed 31 days")


def _normalized_filter(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail=f"TorqueAI durable read {name} filter must not be blank")
    return normalized


def _serialize_dispatch(row: TorqueAIDispatch) -> dict[str, Any]:
    return {
        "load_number": row.provider_load_number,
        "order_number": row.provider_order_number,
        "status": row.status,
        "order_date": row.order_date_text,
        "ship_date": row.ship_date_text,
        "delivery_date": row.delivery_date_text,
        "customer_name": row.customer_name,
        "dispatcher_name": row.dispatcher_name,
        "driver_name": row.driver_name,
        "carrier_name": row.carrier_name,
        "truck_number": row.truck_number,
        "trailer_number": row.trailer_number,
        "loaded_miles": float(row.loaded_miles) if row.loaded_miles is not None else None,
        "first_observed_at": row.first_observed_at.isoformat(),
        "last_changed_at": row.last_changed_at.isoformat(),
    }
