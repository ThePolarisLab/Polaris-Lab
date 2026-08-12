"""Internal parser for Motive vehicle utilization rollups.

This module is intentionally side-effect free except for the read-only vehicle
association query. It does not call Motive, persist utilization, or advance
checkpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import logging
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.connectors.motive_contracts import MOTIVE_PROVIDER
from app.connectors.motive_vehicle_utilization_contract import MOTIVE_VEHICLE_UTILIZATION_ENDPOINT
from app.models.motive import MotiveVehicleRecord

logger = logging.getLogger(__name__)

PARSER_VERSION = "motive_vehicle_idle_rollup_v1"
_CONTAINER_KEY = "vehicle_idle_rollups"
_WRAPPER_KEY = "vehicle_idle_rollup"
_METRIC_KEYS = ("utilization", "idle_time", "driving_time", "idle_fuel", "driving_fuel")
_UNSAFE_SOURCE_KEY_MARKERS = ("token", "secret", "authorization", "api_key", "x-api-key")
_UNSAFE_SOURCE_KEYS = {"vin", "number", "license_plate", "license_plate_number", "vehicle_number", "plate"}


@dataclass(frozen=True, slots=True)
class MotiveVehicleUtilizationRequestContext:
    """Request dates are context only until Motive confirms period semantics."""

    request_start_date: date | None = None
    request_end_date: date | None = None


@dataclass(frozen=True, slots=True)
class MotiveVehicleUtilizationRollup:
    organization_id: str
    organization_slug: str
    provider_vehicle_id: str
    source_endpoint: str = MOTIVE_VEHICLE_UTILIZATION_ENDPOINT
    provider: str = MOTIVE_PROVIDER
    utilization_percent: Decimal | None = None
    idle_time: Decimal | None = None
    driving_time: Decimal | None = None
    idle_fuel: Decimal | None = None
    driving_fuel: Decimal | None = None
    metric_units: bool | None = None
    request_start_date: date | None = None
    request_end_date: date | None = None
    source_keys: tuple[str, ...] = ()
    parser_version: str = PARSER_VERSION


@dataclass(frozen=True, slots=True)
class MotiveVehicleUtilizationAssociation:
    outcome: Literal["matched", "unknown_vehicle"]
    rollup: MotiveVehicleUtilizationRollup
    motive_vehicle_id: int | None = None


class MotiveVehicleUtilizationParseError(ValueError):
    """Safe parse error that never includes provider values or raw payloads."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_vehicle_utilization_rollups(
    payload: Any,
    *,
    organization_id: str,
    organization_slug: str,
    request_context: MotiveVehicleUtilizationRequestContext | None = None,
) -> list[MotiveVehicleUtilizationRollup]:
    if not isinstance(payload, dict):
        raise MotiveVehicleUtilizationParseError("invalid_envelope", "Motive vehicle utilization response must be an object.")
    raw_items = payload.get(_CONTAINER_KEY)
    if raw_items is None:
        raise MotiveVehicleUtilizationParseError("missing_container", "Motive vehicle utilization response did not include vehicle rollups.")
    if not isinstance(raw_items, list):
        raise MotiveVehicleUtilizationParseError("invalid_container", "Motive vehicle utilization rollups must be a list.")

    context = request_context or MotiveVehicleUtilizationRequestContext()
    rollups = [
        _parse_rollup(raw, organization_id=organization_id, organization_slug=organization_slug, request_context=context)
        for raw in raw_items
    ]
    logger.info(
        "MOTIVE VEHICLE UTILIZATION PARSE",
        extra={"motive_operation": "vehicle_utilization_parse", "resource": "vehicle_utilization", "count": len(rollups), "outcome": "parsed"},
    )
    return rollups


def associate_vehicle_utilization_rollup(
    session: Session,
    *,
    organization_id: str,
    rollup: MotiveVehicleUtilizationRollup,
) -> MotiveVehicleUtilizationAssociation:
    with session.no_autoflush:
        vehicle = (
            session.query(MotiveVehicleRecord)
            .filter(
                MotiveVehicleRecord.organization_id == organization_id,
                MotiveVehicleRecord.provider_vehicle_id == rollup.provider_vehicle_id,
            )
            .one_or_none()
        )
    outcome: Literal["matched", "unknown_vehicle"] = "matched" if vehicle is not None else "unknown_vehicle"
    logger.info(
        "MOTIVE VEHICLE UTILIZATION ASSOCIATION",
        extra={"motive_operation": "vehicle_utilization_association", "resource": "vehicle_utilization", "outcome": outcome},
    )
    return MotiveVehicleUtilizationAssociation(outcome=outcome, rollup=rollup, motive_vehicle_id=vehicle.id if vehicle else None)


