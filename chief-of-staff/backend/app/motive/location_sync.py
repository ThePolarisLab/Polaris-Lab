"""Bounded observation sync. Never imported or invoked by the MCP reader."""
from datetime import datetime, timezone
import math

from app.api.assignment_intelligence import _vehicle_lookup, _provider_driver_name
from app.connectors.motive import MotiveConnector, MotiveConnectorError
from app.models.motive import MotiveVehicleRecord
from app.models.motive_location import MotiveLocationObservation
from app.services.geography import province_values
from app.services.location_evidence import utc

MAX_VEHICLES = 100
LOCATION_UNAVAILABLE_REASONS = (
    "location_contract_unavailable", "location_identity_mismatch", "location_unavailable",
    "location_coordinates_invalid", "location_city_or_timestamp_unavailable",
)
UNAVAILABLE_REASONS = ("provider_request_failed", *LOCATION_UNAVAILABLE_REASONS, "unexpected_unavailable")
VEHICLE_STATUS_BUCKETS = ("active", "inactive", "other_or_unknown")


class LocationSyncError(ValueError):
    pass


def _unavailable_reason(exc):
    # Never stringify arbitrary exceptions, echo provider codes, or use raw
    # values as diagnostic keys. Only our exact controlled location errors pass.
    if isinstance(exc, MotiveConnectorError):
        return "provider_request_failed"
    if (isinstance(exc, LocationSyncError) and len(exc.args) == 1
            and type(exc.args[0]) is str and exc.args[0] in LOCATION_UNAVAILABLE_REASONS):
        return exc.args[0]
    return "unexpected_unavailable"


def _vehicle_status_bucket(value):
    if not isinstance(value, str):
        return "other_or_unknown"
    status = " ".join(value.strip().casefold().replace("_", " ").replace("-", " ").split())
    if status in {"active", "in service"}:
        return "active"
    if status in {"inactive", "deactivated", "out of service"}:
        return "inactive"
    return "other_or_unknown"


def _text(value, limit=255):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        return None
    return value.strip()


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return utc(parsed) if parsed.tzinfo else None
    except ValueError:
        return None


def _location(payload, provider_id, unit_number):
    """Require the documented v3 list envelope and exact requested identity.

    The existing safe diagnostic bucket ``location_contract_unavailable`` is
    intentionally narrowed to an empty documented list. Other structural
    contract failures remain unavailable but are classified by the outer safe
    diagnostic boundary as ``unexpected_unavailable``.
    """
    if not isinstance(payload, dict):
        raise LocationSyncError("location_payload_not_object")
    rows = payload.get("vehicles")
    if not isinstance(rows, list):
        raise LocationSyncError("location_vehicles_envelope_missing_or_invalid")
    if len(rows) == 0:
        raise LocationSyncError("location_contract_unavailable")
    if len(rows) != 1:
        raise LocationSyncError("location_multiple_rows")
    vehicle = rows[0].get("vehicle") if isinstance(rows[0], dict) else None
    if (not isinstance(vehicle, dict) or str(vehicle.get("id")) != provider_id
            or _text(vehicle.get("number"), 120) != unit_number):
        raise LocationSyncError("location_identity_mismatch")
    location = vehicle.get("current_location")
    if not isinstance(location, dict):
        raise LocationSyncError("location_unavailable")
    for key, bound in (("lat", 90), ("lon", 180)):
        value = location.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > bound:
            raise LocationSyncError("location_coordinates_invalid")
    province = _text(location.get("state"), 120)
    country = None
    if province:
        try:
            province = province_values(province)[0]
            country = "Canada"  # derived only from a recognized Canadian province
        except ValueError:
            pass
    city, observed_at = _text(location.get("city")), _timestamp(location.get("located_at"))
    if not city or observed_at is None:
        raise LocationSyncError("location_city_or_timestamp_unavailable")
    return {"city": city, "province": province,
            "country": country, "location_observed_at": observed_at}


def sync_locations(session, *, organization_id, connector=None, now=None):
    """All known tenant vehicles, bounded and atomic; failures invalidate old evidence.

    Calls two fixed read endpoints per vehicle. The caller owns tenant resolution
    and machine authentication. This method commits only minimized observations.
    """
    now = utc(now or datetime.now(timezone.utc))
    vehicles = session.query(MotiveVehicleRecord).filter_by(organization_id=organization_id).order_by(MotiveVehicleRecord.id).limit(MAX_VEHICLES + 1).all()
    if len(vehicles) > MAX_VEHICLES:
        raise LocationSyncError("vehicle_bound_exceeded")
    client = connector or (MotiveConnector(organization_id=organization_id) if vehicles else None)
    observations = []
    unavailable_reason_counts = dict.fromkeys(UNAVAILABLE_REASONS, 0)
    requested_by_status = dict.fromkeys(VEHICLE_STATUS_BUCKETS, 0)
    unavailable_by_status = dict.fromkeys(VEHICLE_STATUS_BUCKETS, 0)
    for vehicle in vehicles:
        status_bucket = _vehicle_status_bucket(vehicle.status)
        requested_by_status[status_bucket] += 1
        values = dict(truck_number=vehicle.unit_number, city=None, province=None, country=None, location_observed_at=None,
                      current_driver_name=None, pairing_observed_at=None,
                      collected_at=now, signal_status="unavailable")
        try:
            payload = client._request_json(
                "/v3/vehicle_locations", params={"vehicle_ids[]": vehicle.provider_vehicle_id, "per_page": 2, "page_no": 1},
                operation="durable_location_sync",
            )
            values.update(_location(payload, vehicle.provider_vehicle_id, vehicle.unit_number))
            lookup = _vehicle_lookup(client, vehicle.unit_number)
            if str(lookup.get("id")) == vehicle.provider_vehicle_id and lookup.get("number") == vehicle.unit_number:
                driver = lookup.get("current_driver")
                if isinstance(driver, dict) and driver.get("id") is not None and driver.get("status") == "active":
                    values["current_driver_name"] = _text(_provider_driver_name(driver))
                    values["pairing_observed_at"] = now if values["current_driver_name"] else None
            values["signal_status"] = "observed"
        except Exception as exc:
            # No exception/provider text crosses this boundary. Failed refresh
            # replaces the old signal instead of silently leaving it confirmed.
            values["signal_status"] = "unavailable"
            unavailable_reason_counts[_unavailable_reason(exc)] += 1
            unavailable_by_status[status_bucket] += 1
        observations.append((vehicle.id, values))
    try:
        for vehicle_id, values in observations:
            row = session.query(MotiveLocationObservation).filter_by(organization_id=organization_id, vehicle_id=vehicle_id).with_for_update().one_or_none()
            if row is not None and utc(row.collected_at) > now:
                continue  # an overlapping older collection cannot win
            if row is None:
                row = MotiveLocationObservation(organization_id=organization_id, vehicle_id=vehicle_id)
                session.add(row)
            for name, value in values.items():
                setattr(row, name, value)
        session.commit()
    except Exception:
        session.rollback()
        raise LocationSyncError("location_persistence_failed") from None
    available = sum(values["signal_status"] == "observed" for _, values in observations)
    return {"status": "success" if available == len(vehicles) else "degraded",
            "vehicles_requested": len(vehicles), "locations_observed": available,
            "unavailable": len(vehicles) - available, "as_of": now.isoformat(),
            "unavailable_reason_counts": unavailable_reason_counts,
            "requested_by_status": requested_by_status,
            "unavailable_by_status": unavailable_by_status}
