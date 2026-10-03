"""Read-only tenant-scoped access to durable TorqueAI dispatch records."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchOperational, TorqueAIDispatchStop, TorqueAIDispatchSyncRun, TorqueAIDispatchSyncState
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/api/v1/torqueai", tags=["torqueai"])
TORQUEAI_READ_DEFAULT_LIMIT = 50
TORQUEAI_READ_MAX_LIMIT = 100
TORQUEAI_READ_MAX_RANGE_DAYS = 31
TORQUEAI_CERTIFIED_STOP_ROLE_JOBS = {
    "pickup": "Pick Up",
    "delivery": "Drop Off",
}


def _db() -> Session:
    with SessionLocal() as session:
        yield session


@router.get("/status")
def durable_torqueai_status(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    organization_id = principal.organization_id
    latest_run = session.query(TorqueAIDispatchSyncRun).filter(TorqueAIDispatchSyncRun.organization_id == organization_id).order_by(TorqueAIDispatchSyncRun.started_at.desc(), TorqueAIDispatchSyncRun.id.desc()).first()
    sync_state = session.query(TorqueAIDispatchSyncState).filter(TorqueAIDispatchSyncState.organization_id == organization_id).one_or_none()
    records_stored = session.query(TorqueAIDispatch).filter(TorqueAIDispatch.organization_id == organization_id).count()
    health_status, message = _torqueai_health_presentation(latest_run, sync_state)
    return {
        "health": {"status": health_status, "message": message},
        "status": {
            "connection_status": health_status,
            "records_stored": records_stored,
            "latest_run_status": latest_run.status if latest_run is not None else None,
            "latest_run_trigger_mode": latest_run.trigger_mode if latest_run is not None else None,
            "latest_run_trigger_slot": latest_run.trigger_slot if latest_run is not None else None,
            "latest_run_started_at": latest_run.started_at.isoformat() if latest_run is not None else None,
            "latest_run_completed_at": latest_run.completed_at.isoformat() if latest_run is not None and latest_run.completed_at else None,
            "latest_run_error_code": latest_run.error_code if latest_run is not None else None,
            "last_successful_window_start": sync_state.last_successful_window_start.isoformat() if sync_state is not None else None,
            "last_successful_window_end": sync_state.last_successful_window_end.isoformat() if sync_state is not None else None,
            "last_successful_completed_at": sync_state.last_successful_completed_at.isoformat() if sync_state is not None else None,
            "last_successful_run_id": sync_state.last_successful_run_id if sync_state is not None else None,
            "read_only": True,
            "provider_called": False,
            "tenant_scope_validated": True,
            "secrets_exposed": False,
        },
    }


@router.get("/dispatches")
def list_durable_torqueai_dispatches(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    dispatch_status: str | None = Query(None, alias="status", max_length=120),
    customer: str | None = Query(None, max_length=255),
    dispatcher: str | None = Query(None, max_length=255),
    driver: str | None = Query(None, max_length=255),
    truck: str | None = Query(None, max_length=120),
    carrier: str | None = Query(None, max_length=255),
    trailer: str | None = Query(None, max_length=120),
    currency: str | None = Query(None, max_length=12),
    stop_job: str | None = Query(None, max_length=120),
    stop_role: str | None = Query(None, max_length=20),
    stop_date: date | None = Query(None),
    stop_city: str | None = Query(None, max_length=255),
    stop_province: str | None = Query(None, max_length=120),
    stop_country: str | None = Query(None, max_length=120),
    page: int = Query(1, ge=1),
    limit: int = Query(TORQUEAI_READ_DEFAULT_LIMIT, ge=1, le=TORQUEAI_READ_MAX_LIMIT),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Return normalized durable dispatches and certified stops without provider access."""
    _validate_date_window(date_from, date_to)
    normalized_stop_role = _normalized_stop_role(stop_role)
    normalized_stop_job = _normalized_filter(stop_job, "stop_job")
    if normalized_stop_role is not None and normalized_stop_job is not None:
        raise HTTPException(status_code=422, detail="TorqueAI durable read accepts stop_role or stop_job, not both")

    filters = {
        "status": _normalized_filter(dispatch_status, "status"),
        "customer": _normalized_filter(customer, "customer"),
        "dispatcher": _normalized_filter(dispatcher, "dispatcher"),
        "driver": _normalized_filter(driver, "driver"),
        "truck": _normalized_filter(truck, "truck"),
        "carrier": _normalized_filter(carrier, "carrier"),
        "trailer": _normalized_filter(trailer, "trailer"),
        "currency": _normalized_filter(currency, "currency"),
        "stop_job": normalized_stop_job,
        "stop_role": normalized_stop_role,
        "stop_date": stop_date.isoformat() if stop_date is not None else None,
        "stop_city": _normalized_filter(stop_city, "stop_city"),
        "stop_province": _normalized_filter(stop_province, "stop_province"),
        "stop_country": _normalized_filter(stop_country, "stop_country"),
    }

    query = session.query(TorqueAIDispatch).outerjoin(
        TorqueAIDispatchOperational,
        (TorqueAIDispatchOperational.dispatch_id == TorqueAIDispatch.id) & (TorqueAIDispatchOperational.organization_id == principal.organization_id),
    ).filter(TorqueAIDispatch.organization_id == principal.organization_id)

    if date_from is not None and date_to is not None:
        query = query.filter(
            TorqueAIDispatch.ship_date_text.is_not(None),
            TorqueAIDispatch.ship_date_text >= date_from.isoformat(),
            TorqueAIDispatch.ship_date_text < (date_to + timedelta(days=1)).isoformat(),
        )
    field_map = {
        "status": TorqueAIDispatch.status,
        "customer": TorqueAIDispatch.customer_name,
        "dispatcher": TorqueAIDispatch.dispatcher_name,
        "driver": TorqueAIDispatch.driver_name,
        "truck": TorqueAIDispatch.truck_number,
        "carrier": TorqueAIDispatch.carrier_name,
        "trailer": TorqueAIDispatch.trailer_number,
        "currency": TorqueAIDispatchOperational.currency,
    }
    for name, column in field_map.items():
        if filters[name] is not None:
            query = query.filter(func.lower(column) == filters[name].lower())

    stop_criteria = [TorqueAIDispatchStop.organization_id == principal.organization_id]
    stop_map = {
        "stop_job": TorqueAIDispatchStop.job,
        "stop_city": TorqueAIDispatchStop.city,
        "stop_province": TorqueAIDispatchStop.province,
        "stop_country": TorqueAIDispatchStop.country,
    }
    has_stop_filter = False
    for name, column in stop_map.items():
        if filters[name] is not None:
            has_stop_filter = True
            stop_criteria.append(func.lower(column) == filters[name].lower())
    if filters["stop_role"] is not None:
        has_stop_filter = True
        certified_job = TORQUEAI_CERTIFIED_STOP_ROLE_JOBS[filters["stop_role"]]
        stop_criteria.append(func.lower(TorqueAIDispatchStop.job) == certified_job.lower())
    if filters["stop_date"] is not None:
        has_stop_filter = True
        stop_criteria.append(TorqueAIDispatchStop.scheduled_pickup_date_text == filters["stop_date"])
    if has_stop_filter:
        query = query.filter(TorqueAIDispatch.operational_stops.any(and_(*stop_criteria)))

    total_count = query.count()
    rows = query.order_by(TorqueAIDispatch.last_changed_at.desc(), TorqueAIDispatch.id.desc()).offset((page - 1) * limit).limit(limit).all()
    return {
        "status": "success",
        "provider": "torqueai",
        "source": "durable_database",
        "request": {
            "from": date_from.isoformat() if date_from is not None else None,
            "to": date_to.isoformat() if date_to is not None else None,
            **filters,
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



@router.get("/analytics/lane")
def torqueai_lane_analytics(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    customer: str | None = Query(None, max_length=255),
    pickup_city: str | None = Query(None, max_length=255),
    pickup_province: str | None = Query(None, max_length=120),
    pickup_country: str | None = Query(None, max_length=120),
    delivery_city: str | None = Query(None, max_length=255),
    delivery_province: str | None = Query(None, max_length=120),
    delivery_country: str | None = Query(None, max_length=120),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Aggregate durable TorqueAI revenue and loaded-mile evidence for a lane.

    Unlike the paginated dispatch read, this database-only analytics route permits a
    year-scale window and requires pickup and delivery predicates to match separate
    certified stop roles on the same dispatch.
    """
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="TorqueAI lane analytics from date must not be after to date")
    if (date_to - date_from).days + 1 > 366:
        raise HTTPException(status_code=422, detail="TorqueAI lane analytics range must not exceed 366 days")

    normalized = {
        "customer": _normalized_filter(customer, "customer"),
        "pickup_city": _normalized_filter(pickup_city, "pickup_city"),
        "pickup_province": _normalized_filter(pickup_province, "pickup_province"),
        "pickup_country": _normalized_filter(pickup_country, "pickup_country"),
        "delivery_city": _normalized_filter(delivery_city, "delivery_city"),
        "delivery_province": _normalized_filter(delivery_province, "delivery_province"),
        "delivery_country": _normalized_filter(delivery_country, "delivery_country"),
    }

    query = session.query(TorqueAIDispatch).outerjoin(
        TorqueAIDispatchOperational,
        (TorqueAIDispatchOperational.dispatch_id == TorqueAIDispatch.id)
        & (TorqueAIDispatchOperational.organization_id == principal.organization_id),
    ).filter(
        TorqueAIDispatch.organization_id == principal.organization_id,
        TorqueAIDispatch.ship_date_text.is_not(None),
        TorqueAIDispatch.ship_date_text >= date_from.isoformat(),
        TorqueAIDispatch.ship_date_text < (date_to + timedelta(days=1)).isoformat(),
    )
    if normalized["customer"] is not None:
        query = query.filter(func.lower(TorqueAIDispatch.customer_name) == normalized["customer"].lower())

    def role_predicate(role: str, prefix: str):
        criteria = [
            TorqueAIDispatchStop.organization_id == principal.organization_id,
            func.lower(TorqueAIDispatchStop.job) == TORQUEAI_CERTIFIED_STOP_ROLE_JOBS[role].lower(),
        ]
        for suffix, column in (
            ("city", TorqueAIDispatchStop.city),
            ("province", TorqueAIDispatchStop.province),
            ("country", TorqueAIDispatchStop.country),
        ):
            value = normalized[f"{prefix}_{suffix}"]
            if value is not None:
                criteria.append(func.lower(column) == value.lower())
        return and_(*criteria)

    if any(normalized[f"pickup_{part}"] is not None for part in ("city", "province", "country")):
        query = query.filter(TorqueAIDispatch.operational_stops.any(role_predicate("pickup", "pickup")))
    if any(normalized[f"delivery_{part}"] is not None for part in ("city", "province", "country")):
        query = query.filter(TorqueAIDispatch.operational_stops.any(role_predicate("delivery", "delivery")))

    rows = query.all()
    by_currency: dict[str, dict[str, Any]] = {}
    missing_miles = 0
    missing_revenue = 0
    for row in rows:
        operational = row.operational_enrichment
        miles = row.loaded_miles
        charge = operational.total_charge if operational is not None else None
        currency = (operational.currency or operational.billing_currency) if operational is not None else None
        if miles is None:
            missing_miles += 1
        if charge is None or currency is None:
            missing_revenue += 1
            continue
        bucket = by_currency.setdefault(currency.upper(), {"load_count": 0, "revenue_load_count": 0, "miles_load_count": 0, "rpm_eligible_load_count": 0, "total_revenue": 0.0, "total_loaded_miles": 0.0, "rpm_revenue": 0.0, "rpm_miles": 0.0})
        bucket["revenue_load_count"] += 1
        bucket["total_revenue"] += float(charge)
        if miles is not None:
            bucket["miles_load_count"] += 1
            bucket["total_loaded_miles"] += float(miles)
            if miles > 0:
                bucket["rpm_eligible_load_count"] += 1
                bucket["rpm_revenue"] += float(charge)
                bucket["rpm_miles"] += float(miles)

    for bucket in by_currency.values():
        bucket["load_count"] = len(rows)
        bucket["average_revenue_per_load"] = bucket["total_revenue"] / bucket["revenue_load_count"] if bucket["revenue_load_count"] else None
        bucket["weighted_revenue_per_loaded_mile"] = bucket["rpm_revenue"] / bucket["rpm_miles"] if bucket["rpm_miles"] else None
        del bucket["rpm_revenue"]
        del bucket["rpm_miles"]

    return {
        "status": "success",
        "provider": "torqueai",
        "source": "durable_database",
        "request": {"from": date_from.isoformat(), "to": date_to.isoformat(), **normalized},
        "load_count": len(rows),
        "missing_loaded_miles_count": missing_miles,
        "missing_revenue_or_currency_count": missing_revenue,
        "currency_metrics": dict(sorted(by_currency.items())),
        "provider_called": False,
        "tenant_scope_validated": True,
        "secrets_exposed": False,
    }

def _torqueai_health_presentation(latest_run: TorqueAIDispatchSyncRun | None, sync_state: TorqueAIDispatchSyncState | None) -> tuple[str, str]:
    if latest_run is None:
        return "not_started", "No TorqueAI ingestion run has been recorded yet."
    if latest_run.status == "claimed":
        return "checking", "A scheduled TorqueAI ingestion slot has been claimed."
    if latest_run.status == "success":
        return "healthy", "Latest TorqueAI ingestion completed successfully."
    if sync_state is not None:
        return "degraded", "Latest TorqueAI ingestion failed; prior successful durable data remains available."
    return "degraded", "Latest TorqueAI ingestion failed and no successful durable window is recorded."


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


def _normalized_stop_role(value: str | None) -> str | None:
    normalized = _normalized_filter(value, "stop_role")
    if normalized is None:
        return None
    role = normalized.lower()
    if role not in TORQUEAI_CERTIFIED_STOP_ROLE_JOBS:
        allowed = ", ".join(sorted(TORQUEAI_CERTIFIED_STOP_ROLE_JOBS))
        raise HTTPException(status_code=422, detail=f"TorqueAI durable read stop_role must be one of: {allowed}")
    return role


def _serialize_dispatch(row: TorqueAIDispatch) -> dict[str, Any]:
    operational = row.operational_enrichment
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
        "currency": operational.currency if operational is not None else None,
        "total_charge": float(operational.total_charge) if operational is not None and operational.total_charge is not None else None,
        "stop_count": operational.stop_count if operational is not None else None,
        "stops": [_serialize_stop(stop) for stop in row.operational_stops],
        "first_observed_at": row.first_observed_at.isoformat(),
        "last_changed_at": row.last_changed_at.isoformat(),
    }


def _serialize_stop(stop: TorqueAIDispatchStop) -> dict[str, Any]:
    return {
        "index": stop.stop_index,
        "sequence": float(stop.sequence) if stop.sequence is not None else None,
        "stop_no": stop.stop_no,
        "job": stop.job,
        "name": stop.name,
        "address": stop.address,
        "city": stop.city,
        "province": stop.province,
        "country": stop.country,
        "zip_code": stop.zip_code,
        "latitude": float(stop.latitude) if stop.latitude is not None else None,
        "longitude": float(stop.longitude) if stop.longitude is not None else None,
        "commodity": stop.commodity,
        "notes": stop.notes,
        "driver_name": stop.driver_name,
        "co_driver_name": stop.co_driver_name,
        "carrier_name": stop.carrier_name,
        "truck_number": stop.truck_number,
        "trailer_number": stop.trailer_number,
        "scheduled": {
            "is_window": stop.scheduled_is_window,
            "pickup_date": stop.scheduled_pickup_date_text,
            "pickup_date2": stop.scheduled_pickup_date2_text,
            "pickup_time": stop.scheduled_pickup_time_text,
            "pickup_time2": stop.scheduled_pickup_time2_text,
        },
        "temperature": stop.temperature_text,
        "temperature_unit": stop.temperature_unit,
        "weight": float(stop.weight) if stop.weight is not None else None,
        "weight_unit": stop.weight_unit,
    }
