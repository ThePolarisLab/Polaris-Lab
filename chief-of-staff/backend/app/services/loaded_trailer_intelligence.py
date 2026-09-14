"""Conservative, tenant-scoped loaded trailer evidence from durable data only."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import re

from sqlalchemy.orm import selectinload, with_loader_criteria

from app.api.assignment_guardrails import classify_assignment_consistency, classify_pickup_temporal_status
from app.models.motive import MotiveVehicleRecord
from app.models.motive_location import MotiveLocationObservation
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchStop
from app.services.geography import province_values
from app.services.location_evidence import age_minutes, fresh, location_confidence, utc, STALE_LOCATION_MAX_AGE_MINUTES

MAX_DISPATCHES = 5000
MAX_RESULTS = 500
LOADED_STATUSES = {"loaded", "in transit", "picked up"}
EXCLUDED_STATUSES = {"delivered", "completed", "complete", "cancelled", "canceled", "empty", "unassigned", "unloaded"}


class LoadedTrailerLimitError(ValueError):
    pass


def normalized(value):
    return " ".join((value or "").strip().casefold().replace("_", " ").replace("-", " ").split())


def equipment(value):
    # Keep punctuation; distinct equipment identifiers must not be merged.
    return (value or "").strip().casefold()


def excluded_status(value):
    return bool(set(re.findall(r"[a-z]+", normalized(value))) & EXCLUDED_STATUSES)


def _province(value):
    try:
        return province_values(value.strip())[0].casefold()
    except (ValueError, AttributeError):
        return normalized(value)


def _country(value):
    value = normalized(value)
    return {"ca": "canada", "can": "canada", "us": "united states", "usa": "united states"}.get(value, value)


def matches(city, province, country, request):
    return (equipment(city) == equipment(request["city"])
            and (request.get("province") is None or _province(province) == _province(request["province"]))
            and (request.get("country") is None or _country(country) == _country(request["country"])))


def iso(value):
    return utc(value).isoformat() if value else None


def query_loaded_trailers(session, *, organization_id, request, now=None):
    now = utc(now or datetime.now(timezone.utc))
    # Choose the latest assignment BEFORE location/status filtering. A newer
    # delivered or empty record must suppress an obsolete active assignment.
    dispatches = session.query(TorqueAIDispatch).filter_by(organization_id=organization_id).options(
        selectinload(TorqueAIDispatch.operational_stops),
        with_loader_criteria(TorqueAIDispatchStop, TorqueAIDispatchStop.organization_id == organization_id)
    ).order_by(TorqueAIDispatch.last_changed_at.desc(), TorqueAIDispatch.first_observed_at.desc(), TorqueAIDispatch.id.desc()).limit(MAX_DISPATCHES + 1).all()
    if len(dispatches) > MAX_DISPATCHES:
        raise LoadedTrailerLimitError()
    latest, ambiguous_latest = {}, set()
    for dispatch in dispatches:
        key = equipment(dispatch.trailer_number)
        if key and key not in {"none", "n/a", "na", "unassigned", "-"}:
            previous = latest.get(key)
            if (previous is not None and utc(previous.last_changed_at) == utc(dispatch.last_changed_at)
                    and (equipment(previous.truck_number), normalized(previous.status))
                    != (equipment(dispatch.truck_number), normalized(dispatch.status))):
                ambiguous_latest.add(key)
            latest.setdefault(key, dispatch)
    trucks = Counter(equipment(d.truck_number) for d in latest.values() if not excluded_status(d.status) and equipment(d.truck_number))
    vehicles = defaultdict(list)
    vehicle_rows = session.query(MotiveVehicleRecord, MotiveLocationObservation).outerjoin(
        MotiveLocationObservation,
        (MotiveLocationObservation.vehicle_id == MotiveVehicleRecord.id)
        & (MotiveLocationObservation.organization_id == organization_id),
    ).filter(MotiveVehicleRecord.organization_id == organization_id).limit(MAX_DISPATCHES + 1).all()
    if len(vehicle_rows) > MAX_DISPATCHES:
        raise LoadedTrailerLimitError()
    for vehicle, observation in vehicle_rows:
        vehicles[equipment(vehicle.unit_number)].append((vehicle, observation))
    confirmed, uncertain = [], []
    for dispatch in latest.values():
        status = normalized(dispatch.status)
        if excluded_status(status):
            continue
        flags, evidence = [], ["trailer_assigned_on_dispatch"]
        if equipment(dispatch.trailer_number) in ambiguous_latest:
            flags.append("latest_trailer_assignment_ambiguous")
        if status in LOADED_STATUSES:
            evidence += ["explicit_loaded_or_in_transit_status", "no_terminal_status"]
        else:
            flags.append("loaded_state_not_established")
        if not fresh(dispatch.last_observed_at, now):
            flags.append("dispatch_stale_or_unobserved")
        if utc(dispatch.last_changed_at) > now:
            flags.append("dispatch_timestamp_in_future")
        assignment = {key: getattr(dispatch, key) for key in ("driver_name", "truck_number", "trailer_number")}
        flags += classify_assignment_consistency(dispatch.status, assignment)["reason_codes"]
        stops = [s for s in dispatch.operational_stops if s.organization_id == organization_id]
        pickups = [s for s in stops if normalized(s.job) == "pick up"]
        temporal = [classify_pickup_temporal_status(s.scheduled_pickup_date_text, reference_date=now.date())["status"] for s in pickups]
        if temporal and all(t == "upcoming" for t in temporal):
            flags.append("pickup_schedule_in_future")
        if any((equipment(s.truck_number) and equipment(s.truck_number) != equipment(dispatch.truck_number))
               or (equipment(s.trailer_number) and equipment(s.trailer_number) != equipment(dispatch.trailer_number)) for s in stops):
            flags.append("stop_assignment_conflicts_with_dispatch")
        if trucks[equipment(dispatch.truck_number)] > 1:
            flags.append("truck_has_multiple_current_trailer_assignments")
        pairs = vehicles[equipment(dispatch.truck_number)] if equipment(dispatch.truck_number) else []
        observation = pairs[0][1] if len(pairs) == 1 else None
        if len(pairs) > 1:
            flags.append("ambiguous_vehicle_number")
        if observation and observation.city:
            # GPS elsewhere always beats a scheduled stop, even when stale.
            if not matches(observation.city, observation.province, observation.country, request):
                continue
            source = "motive_gps"
            city, province, country = observation.city, observation.province, observation.country
            located_at = observation.location_observed_at
            if equipment(observation.truck_number) != equipment(dispatch.truck_number):
                flags.append("vehicle_number_changed_since_observation")
            if located_at and utc(located_at) < utc(dispatch.last_changed_at):
                flags.append("gps_predates_dispatch_assignment_evidence")
            if observation.signal_status != "observed" or not fresh(observation.collected_at, now):
                flags.append("location_collection_unavailable_or_stale")
            if not fresh(located_at, now):
                flags.append("location_stale_missing_or_future")
            if (not fresh(observation.pairing_observed_at, now) or not normalized(dispatch.driver_name)
                    or equipment(observation.current_driver_name) != equipment(dispatch.driver_name)):
                flags.append("current_driver_pairing_unverified_or_conflicting")
            else:
                evidence.append("motive_current_driver_matches_dispatch_driver")
            if normalized(pairs[0][0].status) not in {"active", "in service"}:
                flags.append("vehicle_status_requires_verification")
            evidence += ["motive_city_matches_request", "trailer_location_via_dispatch_truck_assignment"]
        else:
            matching_stops = [s for s in stops if matches(s.city, s.province, s.country, request)]
            if not matching_stops:
                continue
            # Only a possible match, never a current physical-location assertion.
            source, city, province, country, located_at = "dispatch_inference", None, None, None, None
            flags += ["current_location_unavailable", "scheduled_stop_only_not_current_location"]
        is_confirmed = not flags
        row = {
            "trailer_number": dispatch.trailer_number, "load_number": dispatch.provider_load_number,
            "load_status": dispatch.status, "truck_number": dispatch.truck_number,
            "current_city": city, "current_province": province, "current_country": country,
            "location_source": source, "location_observed_at": iso(located_at),
            "dispatch_last_changed_at": iso(dispatch.last_changed_at),
            "dispatch_last_observed_at": iso(dispatch.last_observed_at),
            "pairing_observed_at": iso(observation.pairing_observed_at) if observation else None,
            "loaded_state": "confirmed" if is_confirmed else "uncertain",
            "loaded_evidence": evidence,
            "confidence": location_confidence(max(age_minutes(t, now) for t in (
                located_at, dispatch.last_observed_at, observation.pairing_observed_at,
                observation.collected_at,
            ))) if is_confirmed else "low",
            "attention_flags": sorted(set(flags)),
        }
        (confirmed if is_confirmed else uncertain).append(row)
    if len(confirmed) + len(uncertain) > MAX_RESULTS:
        raise LoadedTrailerLimitError()
    return {
        "status": "success", "source": "polaris_operational_intelligence", "request": request,
        "as_of": now.isoformat(), "location_staleness_threshold_minutes": STALE_LOCATION_MAX_AGE_MINUTES,
        "summary": {"confirmed_loaded_trailer_count": len(confirmed), "uncertain_loaded_trailer_count": len(uncertain)},
        "trailers": sorted(confirmed, key=lambda r: equipment(r["trailer_number"])),
        "uncertain_trailers": sorted(uncertain, key=lambda r: equipment(r["trailer_number"])),
    }
