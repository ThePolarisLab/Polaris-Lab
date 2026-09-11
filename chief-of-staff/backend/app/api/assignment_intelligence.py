"""Read-only assignment intelligence combining TorqueAI pickup context with Motive signals."""

from __future__ import annotations

from datetime import date, datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.connectors.motive import MotiveConnector, MotiveConnectorError
from app.database.database import SessionLocal
from app.models.motive import MotiveDriverRecord, MotiveVehicleRecord
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchStop
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/api/v1/assignment-intelligence", tags=["assignment-intelligence"])
PICKUP_JOB = "Pick Up"
MAX_TRUCK_CANDIDATES = 20
MAX_DRIVER_CANDIDATES = 100


def _db() -> Session:
    with SessionLocal() as session:
        yield session


@router.get("/candidates")
def assignment_candidates(
    load_number: str = Query(..., min_length=1, max_length=120),
    hos_date: date | None = Query(None),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Rank truck and driver signals separately for dispatcher review.

    Truck/driver pairing is intentionally not inferred because Motive's certified
    latest-location sample did not prove an authoritative current pairing field.
    Driver HOS durations are relative workload signals, not legal remaining-hours
    calculations.
    """
    dispatch = (
        session.query(TorqueAIDispatch)
        .filter(
            TorqueAIDispatch.organization_id == principal.organization_id,
            TorqueAIDispatch.provider_load_number == load_number.strip(),
        )
        .first()
    )
    if dispatch is None:
        raise HTTPException(status_code=404, detail="TorqueAI load not found")

    pickup = _first_pickup(dispatch)
    if pickup is None:
        raise HTTPException(status_code=422, detail="TorqueAI load has no certified Pick Up stop")
    if pickup.latitude is None or pickup.longitude is None:
        raise HTTPException(status_code=422, detail="Pickup stop is missing certified coordinates")

    target_hos_date = hos_date or _parse_date(pickup.scheduled_pickup_date_text) or datetime.now(timezone.utc).date()
    motive = MotiveConnector(organization_id=principal.organization_id)

    trucks = _rank_trucks(
        session,
        organization_id=principal.organization_id,
        pickup_lat=float(pickup.latitude),
        pickup_lon=float(pickup.longitude),
        certification_date=target_hos_date,
        connector=motive,
    )
    drivers = _rank_drivers(
        session,
        organization_id=principal.organization_id,
        hos_date=target_hos_date,
        connector=motive,
    )

    return {
        "status": "success",
        "planning_scope": "assignment_read_only_v1",
        "load": {
            "load_number": dispatch.provider_load_number,
            "order_number": dispatch.provider_order_number,
            "status": dispatch.status,
            "customer_name": dispatch.customer_name,
            "current_assignment": {
                "driver_name": dispatch.driver_name,
                "truck_number": dispatch.truck_number,
                "trailer_number": dispatch.trailer_number,
            },
            "pickup": {
                "name": pickup.name,
                "city": pickup.city,
                "province": pickup.province,
                "country": pickup.country,
                "scheduled_date": pickup.scheduled_pickup_date_text,
                "scheduled_time": pickup.scheduled_pickup_time_text,
            },
        },
        "truck_candidates": trucks,
        "driver_candidates": drivers,
        "decision_guardrails": {
            "truck_driver_pairing_inferred": False,
            "hos_is_legal_remaining_hours": False,
            "dispatcher_approval_required": True,
            "autonomous_assignment_performed": False,
        },
        "provider_calls": {
            "motive_latest_location": True,
            "motive_hos": True,
            "torqueai_live": False,
        },
        "tenant_scope_validated": True,
        "secrets_exposed": False,
    }


def _first_pickup(dispatch: TorqueAIDispatch) -> TorqueAIDispatchStop | None:
    stops = [stop for stop in dispatch.operational_stops if (stop.job or "").strip().lower() == PICKUP_JOB.lower()]
    stops.sort(key=lambda stop: (stop.stop_index, stop.id))
    return stops[0] if stops else None


def _rank_trucks(
    session: Session,
    *,
    organization_id: str,
    pickup_lat: float,
    pickup_lon: float,
    certification_date: date,
    connector: MotiveConnector,
) -> list[dict[str, Any]]:
    vehicles = (
        session.query(MotiveVehicleRecord)
        .filter(MotiveVehicleRecord.organization_id == organization_id)
        .order_by(MotiveVehicleRecord.unit_number.asc(), MotiveVehicleRecord.id.asc())
        .limit(MAX_TRUCK_CANDIDATES)
        .all()
    )
    candidates: list[dict[str, Any]] = []
    for vehicle in vehicles:
        endpoint = f"/v1/vehicle_locations/{vehicle.provider_vehicle_id}"
        try:
            payload = connector._request_json(  # noqa: SLF001 - hardened provider auth/retry path.
                endpoint,
                params={"date": certification_date.isoformat()},
                operation="assignment_intelligence_latest_vehicle_location",
            )
        except MotiveConnectorError:
            continue
        location = _extract_latest_location(payload)
        if location is None:
            continue
        lat = _number(location.get("lat"))
        lon = _number(location.get("lon"))
        if lat is None or lon is None:
            continue
        distance_km = _haversine_km(pickup_lat, pickup_lon, lat, lon)
        located_at = location.get("located_at") if isinstance(location.get("located_at"), str) else None
        freshness_minutes = _freshness_minutes(located_at)
        status_penalty = 0 if (vehicle.status or "").strip().lower() in {"active", "in service", "in_service"} else 1
        freshness_penalty = freshness_minutes if freshness_minutes is not None else 1000000.0
        candidates.append(
            {
                "truck_number": vehicle.unit_number,
                "vehicle_status": vehicle.status,
                "distance_to_pickup_km": round(distance_km, 1),
                "location_freshness_minutes": round(freshness_minutes, 1) if freshness_minutes is not None else None,
                "speed": _number(location.get("speed")),
                "fuel_primary_remaining_percentage": _number(location.get("fuel_primary_remaining_percentage")),
                "ranking_basis": ["pickup_distance", "location_freshness", "vehicle_status"],
                "_sort": (status_penalty, distance_km, freshness_penalty, vehicle.unit_number or ""),
            }
        )
    candidates.sort(key=lambda item: item["_sort"])
    for rank, candidate in enumerate(candidates, start=1):
        candidate.pop("_sort", None)
        candidate["rank"] = rank
    return candidates


def _rank_drivers(
    session: Session,
    *,
    organization_id: str,
    hos_date: date,
    connector: MotiveConnector,
) -> list[dict[str, Any]]:
    try:
        payload = connector._request_json(  # noqa: SLF001 - hardened provider auth/retry path.
            "/v1/hours_of_service",
            params={
                "start_date": hos_date.isoformat(),
                "end_date": hos_date.isoformat(),
                "per_page": MAX_DRIVER_CANDIDATES,
                "page_no": 1,
            },
            operation="assignment_intelligence_hos",
        )
    except MotiveConnectorError:
        return []

    known = {
        driver.provider_driver_id: driver
        for driver in session.query(MotiveDriverRecord)
        .filter(MotiveDriverRecord.organization_id == organization_id)
        .all()
    }
    candidates: list[dict[str, Any]] = []
    rows = payload.get("hours_of_services", []) if isinstance(payload, dict) else []
    for item in rows if isinstance(rows, list) else []:
        hos = item.get("hours_of_service") if isinstance(item, dict) else None
        if not isinstance(hos, dict):
            continue
        provider_driver = hos.get("driver")
        if not isinstance(provider_driver, dict):
            continue
        provider_id = provider_driver.get("id")
        driver_record = known.get(str(provider_id)) if provider_id is not None else None
        name = driver_record.name if driver_record is not None else _provider_driver_name(provider_driver)
        status = driver_record.status if driver_record is not None else provider_driver.get("status")
        driving = _integer(hos.get("driving_duration"))
        on_duty = _integer(hos.get("on_duty_duration"))
        active_penalty = 0 if str(status or "").strip().lower() == "active" else 1
        candidates.append(
            {
                "driver_name": name,
                "driver_status": status,
                "hos_date": hos.get("date"),
                "driving_duration_seconds": driving,
                "on_duty_duration_seconds": on_duty,
                "off_duty_duration_seconds": _integer(hos.get("off_duty_duration")),
                "sleeper_duration_seconds": _integer(hos.get("sleeper_duration")),
                "waiting_duration_seconds": _integer(hos.get("waiting_duration")),
                "ranking_basis": ["active_status", "lower_observed_driving_duration", "lower_observed_on_duty_duration"],
                "_sort": (active_penalty, driving if driving is not None else 10**12, on_duty if on_duty is not None else 10**12, name or ""),
            }
        )
    candidates.sort(key=lambda item: item["_sort"])
    for rank, candidate in enumerate(candidates, start=1):
        candidate.pop("_sort", None)
        candidate["rank"] = rank
    return candidates


def _extract_latest_location(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    rows = payload.get("vehicle_locations")
    if not isinstance(rows, list):
        return None
    for item in rows:
        if isinstance(item, dict) and isinstance(item.get("vehicle_location"), dict):
            return item["vehicle_location"]
    return None


def _provider_driver_name(driver: dict[str, Any]) -> str | None:
    parts = [str(driver.get(key) or "").strip() for key in ("first_name", "last_name")]
    name = " ".join(part for part in parts if part)
    return name or None


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _integer(value: Any) -> int | None:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def _freshness_minutes(value: str | None) -> float | None:
    if not value:
        return None
    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds() / 60.0)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_km = 6371.0088
    lat1r, lon1r, lat2r, lon2r = map(radians, (lat1, lon1, lat2, lon2))
    dlat = lat2r - lat1r
    dlon = lon2r - lon1r
    a = sin(dlat / 2) ** 2 + cos(lat1r) * cos(lat2r) * sin(dlon / 2) ** 2
    return 2 * earth_km * asin(sqrt(a))
