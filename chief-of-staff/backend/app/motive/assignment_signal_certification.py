"""Privacy-safe production certification for Motive assignment signals.

This gate observes only schema/type structure for two read-only resources needed
by future truck/driver assignment intelligence:
- driver Hours of Service (HOS)
- bounded stored-vehicle location history samples

No raw provider values are returned to callers.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.motive import MotiveConnector, MotiveConnectorError
from app.models.motive import MotiveVehicleRecord
from app.motive.vehicle_utilization_scheduler import resolve_scheduled_organization

HOS_ENDPOINT = "/v1/hours_of_service"
VEHICLE_LOCATION_ENDPOINT_TEMPLATE = "/v3/vehicle_locations/{vehicle_id}"
MAX_SCHEMA_DEPTH = 6
MAX_ARRAY_ITEMS_TO_OBSERVE = 5
MAX_LOCATION_VEHICLES_TO_SAMPLE = 5
LOCATION_LOOKBACK_DAYS = 7


def certify_assignment_signal_schema(
    session: Session,
    *,
    certification_date: date,
    connector: MotiveConnector | None = None,
) -> dict[str, Any]:
    organization = resolve_scheduled_organization(session)
    client = connector or MotiveConnector(organization_id=organization.id)

    hos = _certify_resource(
        lambda: client._request_json(  # noqa: SLF001 - certification reuses the connector's hardened auth/retry path.
            HOS_ENDPOINT,
            params={
                "start_date": certification_date.isoformat(),
                "end_date": certification_date.isoformat(),
                "per_page": 5,
                "page_no": 1,
            },
            operation="assignment_signal_hos_certification",
        )
    )

    location = _certify_vehicle_location_schema(
        session,
        organization_id=organization.id,
        certification_date=certification_date,
        client=client,
    )

    return {
        "status": "certification_completed",
        "provider": "motive",
        "operation": "assignment_signal_schema_certification",
        "certification_date": certification_date.isoformat(),
        "resources": {
            "hours_of_service": hos,
            "vehicle_location": location,
        },
        "schema_values_returned": False,
        "raw_provider_payloads_returned": False,
        "driver_identity_values_returned": False,
        "vehicle_identity_values_returned": False,
        "coordinates_returned": False,
        "secrets_exposed": False,
    }


def _certify_vehicle_location_schema(
    session: Session,
    *,
    organization_id: str,
    certification_date: date,
    client: MotiveConnector,
) -> dict[str, Any]:
    stored_vehicles = (
        session.query(MotiveVehicleRecord)
        .filter(MotiveVehicleRecord.organization_id == organization_id)
        .order_by(MotiveVehicleRecord.id.asc())
        .limit(MAX_LOCATION_VEHICLES_TO_SAMPLE)
        .all()
    )
    if not stored_vehicles:
        return {
            "available": False,
            "error_code": "no_stored_vehicle",
            "provider_http_status": None,
            "observed_schema_paths": {},
            "vehicles_examined": 0,
            "lookback_days": LOCATION_LOOKBACK_DAYS,
            "non_empty_sample_found": False,
        }

    start_date = certification_date - timedelta(days=LOCATION_LOOKBACK_DAYS - 1)
    last_error: dict[str, Any] | None = None
    vehicles_examined = 0
    for stored_vehicle in stored_vehicles:
        vehicles_examined += 1
        endpoint = VEHICLE_LOCATION_ENDPOINT_TEMPLATE.format(vehicle_id=stored_vehicle.provider_vehicle_id)
        resource = _certify_resource(
            lambda endpoint=endpoint: client._request_json(  # noqa: SLF001 - hardened read path; provider id never returned.
                endpoint,
                params={
                    "start_date": start_date.isoformat(),
                    "end_date": certification_date.isoformat(),
                },
                operation="assignment_signal_vehicle_location_certification",
            )
        )
        if not resource["available"]:
            last_error = resource
            continue
        if _vehicle_location_payload_is_non_empty(resource):
            return {
                **resource,
                "vehicles_examined": vehicles_examined,
                "lookback_days": LOCATION_LOOKBACK_DAYS,
                "non_empty_sample_found": True,
            }

    if last_error is not None and vehicles_examined == len(stored_vehicles):
        return {
            **last_error,
            "vehicles_examined": vehicles_examined,
            "lookback_days": LOCATION_LOOKBACK_DAYS,
            "non_empty_sample_found": False,
        }

    return {
        "available": True,
        "error_code": None,
        "provider_http_status": 200,
        "observed_schema_paths": {
            "$": ["object"],
            "$.vehicle_locations": ["array"],
            "$.vehicle_locations[]": ["empty"],
        },
        "vehicles_examined": vehicles_examined,
        "lookback_days": LOCATION_LOOKBACK_DAYS,
        "non_empty_sample_found": False,
    }


def _vehicle_location_payload_is_non_empty(resource: dict[str, Any]) -> bool:
    observed = resource.get("observed_schema_paths")
    if not isinstance(observed, dict):
        return False
    item_types = observed.get("$.vehicle_locations[]")
    return isinstance(item_types, list) and any(item_type != "empty" for item_type in item_types)


def _certify_resource(fetcher) -> dict[str, Any]:
    try:
        payload = fetcher()
    except MotiveConnectorError as exc:
        return {
            "available": False,
            "error_code": exc.code,
            "provider_http_status": exc.http_status,
            "observed_schema_paths": {},
        }
    return {
        "available": True,
        "error_code": None,
        "provider_http_status": 200,
        "observed_schema_paths": _schema_paths(payload),
    }


def _schema_paths(value: Any) -> dict[str, list[str]]:
    observed: dict[str, set[str]] = {}
    _observe(value, path="$", depth=0, observed=observed)
    return {path: sorted(types) for path, types in sorted(observed.items())}


def _observe(value: Any, *, path: str, depth: int, observed: dict[str, set[str]]) -> None:
    observed.setdefault(path, set()).add(_type_name(value))
    if depth >= MAX_SCHEMA_DEPTH:
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and key:
                _observe(child, path=f"{path}.{key}", depth=depth + 1, observed=observed)
        return
    if isinstance(value, list):
        array_path = f"{path}[]"
        if not value:
            observed.setdefault(array_path, set()).add("empty")
            return
        for child in value[:MAX_ARRAY_ITEMS_TO_OBSERVE]:
            _observe(child, path=array_path, depth=depth + 1, observed=observed)


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "other"
