"""Read-only operational planning views over durable TorqueAI dispatch data."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchStop
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/api/v1/torqueai/planning", tags=["torqueai-planning"])
PICKUP_JOB = "Pick Up"
DELIVERY_JOB = "Drop Off"


def _db() -> Session:
    with SessionLocal() as session:
        yield session


def _normalized_location(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=f"TorqueAI pickup planning {field} must not be blank")
    return normalized


@router.get("/pickups")
def pickup_plan(
    target_date: date = Query(..., alias="date"),
    province: str = Query(..., max_length=120),
    city: str | None = Query(None, max_length=255),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Summarize certified pickups for one date/location from durable data only.

    This endpoint intentionally does not recommend or assign a driver/truck. It
    exposes the evidence needed for a later Motive/HOS-aware decision layer.
    """
    normalized_province = _normalized_location(province, field="province")
    normalized_city = _normalized_location(city, field="city") if city is not None else None

    stop_criteria = [
        TorqueAIDispatchStop.organization_id == principal.organization_id,
        func.lower(TorqueAIDispatchStop.job) == PICKUP_JOB.lower(),
        TorqueAIDispatchStop.scheduled_pickup_date_text == target_date.isoformat(),
        func.lower(TorqueAIDispatchStop.province) == normalized_province.lower(),
    ]
    if normalized_city is not None:
        stop_criteria.append(func.lower(TorqueAIDispatchStop.city) == normalized_city.lower())

    rows = (
        session.query(TorqueAIDispatch)
        .filter(TorqueAIDispatch.organization_id == principal.organization_id)
        .filter(TorqueAIDispatch.operational_stops.any(and_(*stop_criteria)))
        .order_by(TorqueAIDispatch.last_changed_at.desc(), TorqueAIDispatch.id.desc())
        .all()
    )

    planned_loads = [
        _serialize_pickup_plan_row(
            row,
            target_date=target_date,
            province=normalized_province,
            city=normalized_city,
        )
        for row in rows
    ]
    attention_required_count = sum(1 for item in planned_loads if item["attention_flags"])
    unassigned_driver_count = sum(1 for item in planned_loads if "missing_driver" in item["attention_flags"])
    unassigned_truck_count = sum(1 for item in planned_loads if "missing_truck" in item["attention_flags"])

    return {
        "status": "success",
        "provider": "torqueai",
        "source": "durable_database",
        "planning_scope": "pickup_read_only",
        "request": {
            "date": target_date.isoformat(),
            "province": normalized_province,
            "city": normalized_city,
            "role": "pickup",
            "certified_provider_job": PICKUP_JOB,
        },
        "summary": {
            "pickup_load_count": len(planned_loads),
            "attention_required_count": attention_required_count,
            "missing_driver_count": unassigned_driver_count,
            "missing_truck_count": unassigned_truck_count,
        },
        "loads": planned_loads,
        "provider_called": False,
        "autonomous_assignment_performed": False,
        "tenant_scope_validated": True,
        "secrets_exposed": False,
    }


def _serialize_pickup_plan_row(
    row: TorqueAIDispatch,
    *,
    target_date: date,
    province: str,
    city: str | None,
) -> dict[str, Any]:
    matching_pickups = [
        stop
        for stop in row.operational_stops
        if _eq(stop.job, PICKUP_JOB)
        and stop.scheduled_pickup_date_text == target_date.isoformat()
        and _eq(stop.province, province)
        and (city is None or _eq(stop.city, city))
    ]
    matching_pickups.sort(key=lambda stop: (stop.stop_index, stop.id))
    drop_offs = [stop for stop in row.operational_stops if _eq(stop.job, DELIVERY_JOB)]
    drop_offs.sort(key=lambda stop: (stop.stop_index, stop.id))

    attention_flags: list[str] = []
    if not _present(row.driver_name):
        attention_flags.append("missing_driver")
    if not _present(row.truck_number):
        attention_flags.append("missing_truck")
    if not _present(row.trailer_number):
        attention_flags.append("missing_trailer")
    if matching_pickups and not any(_present(stop.scheduled_pickup_time_text) for stop in matching_pickups):
        attention_flags.append("missing_pickup_time")
    if matching_pickups and not any(_present(stop.address) for stop in matching_pickups):
        attention_flags.append("missing_pickup_address")
    if not drop_offs:
        attention_flags.append("missing_drop_off_stop")

    operational = row.operational_enrichment
    return {
        "load_number": row.provider_load_number,
        "order_number": row.provider_order_number,
        "status": row.status,
        "customer_name": row.customer_name,
        "dispatcher_name": row.dispatcher_name,
        "assignment": {
            "driver_name": row.driver_name,
            "truck_number": row.truck_number,
            "trailer_number": row.trailer_number,
        },
        "loaded_miles": float(row.loaded_miles) if row.loaded_miles is not None else None,
        "currency": operational.currency if operational is not None else None,
        "total_charge": float(operational.total_charge) if operational is not None and operational.total_charge is not None else None,
        "pickup_stops": [_serialize_planning_stop(stop) for stop in matching_pickups],
        "drop_off_stops": [_serialize_planning_stop(stop) for stop in drop_offs],
        "attention_flags": attention_flags,
        "last_changed_at": row.last_changed_at.isoformat(),
    }


def _serialize_planning_stop(stop: TorqueAIDispatchStop) -> dict[str, Any]:
    return {
        "index": stop.stop_index,
        "job": stop.job,
        "name": stop.name,
        "address": stop.address,
        "city": stop.city,
        "province": stop.province,
        "country": stop.country,
        "zip_code": stop.zip_code,
        "scheduled": {
            "is_window": stop.scheduled_is_window,
            "date": stop.scheduled_pickup_date_text,
            "date2": stop.scheduled_pickup_date2_text,
            "time": stop.scheduled_pickup_time_text,
            "time2": stop.scheduled_pickup_time2_text,
        },
        "commodity": stop.commodity,
        "temperature": stop.temperature_text,
        "temperature_unit": stop.temperature_unit,
        "weight": float(stop.weight) if stop.weight is not None else None,
        "weight_unit": stop.weight_unit,
    }


def _eq(value: str | None, expected: str) -> bool:
    return bool(value is not None and value.strip().lower() == expected.strip().lower())


def _present(value: str | None) -> bool:
    return bool(value is not None and value.strip())
