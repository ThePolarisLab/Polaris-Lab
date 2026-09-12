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
HIGH_CONFIDENCE_LOCATION_MAX_AGE_MINUTES = 30.0
STALE_LOCATION_MAX_AGE_MINUTES = 120.0
PAIRING_SOURCE = "motive_vehicle_lookup_current_driver"
READINESS_READY = "ready"
READINESS_VERIFY = "verify"
READINESS_NOT_SUITABLE = "not_suitable"
ACTIVE_VEHICLE_STATUSES = {"active", "in service", "in_service"}
INACTIVE_VEHICLE_STATUSES = {"inactive", "deactivated", "out of service", "out_of_service"}
ACTIVE_DRIVER_STATUSES = {"active"}
INACTIVE_DRIVER_STATUSES = {"inactive", "deactivated"}


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
    """Return dispatcher decision support without assigning equipment or drivers.

    Motive vehicle lookup is treated as the authoritative source for the vehicle's
    current_driver relationship when that object is present. HOS records remain
    observed duty-duration signals; Polaris does not calculate legal remaining HOS.
    Dispatch readiness is advisory and does not replace dispatcher judgment.
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

    today = datetime.now(timezone.utc).date()
    target_hos_date = hos_date or today
    motive = MotiveConnector(organization_id=principal.organization_id)

    drivers = _rank_drivers(
        session,
        organization_id=principal.organization_id,
        hos_date=target_hos_date,
        connector=motive,
    )
    trucks = _rank_trucks(
        session,
        organization_id=principal.organization_id,
        pickup_lat=float(pickup.latitude),
        pickup_lon=float(pickup.longitude),
        location_date=today,
        connector=motive,
    )
    _attach_paired_driver_hos(trucks, drivers)
    _attach_dispatch_readiness(trucks)
    _strip_internal_ids(trucks, drivers)

    top_truck = trucks[0] if trucks else None
    top_truck_location_stale = bool(top_truck and top_truck.get("location_stale"))
    stale_truck_locations_present = any(bool(candidate.get("location_stale")) for candidate in trucks)
    authoritative_pairs_present = any(bool(candidate.get("current_driver_authoritative")) for candidate in trucks)
    readiness_counts = {
        classification: sum(
            1
            for candidate in trucks
            if (candidate.get("dispatch_readiness") or {}).get("classification") == classification
        )
        for classification in (READINESS_READY, READINESS_VERIFY, READINESS_NOT_SUITABLE)
    }
    top_truck_readiness = (
        (top_truck.get("dispatch_readiness") or {}).get("classification")
        if top_truck is not None
        else None
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
        "signal_dates": {
            "motive_latest_location": today.isoformat(),
            "motive_hos": target_hos_date.isoformat(),
        },
        "truck_candidates": trucks,
        "driver_candidates": drivers,
        "readiness_summary": {
            "ready": readiness_counts[READINESS_READY],
            "verify": readiness_counts[READINESS_VERIFY],
            "not_suitable": readiness_counts[READINESS_NOT_SUITABLE],
            "top_ranked_truck_readiness": top_truck_readiness,
        },
        "decision_guardrails": {
            "truck_driver_pairing_inferred": False,
            "truck_driver_pairing_authoritative_source": PAIRING_SOURCE,
            "authoritative_truck_driver_pairs_present": authoritative_pairs_present,
            "hos_is_legal_remaining_hours": False,
            "hos_duration_unit": "seconds",
            "hos_duration_unit_certified": True,
            "legacy_hos_seconds_labels_unit_unverified": False,
            "location_staleness_threshold_minutes": STALE_LOCATION_MAX_AGE_MINUTES,
            "stale_truck_locations_present": stale_truck_locations_present,
            "top_truck_location_stale": top_truck_location_stale,
            "top_truck_requires_location_verification": top_truck_location_stale,
            "dispatch_readiness_is_advisory": True,
            "dispatch_readiness_uses_legal_remaining_hos": False,
            "dispatch_readiness_distance_threshold_applied": False,
            "distance_remains_relative_ranking_signal": True,
            "dispatcher_approval_required": True,
            "autonomous_assignment_performed": False,
        },
        "provider_calls": {
            "motive_latest_location": True,
            "motive_vehicle_lookup": True,
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
    location_date: date,
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
        try:
            location_payload = connector._request_json(  # noqa: SLF001 - hardened provider auth/retry path.
                f"/v1/vehicle_locations/{vehicle.provider_vehicle_id}",
                params={"date": location_date.isoformat()},
                operation="assignment_intelligence_latest_vehicle_location",
            )
        except MotiveConnectorError:
            continue
        location = _extract_latest_location(location_payload)
        if location is None:
            continue
        lat = _number(location.get("lat"))
        lon = _number(location.get("lon"))
        if lat is None or lon is None:
            continue

        vehicle_lookup = _vehicle_lookup(connector, vehicle.unit_number)
        current_driver = vehicle_lookup.get("current_driver") if isinstance(vehicle_lookup, dict) else None
        availability = vehicle_lookup.get("availability_details") if isinstance(vehicle_lookup, dict) else None
        authoritative_driver = current_driver if isinstance(current_driver, dict) else None
        provider_driver_id = authoritative_driver.get("id") if authoritative_driver else None

        distance_km = _haversine_km(pickup_lat, pickup_lon, lat, lon)
        located_at = location.get("located_at") if isinstance(location.get("located_at"), str) else None
        freshness_minutes = _freshness_minutes(located_at)
        location_stale = freshness_minutes is None or freshness_minutes > STALE_LOCATION_MAX_AGE_MINUTES
        status_penalty = 0 if (vehicle.status or "").strip().lower() in ACTIVE_VEHICLE_STATUSES else 1
        freshness_penalty = freshness_minutes if freshness_minutes is not None else 1000000.0

        candidates.append(
            {
                "truck_number": vehicle.unit_number,
                "vehicle_status": vehicle.status,
                "distance_to_pickup_km": round(distance_km, 1),
                "location_freshness_minutes": round(freshness_minutes, 1) if freshness_minutes is not None else None,
                "location_confidence": _location_confidence(freshness_minutes),
                "location_stale": location_stale,
                "location_verification_required": location_stale,
                "speed": _number(location.get("speed")),
                "fuel_primary_remaining_percentage": _number(location.get("fuel_primary_remaining_percentage")),
                "current_driver": {
                    "name": _provider_driver_name(authoritative_driver) if authoritative_driver else None,
                    "status": authoritative_driver.get("status") if authoritative_driver else None,
                },
                "current_driver_authoritative": authoritative_driver is not None,
                "current_driver_source": PAIRING_SOURCE if authoritative_driver is not None else None,
                "dispatch_availability_status": availability.get("availability_status") if isinstance(availability, dict) else None,
                "_current_driver_provider_id": str(provider_driver_id) if provider_driver_id is not None else None,
                "ranking_basis": ["pickup_distance", "location_freshness", "vehicle_status"],
                "_sort": (status_penalty, distance_km, freshness_penalty, vehicle.unit_number or ""),
            }
        )
    candidates.sort(key=lambda item: item["_sort"])
    for rank, candidate in enumerate(candidates, start=1):
        candidate.pop("_sort", None)
        candidate["rank"] = rank
    return candidates


def _vehicle_lookup(connector: MotiveConnector, unit_number: str | None) -> dict[str, Any]:
    if not unit_number:
        return {}
    try:
        payload = connector._request_json(  # noqa: SLF001 - hardened provider auth/retry path.
            "/v1/vehicles/lookup",
            params={"number": unit_number},
            operation="assignment_intelligence_vehicle_lookup",
        )
    except MotiveConnectorError:
        return {}
    vehicle = payload.get("vehicle") if isinstance(payload, dict) else None
    return vehicle if isinstance(vehicle, dict) else {}


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
        provider_id_text = str(provider_id) if provider_id is not None else None
        driver_record = known.get(provider_id_text) if provider_id_text is not None else None
        name = driver_record.name if driver_record is not None else _provider_driver_name(provider_driver)
        status = driver_record.status if driver_record is not None else provider_driver.get("status")
        driving = _integer(hos.get("driving_duration"))
        on_duty = _integer(hos.get("on_duty_duration"))
        off_duty = _integer(hos.get("off_duty_duration"))
        sleeper = _integer(hos.get("sleeper_duration"))
        waiting = _integer(hos.get("waiting_duration"))
        active_penalty = 0 if str(status or "").strip().lower() == "active" else 1
        candidates.append(
            {
                "driver_name": name,
                "driver_status": status,
                "hos_date": hos.get("date"),
                "observed_driving_duration": driving,
                "observed_on_duty_duration": on_duty,
                "observed_off_duty_duration": off_duty,
                "observed_sleeper_duration": sleeper,
                "observed_waiting_duration": waiting,
                "duration_unit": "seconds",
                "duration_unit_certified": True,
                "driving_duration_seconds": driving,
                "on_duty_duration_seconds": on_duty,
                "off_duty_duration_seconds": off_duty,
                "sleeper_duration_seconds": sleeper,
                "waiting_duration_seconds": waiting,
                "_provider_driver_id": provider_id_text,
                "ranking_basis": ["active_status", "lower_observed_driving_duration", "lower_observed_on_duty_duration"],
                "_sort": (active_penalty, driving if driving is not None else 10**12, on_duty if on_duty is not None else 10**12, name or ""),
            }
        )
    candidates.sort(key=lambda item: item["_sort"])
    for rank, candidate in enumerate(candidates, start=1):
        candidate.pop("_sort", None)
        candidate["rank"] = rank
    return candidates


def _attach_paired_driver_hos(trucks: list[dict[str, Any]], drivers: list[dict[str, Any]]) -> None:
    by_provider_id = {
        candidate.get("_provider_driver_id"): candidate
        for candidate in drivers
        if candidate.get("_provider_driver_id")
    }
    for truck in trucks:
        provider_id = truck.get("_current_driver_provider_id")
        driver = by_provider_id.get(provider_id)
        truck["current_driver_hos_observed"] = (
            {
                "hos_date": driver.get("hos_date"),
                "driving_duration_seconds": driver.get("driving_duration_seconds"),
                "on_duty_duration_seconds": driver.get("on_duty_duration_seconds"),
                "off_duty_duration_seconds": driver.get("off_duty_duration_seconds"),
                "sleeper_duration_seconds": driver.get("sleeper_duration_seconds"),
                "waiting_duration_seconds": driver.get("waiting_duration_seconds"),
                "is_legal_remaining_hours": False,
            }
            if driver is not None
            else None
        )


def _attach_dispatch_readiness(trucks: list[dict[str, Any]]) -> None:
    for truck in trucks:
        truck["dispatch_readiness"] = _classify_dispatch_readiness(truck)


def _classify_dispatch_readiness(candidate: dict[str, Any]) -> dict[str, Any]:
    hard_blockers: list[str] = []
    verification_reasons: list[str] = []

    vehicle_status = _normalized_status(candidate.get("vehicle_status"))
    availability_status = _normalized_status(candidate.get("dispatch_availability_status"))
    current_driver = candidate.get("current_driver") if isinstance(candidate.get("current_driver"), dict) else {}
    driver_status = _normalized_status(current_driver.get("status"))

    if availability_status in {"out_of_service", "out of service"}:
        hard_blockers.append("motive_dispatch_availability_out_of_service")
    if vehicle_status in INACTIVE_VEHICLE_STATUSES:
        hard_blockers.append("vehicle_status_not_active")
    elif vehicle_status not in ACTIVE_VEHICLE_STATUSES:
        verification_reasons.append("vehicle_status_requires_verification")

    if candidate.get("current_driver_authoritative"):
        if driver_status in INACTIVE_DRIVER_STATUSES:
            hard_blockers.append("authoritative_current_driver_not_active")
        elif driver_status not in ACTIVE_DRIVER_STATUSES:
            verification_reasons.append("authoritative_current_driver_status_requires_verification")
    else:
        verification_reasons.append("authoritative_current_driver_missing")

    if candidate.get("location_stale"):
        verification_reasons.append("location_stale_or_missing")
    if availability_status != "in_service" and not hard_blockers:
        verification_reasons.append("motive_dispatch_availability_not_confirmed_in_service")
    if candidate.get("current_driver_hos_observed") is None:
        verification_reasons.append("paired_driver_hos_observation_missing")

    if hard_blockers:
        classification = READINESS_NOT_SUITABLE
    elif verification_reasons:
        classification = READINESS_VERIFY
    else:
        classification = READINESS_READY

    return {
        "classification": classification,
        "verification_required": classification != READINESS_READY,
        "hard_blockers": hard_blockers,
        "verification_reasons": verification_reasons,
        "distance_to_pickup_km": candidate.get("distance_to_pickup_km"),
        "distance_threshold_applied": False,
        "distance_requires_dispatch_judgment": True,
        "legal_remaining_hos_confirmed": False,
        "dispatcher_approval_required": True,
    }


def _strip_internal_ids(trucks: list[dict[str, Any]], drivers: list[dict[str, Any]]) -> None:
    for truck in trucks:
        truck.pop("_current_driver_provider_id", None)
    for driver in drivers:
        driver.pop("_provider_driver_id", None)


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


def _provider_driver_name(driver: dict[str, Any] | None) -> str | None:
    if not isinstance(driver, dict):
        return None
    parts = [str(driver.get(key) or "").strip() for key in ("first_name", "last_name")]
    name = " ".join(part for part in parts if part)
    return name or None


def _normalized_status(value: Any) -> str:
    return str(value or "").strip().lower()


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


def _location_confidence(freshness_minutes: float | None) -> str:
    if freshness_minutes is None:
        return "unknown"
    if freshness_minutes <= HIGH_CONFIDENCE_LOCATION_MAX_AGE_MINUTES:
        return "high"
    if freshness_minutes <= STALE_LOCATION_MAX_AGE_MINUTES:
        return "medium"
    return "low"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_km = 6371.0088
    lat1r, lon1r, lat2r, lon2r = map(radians, (lat1, lon1, lat2, lon2))
    dlat = lat2r - lat1r
    dlon = lon2r - lon1r
    a = sin(dlat / 2) ** 2 + cos(lat1r) * cos(lat2r) * sin(dlon / 2) ** 2
    return 2 * earth_km * asin(sqrt(a))