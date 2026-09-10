"""Operational enrichment layered onto the certified TorqueAI ingestion path.

The provider is called only by the existing bounded connector. This module keeps
an explicit whitelist of production-certified fields and persists normalized
operational data in the same successful transaction as the base dispatch rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.connectors.torqueai import TorqueAIConnector, TorqueAIDispatchPage
from app.connectors.torqueai_ingestion import TorqueAIDispatchIngestionError, _normalize_dispatch, ingest_torqueai_dispatches as _ingest_base_dispatches
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchOperational, TorqueAIDispatchStop, TorqueAIDispatchSyncRun


@dataclass(frozen=True, slots=True)
class _StopSnapshot:
    stop_index: int
    values: dict[str, Any]
    source_fingerprint: str


@dataclass(frozen=True, slots=True)
class _OperationalSnapshot:
    provider_load_number: str
    provider_order_number: str
    currency: str | None
    total_charge: Decimal | None
    billing_currency: str | None
    billing_rate: Decimal | None
    billing_subtotal: Decimal | None
    billing_tax_amount: Decimal | None
    billing_total: Decimal | None
    stop_count: int | None
    stops: tuple[_StopSnapshot, ...]
    source_fingerprint: str

    @property
    def identity(self) -> tuple[str, str]:
        return self.provider_load_number, self.provider_order_number


class _OperationalCaptureConnector:
    def __init__(self, delegate: TorqueAIConnector) -> None:
        self._delegate = delegate
        self.snapshots: dict[tuple[str, str], _OperationalSnapshot] = {}

    def fetch_dispatches(self, **kwargs: Any) -> TorqueAIDispatchPage:
        page = self._delegate.fetch_dispatches(**kwargs)
        for raw in page.data:
            normalized = _normalize_dispatch(raw)
            snapshot = _operational_snapshot(raw, normalized.identity)
            if snapshot.identity in self.snapshots:
                raise TorqueAIDispatchIngestionError("provider_duplicate_identity", "TorqueAI returned a duplicate provisional dispatch identity")
            self.snapshots[snapshot.identity] = snapshot
        return page


def ingest_torqueai_dispatches(
    session: Session,
    *,
    organization_id: str,
    organization_slug: str,
    date_from: date,
    date_to: date,
    connector: TorqueAIConnector | None = None,
    claimed_run_id: str | None = None,
) -> dict[str, Any]:
    """Run base ingestion plus certified operational enrichment with no extra provider call."""
    provider = connector or TorqueAIConnector(organization_slug=organization_slug)
    capture = _OperationalCaptureConnector(provider)
    existing_base_fingerprints = {
        (row.provider_load_number, row.provider_order_number): row.source_fingerprint
        for row in session.query(TorqueAIDispatch).filter(TorqueAIDispatch.organization_id == organization_id).all()
    }
    adjustment = {"operational_only_updates": 0}

    def apply_enrichment_before_success_commit(active_session: Session) -> None:
        success_run = _pending_success_run(active_session, organization_id=organization_id, date_from=date_from, date_to=date_to, claimed_run_id=claimed_run_id)
        if success_run is None:
            return

        active_session.flush()
        now = datetime.now(timezone.utc)
        base_rows = {
            (row.provider_load_number, row.provider_order_number): row
            for row in active_session.query(TorqueAIDispatch).filter(TorqueAIDispatch.organization_id == organization_id).all()
        }
        existing_enrichment = {
            row.dispatch_id: row
            for row in active_session.query(TorqueAIDispatchOperational).filter(TorqueAIDispatchOperational.organization_id == organization_id).all()
        }

        operational_only_updates = 0
        for identity, snapshot in capture.snapshots.items():
            dispatch = base_rows.get(identity)
            if dispatch is None:
                raise TorqueAIDispatchIngestionError("database_write_failed", "TorqueAI operational enrichment dispatch identity was not persisted")

            enrichment = existing_enrichment.get(dispatch.id)
            previous_fingerprint = enrichment.source_fingerprint if enrichment is not None else None
            changed = previous_fingerprint != snapshot.source_fingerprint
            enrichment_values = {
                "currency": snapshot.currency,
                "total_charge": snapshot.total_charge,
                "billing_currency": snapshot.billing_currency,
                "billing_rate": snapshot.billing_rate,
                "billing_subtotal": snapshot.billing_subtotal,
                "billing_tax_amount": snapshot.billing_tax_amount,
                "billing_total": snapshot.billing_total,
                "stop_count": snapshot.stop_count,
            }

            if enrichment is None:
                enrichment = TorqueAIDispatchOperational(
                    organization_id=organization_id,
                    dispatch_id=dispatch.id,
                    source_fingerprint=snapshot.source_fingerprint,
                    first_observed_at=now,
                    last_changed_at=now,
                    **enrichment_values,
                )
                active_session.add(enrichment)
                existing_enrichment[dispatch.id] = enrichment
            elif changed:
                for key, value in enrichment_values.items():
                    setattr(enrichment, key, value)
                enrichment.source_fingerprint = snapshot.source_fingerprint
                enrichment.last_changed_at = now

            if changed:
                _replace_stops(active_session, organization_id=organization_id, dispatch=dispatch, snapshots=snapshot.stops, observed_at=now)

            if not changed or identity not in existing_base_fingerprints:
                continue
            if dispatch.source_fingerprint == existing_base_fingerprints[identity]:
                dispatch.last_changed_at = now
                operational_only_updates += 1

        if operational_only_updates:
            success_run.rows_updated += operational_only_updates
            success_run.rows_unchanged -= operational_only_updates
            adjustment["operational_only_updates"] = operational_only_updates

    event.listen(session, "before_commit", apply_enrichment_before_success_commit)
    try:
        result = _ingest_base_dispatches(
            session,
            organization_id=organization_id,
            organization_slug=organization_slug,
            date_from=date_from,
            date_to=date_to,
            connector=capture,
            claimed_run_id=claimed_run_id,
        )
    finally:
        if event.contains(session, "before_commit", apply_enrichment_before_success_commit):
            event.remove(session, "before_commit", apply_enrichment_before_success_commit)

    count = adjustment["operational_only_updates"]
    if count:
        result = dict(result)
        result["rows_updated"] = int(result["rows_updated"]) + count
        result["rows_unchanged"] = int(result["rows_unchanged"]) - count
    return result


def _replace_stops(session: Session, *, organization_id: str, dispatch: TorqueAIDispatch, snapshots: tuple[_StopSnapshot, ...], observed_at: datetime) -> None:
    existing_first_observed = {
        row.stop_index: row.first_observed_at
        for row in session.query(TorqueAIDispatchStop).filter(
            TorqueAIDispatchStop.organization_id == organization_id,
            TorqueAIDispatchStop.dispatch_id == dispatch.id,
        ).all()
    }
    session.query(TorqueAIDispatchStop).filter(
        TorqueAIDispatchStop.organization_id == organization_id,
        TorqueAIDispatchStop.dispatch_id == dispatch.id,
    ).delete(synchronize_session=False)
    for stop in snapshots:
        session.add(TorqueAIDispatchStop(
            organization_id=organization_id,
            dispatch_id=dispatch.id,
            stop_index=stop.stop_index,
            source_fingerprint=stop.source_fingerprint,
            first_observed_at=existing_first_observed.get(stop.stop_index, observed_at),
            last_changed_at=observed_at,
            **stop.values,
        ))


def _pending_success_run(session: Session, *, organization_id: str, date_from: date, date_to: date, claimed_run_id: str | None) -> TorqueAIDispatchSyncRun | None:
    for item in list(session.new) + list(session.dirty):
        if not isinstance(item, TorqueAIDispatchSyncRun):
            continue
        if item.organization_id != organization_id or item.status != "success":
            continue
        if item.requested_from != date_from or item.requested_to != date_to:
            continue
        if claimed_run_id is not None and item.run_id != claimed_run_id:
            continue
        return item
    return None


def _operational_snapshot(raw: dict[str, Any], identity: tuple[str, str]) -> _OperationalSnapshot:
    stops_raw = raw.get("stops")
    if stops_raw is None:
        stop_snapshots: tuple[_StopSnapshot, ...] = ()
        stop_count = None
    elif isinstance(stops_raw, list):
        stop_snapshots = tuple(_stop_snapshot(stop, index) for index, stop in enumerate(stops_raw))
        stop_count = len(stops_raw)
    else:
        raise _contract_error("stops")

    billing = raw.get("billing")
    if billing is None:
        billing = {}
    if not isinstance(billing, dict):
        raise _contract_error("billing")

    values = {
        "currency": _optional_text(raw.get("currency"), 12),
        "total_charge": _optional_decimal(raw.get("totalCharge"), "total charge"),
        "billing_currency": _optional_text(billing.get("currency"), 12),
        "billing_rate": _optional_decimal(billing.get("rate"), "billing rate"),
        "billing_subtotal": _optional_decimal(billing.get("subTotal"), "billing subtotal"),
        "billing_tax_amount": _optional_decimal(billing.get("taxAmount"), "billing tax amount"),
        "billing_total": _optional_decimal(billing.get("total"), "billing total"),
        "stop_count": stop_count,
    }
    canonical = {key: _canonical_value(value) for key, value in values.items()}
    canonical["stops"] = [{"index": stop.stop_index, "fingerprint": stop.source_fingerprint} for stop in stop_snapshots]
    fingerprint = _fingerprint(canonical)
    return _OperationalSnapshot(provider_load_number=identity[0], provider_order_number=identity[1], stops=stop_snapshots, source_fingerprint=fingerprint, **values)


def _stop_snapshot(raw: Any, index: int) -> _StopSnapshot:
    if not isinstance(raw, dict):
        raise _contract_error("stop")
    scheduled = raw.get("scheduled")
    if scheduled is None:
        scheduled = {}
    if not isinstance(scheduled, dict):
        raise _contract_error("scheduled stop")

    values = {
        "sequence": _optional_decimal(raw.get("sequence"), "stop sequence"),
        "stop_no": _optional_text(raw.get("stopNo"), 120),
        "job": _optional_text(raw.get("job"), 120),
        "name": _optional_text(raw.get("name"), 255),
        "address": _optional_text(raw.get("address"), 500),
        "city": _optional_text(raw.get("city"), 255),
        "province": _optional_text(raw.get("province"), 120),
        "country": _optional_text(raw.get("country"), 120),
        "zip_code": _optional_text(raw.get("zipCode"), 40),
        "latitude": _optional_decimal(raw.get("latitude"), "stop latitude"),
        "longitude": _optional_decimal(raw.get("longitude"), "stop longitude"),
        "commodity": _optional_text(raw.get("commodity"), 500),
        "notes": _optional_text(raw.get("notes"), 2000),
        "driver_name": _optional_text(raw.get("driverName"), 255),
        "co_driver_name": _optional_text(raw.get("coDriverName"), 255),
        "carrier_name": _optional_text(raw.get("carrierName"), 255),
        "truck_number": _optional_text(raw.get("truckNumber"), 120),
        "trailer_number": _optional_text(raw.get("trailerNumber"), 120),
        "scheduled_is_window": _optional_bool(scheduled.get("isWindow")),
        "scheduled_pickup_date_text": _optional_text(scheduled.get("pickupDate"), 120),
        "scheduled_pickup_date2_text": _optional_text(scheduled.get("pickupDate2"), 120),
        "scheduled_pickup_time_text": _optional_text(scheduled.get("pickupTime"), 120),
        "scheduled_pickup_time2_text": _optional_text(scheduled.get("pickupTime2"), 120),
        "temperature_text": _optional_mixed_scalar(raw.get("temperature"), 255),
        "temperature_unit": _optional_text(raw.get("temperatureUnit"), 40),
        "weight": _optional_decimal(raw.get("weight"), "stop weight"),
        "weight_unit": _optional_text(raw.get("weightUnit"), 40),
    }
    return _StopSnapshot(stop_index=index, values=values, source_fingerprint=_fingerprint({key: _canonical_value(value) for key, value in values.items()}))


def _optional_text(value: Any, maximum_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _contract_error("text")
    normalized = value.strip()
    if len(normalized) > maximum_length:
        raise TorqueAIDispatchIngestionError("provider_contract_error", "TorqueAI certified operational text field exceeded its bound")
    return normalized


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise _contract_error("boolean")
    return value


def _optional_mixed_scalar(value: Any, maximum_length: int) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise _contract_error("mixed scalar")
    text = str(value).strip()
    if len(text) > maximum_length:
        raise TorqueAIDispatchIngestionError("provider_contract_error", "TorqueAI certified mixed operational field exceeded its bound")
    return text


def _optional_decimal(value: Any, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise _contract_error(field_name)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise TorqueAIDispatchIngestionError("provider_contract_error", f"TorqueAI certified {field_name} field was invalid") from exc
    if not result.is_finite():
        raise TorqueAIDispatchIngestionError("provider_contract_error", f"TorqueAI certified {field_name} field was invalid")
    return result


def _contract_error(_field: str) -> TorqueAIDispatchIngestionError:
    return TorqueAIDispatchIngestionError("provider_contract_error", "TorqueAI certified operational field had an invalid type")


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    return value


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()
