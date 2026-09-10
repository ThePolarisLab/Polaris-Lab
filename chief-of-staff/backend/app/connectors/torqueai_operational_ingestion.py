"""Operational enrichment layered onto the certified TorqueAI ingestion path.

This module reuses the existing provider calls and base dispatch transaction. It
captures only explicitly approved top-level provider fields and writes them to a
separate one-to-one enrichment table during the same successful database commit.
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
from app.connectors.torqueai_ingestion import (
    TORQUEAI_INGEST_PAGE_SIZE,
    TorqueAIDispatchIngestionError,
    _normalize_dispatch,
    ingest_torqueai_dispatches as _ingest_base_dispatches,
)
from app.models.torqueai import (
    TorqueAIDispatch,
    TorqueAIDispatchOperational,
    TorqueAIDispatchSyncRun,
)


@dataclass(frozen=True, slots=True)
class _OperationalSnapshot:
    provider_load_number: str
    provider_order_number: str
    currency: str | None
    total_charge: Decimal | None
    stop_count: int | None
    source_fingerprint: str

    @property
    def identity(self) -> tuple[str, str]:
        return self.provider_load_number, self.provider_order_number


class _OperationalCaptureConnector:
    """Delegate provider access while validating/capturing approved extra fields."""

    def __init__(self, delegate: TorqueAIConnector) -> None:
        self._delegate = delegate
        self.snapshots: dict[tuple[str, str], _OperationalSnapshot] = {}

    def fetch_dispatches(self, **kwargs: Any) -> TorqueAIDispatchPage:
        page = self._delegate.fetch_dispatches(**kwargs)
        for raw in page.data:
            # Reuse the certified base normalizer so operational validation cannot
            # accept a record that the durable base ingestion would later reject.
            normalized = _normalize_dispatch(raw)
            snapshot = _operational_snapshot(raw, normalized.identity)
            if snapshot.identity in self.snapshots:
                raise TorqueAIDispatchIngestionError(
                    "provider_duplicate_identity",
                    "TorqueAI returned a duplicate provisional dispatch identity",
                )
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
    """Run certified ingestion plus approved enrichment with no extra provider call."""
    provider = connector or TorqueAIConnector(organization_slug=organization_slug)
    capture = _OperationalCaptureConnector(provider)

    existing_base_fingerprints = {
        (row.provider_load_number, row.provider_order_number): row.source_fingerprint
        for row in session.query(TorqueAIDispatch)
        .filter(TorqueAIDispatch.organization_id == organization_id)
        .all()
    }
    adjustment = {"operational_only_updates": 0}

    def apply_enrichment_before_success_commit(active_session: Session) -> None:
        success_run = _pending_success_run(
            active_session,
            organization_id=organization_id,
            date_from=date_from,
            date_to=date_to,
            claimed_run_id=claimed_run_id,
        )
        if success_run is None:
            # Failed-run history commits must never persist partial enrichment.
            return

        active_session.flush()
        now = datetime.now(timezone.utc)
        base_rows = {
            (row.provider_load_number, row.provider_order_number): row
            for row in active_session.query(TorqueAIDispatch)
            .filter(TorqueAIDispatch.organization_id == organization_id)
            .all()
        }
        existing_enrichment = {
            row.dispatch_id: row
            for row in active_session.query(TorqueAIDispatchOperational)
            .filter(TorqueAIDispatchOperational.organization_id == organization_id)
            .all()
        }

        operational_only_updates = 0
        for identity, snapshot in capture.snapshots.items():
            dispatch = base_rows.get(identity)
            if dispatch is None:
                # The base ingestion validated the same identity set, so absence
                # here indicates an internal persistence invariant failure.
                raise RuntimeError("TorqueAI operational enrichment dispatch identity missing after flush")

            enrichment = existing_enrichment.get(dispatch.id)
            previous_operational_fingerprint = enrichment.source_fingerprint if enrichment is not None else None
            operational_changed = previous_operational_fingerprint != snapshot.source_fingerprint

            if enrichment is None:
                enrichment = TorqueAIDispatchOperational(
                    organization_id=organization_id,
                    dispatch_id=dispatch.id,
                    currency=snapshot.currency,
                    total_charge=snapshot.total_charge,
                    stop_count=snapshot.stop_count,
                    source_fingerprint=snapshot.source_fingerprint,
                    first_observed_at=now,
                    last_changed_at=now,
                )
                active_session.add(enrichment)
                existing_enrichment[dispatch.id] = enrichment
            elif operational_changed:
                enrichment.currency = snapshot.currency
                enrichment.total_charge = snapshot.total_charge
                enrichment.stop_count = snapshot.stop_count
                enrichment.source_fingerprint = snapshot.source_fingerprint
                enrichment.last_changed_at = now

            if not operational_changed or identity not in existing_base_fingerprints:
                continue

            base_changed = dispatch.source_fingerprint != existing_base_fingerprints[identity]
            if not base_changed:
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

    operational_only_updates = adjustment["operational_only_updates"]
    if operational_only_updates:
        result = dict(result)
        result["rows_updated"] = int(result["rows_updated"]) + operational_only_updates
        result["rows_unchanged"] = int(result["rows_unchanged"]) - operational_only_updates
    return result


def _pending_success_run(
    session: Session,
    *,
    organization_id: str,
    date_from: date,
    date_to: date,
    claimed_run_id: str | None,
) -> TorqueAIDispatchSyncRun | None:
    candidates = list(session.new) + list(session.dirty)
    for item in candidates:
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
    approved = {
        "currency": _optional_text(raw.get("currency"), maximum_length=12),
        "total_charge": _optional_decimal(raw.get("totalCharge"), field_name="total charge"),
        "stop_count": _optional_stop_count(raw.get("stops")),
    }
    canonical = {
        key: _canonical_value(value)
        for key, value in approved.items()
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode("utf-8")
    ).hexdigest()
    return _OperationalSnapshot(
        provider_load_number=identity[0],
        provider_order_number=identity[1],
        source_fingerprint=fingerprint,
        **approved,
    )


def _optional_text(value: Any, *, maximum_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TorqueAIDispatchIngestionError(
            "provider_contract_error",
            "TorqueAI certified operational text field had an invalid type",
        )
    normalized = value.strip()
    if len(normalized) > maximum_length:
        raise TorqueAIDispatchIngestionError(
            "provider_contract_error",
            "TorqueAI certified operational text field exceeded its bound",
        )
    return normalized


def _optional_decimal(value: Any, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise TorqueAIDispatchIngestionError(
            "provider_contract_error",
            f"TorqueAI certified {field_name} field had an invalid type",
        )
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise TorqueAIDispatchIngestionError(
            "provider_contract_error",
            f"TorqueAI certified {field_name} field was invalid",
        ) from exc
    if not result.is_finite():
        raise TorqueAIDispatchIngestionError(
            "provider_contract_error",
            f"TorqueAI certified {field_name} field was invalid",
        )
    return result


def _optional_stop_count(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise TorqueAIDispatchIngestionError(
            "provider_contract_error",
            "TorqueAI certified stops field had an invalid type",
        )
    return len(value)


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    return value