def associate_vehicle_utilization_rollups(
    session: Session,
    *,
    organization_id: str,
    rollups: list[MotiveVehicleUtilizationRollup],
) -> list[MotiveVehicleUtilizationAssociation]:
    return [associate_vehicle_utilization_rollup(session, organization_id=organization_id, rollup=rollup) for rollup in rollups]


def _parse_rollup(
    raw: Any,
    *,
    organization_id: str,
    organization_slug: str,
    request_context: MotiveVehicleUtilizationRequestContext,
) -> MotiveVehicleUtilizationRollup:
    if not isinstance(raw, dict):
        raise MotiveVehicleUtilizationParseError("invalid_item", "Motive vehicle utilization rollup must be an object.")
    wrapped = raw.get(_WRAPPER_KEY)
    if wrapped is None:
        raise MotiveVehicleUtilizationParseError("missing_wrapper", "Motive vehicle utilization rollup wrapper is missing.")
    if not isinstance(wrapped, dict):
        raise MotiveVehicleUtilizationParseError("invalid_wrapper", "Motive vehicle utilization rollup wrapper must be an object.")

    vehicle = wrapped.get("vehicle")
    if not isinstance(vehicle, dict):
        raise MotiveVehicleUtilizationParseError("missing_vehicle", "Motive vehicle utilization rollup did not include vehicle metadata.")
    provider_vehicle_id = _provider_vehicle_id(vehicle.get("id"))
    metrics = {key: _decimal_metric(wrapped.get(key), metric_name=key) for key in _METRIC_KEYS}
    return MotiveVehicleUtilizationRollup(
        organization_id=organization_id,
        organization_slug=organization_slug,
        provider_vehicle_id=provider_vehicle_id,
        utilization_percent=metrics["utilization"],
        idle_time=metrics["idle_time"],
        driving_time=metrics["driving_time"],
        idle_fuel=metrics["idle_fuel"],
        driving_fuel=metrics["driving_fuel"],
        metric_units=vehicle.get("metric_units") if isinstance(vehicle.get("metric_units"), bool) else None,
        request_start_date=request_context.request_start_date,
        request_end_date=request_context.request_end_date,
        source_keys=_source_keys(wrapped),
    )


def _provider_vehicle_id(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        raise MotiveVehicleUtilizationParseError("missing_vehicle_id", "Motive vehicle utilization rollup did not include a vehicle identity.")
    if isinstance(value, (dict, list, tuple, set)):
        raise MotiveVehicleUtilizationParseError("invalid_vehicle_id", "Motive vehicle utilization rollup included an invalid vehicle identity.")
    text = str(value).strip()
    if not text:
        raise MotiveVehicleUtilizationParseError("missing_vehicle_id", "Motive vehicle utilization rollup did not include a vehicle identity.")
    return text


def _decimal_metric(value: Any, *, metric_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise MotiveVehicleUtilizationParseError("invalid_metric_type", "Motive vehicle utilization metric had an invalid type.")
    if isinstance(value, (dict, list, tuple, set)):
        raise MotiveVehicleUtilizationParseError("invalid_metric_type", "Motive vehicle utilization metric had an invalid type.")
    if isinstance(value, str):
        if not value.strip():
            raise MotiveVehicleUtilizationParseError("invalid_metric_type", "Motive vehicle utilization metric had an invalid type.")
        candidate = value.strip()
    elif isinstance(value, (int, float, Decimal)):
        candidate = str(value)
    else:
        raise MotiveVehicleUtilizationParseError("invalid_metric_type", "Motive vehicle utilization metric had an invalid type.")
    try:
        parsed = Decimal(candidate)
    except InvalidOperation as exc:
        raise MotiveVehicleUtilizationParseError("invalid_metric_type", "Motive vehicle utilization metric had an invalid type.") from exc
    if not parsed.is_finite():
        raise MotiveVehicleUtilizationParseError("invalid_metric_type", "Motive vehicle utilization metric had an invalid type.")
    return parsed


def _source_keys(item: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(key for key in (str(raw_key) for raw_key in item.keys()) if _safe_source_key(key)))


def _safe_source_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _UNSAFE_SOURCE_KEYS:
        return False
    return not any(marker in lowered for marker in _UNSAFE_SOURCE_KEY_MARKERS)
