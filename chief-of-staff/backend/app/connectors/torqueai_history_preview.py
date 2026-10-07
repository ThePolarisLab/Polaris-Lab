"""Operator-only historical preview. No persistence, claims, or scheduler entry point."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date
import json
import os
from typing import Any

from sqlalchemy import event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import Select

from app.connectors.torqueai import (
    TORQUEAI_ORGANIZATION_SLUG_ENV, TorqueAIConnector, TorqueAIConnectorError,
    _coerce_date,
)
from app.connectors.torqueai_ingestion import (
    TORQUEAI_INGEST_MAX_PAGES, TORQUEAI_INGEST_MAX_ROWS, TORQUEAI_INGEST_PAGE_SIZE,
    TorqueAIDispatchIngestionError, _normalize_pages, _required_pages, _validate_window,
)
from app.connectors.torqueai_operational_ingestion import _operational_snapshot
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchOperational
from app.organizations.models import Organization

MOR_SLUG = "mor-logistics"


@contextmanager
def _select_only_connection(engine: Engine):
    """Own transaction, no ORM unit of work; rollback even on success/failure."""
    with engine.connect() as connection:
        with connection.begin() as transaction:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))

            def only_select(conn, cursor, statement, parameters, context, executemany):
                if not context.compiled or not isinstance(context.compiled.statement, Select):
                    raise TorqueAIDispatchIngestionError("readonly_violation", "Preview permits SELECT queries only")

            event.listen(connection, "before_cursor_execute", only_select)
            try:
                yield connection
            finally:
                transaction.rollback()
                event.remove(connection, "before_cursor_execute", only_select)


def preview_torqueai_history(
    engine: Engine, *, date_from: date, date_to: date,
    connector: TorqueAIConnector | None = None,
) -> dict[str, Any]:
    """Preview one bounded window for configured active MOR, using provider truth only.

    No caller-supplied tenant, session, workbook, persistence callback or write mode.
    Conflict identities are excluded from insert/update/unchanged classifications.
    """
    result: dict[str, Any] = {
        "status": "failed", "mode": "historical_preview", "provider": "torqueai",
        "request": {}, "provider_records_received": 0, "validated_records": 0,
        "would_insert": 0, "would_update": 0, "unchanged": 0,
        "identity_conflicts": 0, "missing_usable_lane_stops": 0, "identities": [],
        "pagination": {"page_size": TORQUEAI_INGEST_PAGE_SIZE, "pages_fetched": 0,
                       "provider_total_count": None, "pages": []},
        "returned_ship_dates": {"minimum": None, "maximum": None,
                                "outside_requested_window": 0, "missing_or_invalid": 0},
        "validation_failures": [], "database_writes": False, "provider_writes": False,
        "checkpoint_modified": False, "claims_modified": False,
        "raw_provider_payload_returned": False,
    }
    try:
        date_from = _coerce_date(date_from, "from")
        date_to = _coerce_date(date_to, "to")
        _validate_window(date_from, date_to)
        result["request"] = {"from": date_from.isoformat(), "to": date_to.isoformat()}
        if os.getenv(TORQUEAI_ORGANIZATION_SLUG_ENV, "").strip() != MOR_SLUG:
            raise TorqueAIDispatchIngestionError("organization_scope_mismatch", "Preview requires configured MOR scope")
        with _select_only_connection(engine) as connection:
            organization_id = connection.execute(select(Organization.id).where(
                Organization.slug == MOR_SLUG, Organization.status == "active",
            )).scalar_one_or_none()
            if organization_id is None:
                raise TorqueAIDispatchIngestionError("organization_scope_mismatch", "Preview requires active MOR tenant")
        provider = connector or TorqueAIConnector(organization_slug=MOR_SLUG)
        if provider.organization_slug != MOR_SLUG:
            raise TorqueAIDispatchIngestionError("organization_scope_mismatch", "Preview provider must use MOR scope")
        pages = []
        required_pages = 1
        for page_number in range(1, TORQUEAI_INGEST_MAX_PAGES + 1):
            page = provider.fetch_dispatches(date_from=date_from, date_to=date_to,
                                            page=page_number, limit=TORQUEAI_INGEST_PAGE_SIZE)
            pages.append(page)
            result["provider_records_received"] += len(page.data)
            pagination = result["pagination"]
            pagination["pages_fetched"] += 1
            pagination["pages"].append({"page": page.page, "records": len(page.data),
                                        "total_count": page.total_count, "items_per_page": page.items_per_page})
            if page_number == 1:
                pagination["provider_total_count"] = page.total_count
                required_pages = _required_pages(page)
                if page.total_count > TORQUEAI_INGEST_MAX_ROWS or required_pages > TORQUEAI_INGEST_MAX_PAGES:
                    raise TorqueAIDispatchIngestionError("ingestion_bound_exceeded", "Preview exceeds approved ingestion bounds")
            if (page.page != page_number or page.date_from != date_from or page.date_to != date_to
                    or page.total_count != pages[0].total_count
                    or page.items_per_page != pages[0].items_per_page
                    or not 1 <= page.items_per_page <= TORQUEAI_INGEST_PAGE_SIZE
                    or len(page.data) > page.items_per_page):
                raise TorqueAIDispatchIngestionError("provider_contract_error", "Preview pagination contract changed")
            if page_number == required_pages:
                break
        # Existing ingestion trims order identifiers. Refuse noncanonical input here
        # rather than silently present a guessed exact historical identity.
        if any(isinstance(raw.get("orderNumber"), str) and raw["orderNumber"] != raw["orderNumber"].strip()
               for page in pages for raw in page.data):
            raise TorqueAIDispatchIngestionError("identity_not_exact", "Preview order identity contains outer whitespace")
        normalized = _normalize_pages(pages)
        snapshots = [_operational_snapshot(raw, item.identity)
                     for raw, item in zip((raw for page in pages for raw in page.data), normalized)]
        result["validated_records"] = len(normalized)
        if len(normalized) != pages[0].total_count:
            raise TorqueAIDispatchIngestionError("provider_contract_error", "Preview row count differs from provider total")
        # Only selected scalar columns enter the preview; no ORM objects can become dirty.
        with _select_only_connection(engine) as connection:
            active_organization = connection.execute(select(Organization.id).where(
                Organization.id == organization_id, Organization.slug == MOR_SLUG,
                Organization.status == "active",
            )).scalar_one_or_none()
            if active_organization is None:
                raise TorqueAIDispatchIngestionError("organization_scope_mismatch", "MOR tenant became unavailable")
            rows = connection.execute(select(
                TorqueAIDispatch.provider_load_number, TorqueAIDispatch.provider_order_number,
                TorqueAIDispatch.source_fingerprint,
                TorqueAIDispatchOperational.source_fingerprint.label("operational_fingerprint"),
            ).outerjoin(TorqueAIDispatchOperational, (
                (TorqueAIDispatchOperational.dispatch_id == TorqueAIDispatch.id)
                & (TorqueAIDispatchOperational.organization_id == organization_id)
            )).where(TorqueAIDispatch.organization_id == organization_id,
                     TorqueAIDispatch.provider_load_number.in_([item.provider_load_number for item in normalized]))).all()
        existing = {(row[0], row[1]): (row[2], row[3]) for row in rows}
        orders: dict[str, set[str]] = {}
        for load, order in [*existing, *(item.identity for item in normalized)]:
            orders.setdefault(load, set()).add(order)
        ship_dates = []
        for item, snapshot in zip(normalized, snapshots):
            conflict = len(orders[item.provider_load_number]) > 1
            previous = existing.get(item.identity)
            classification = ("identity_conflict" if conflict else "would_insert" if previous is None
                              else "unchanged" if previous == (item.source_fingerprint, snapshot.source_fingerprint)
                              else "would_update")
            result["identity_conflicts" if conflict else classification] += 1
            usable_stops = _usable_lane_stops(snapshot.stops)
            result["missing_usable_lane_stops"] += int(not usable_stops)
            result["identities"].append({
                "provider_load_number": item.provider_load_number,
                "provider_order_number": item.provider_order_number,
                "classification": classification, "exact_identity_present": previous is not None,
                "conflicting_order_numbers": sorted(orders[item.provider_load_number]) if conflict else [],
                "missing_usable_lane_stops": not usable_stops,
            })
            try:
                ship_date = date.fromisoformat(item.ship_date_text or "")
                ship_dates.append(ship_date)
                result["returned_ship_dates"]["outside_requested_window"] += int(not date_from <= ship_date <= date_to)
            except ValueError:
                result["returned_ship_dates"]["missing_or_invalid"] += 1
        if ship_dates:
            result["returned_ship_dates"].update(minimum=min(ship_dates).isoformat(), maximum=max(ship_dates).isoformat())
        result["status"] = "success"
    except (TorqueAIConnectorError, TorqueAIDispatchIngestionError) as exc:
        result["validation_failures"] = [{"code": exc.code}]
    except SQLAlchemyError:
        result["validation_failures"] = [{"code": "database_read_failed"}]
    return result


def _usable_lane_stops(stops) -> bool:
    # Same literal roles used by durable analytics; no alias/customer inference.
    roles = {stop.values["job"].lower() for stop in stops
             if stop.values["job"] and all(stop.values[field] for field in ("city", "province", "country"))}
    return {"pick up", "drop off"}.issubset(roles)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only MOR TorqueAI historical preview")
    parser.add_argument("--from", dest="date_from", required=True)
    parser.add_argument("--to", dest="date_to", required=True)
    args = parser.parse_args()
    from app.database.database import engine
    result = preview_torqueai_history(engine, date_from=args.date_from, date_to=args.date_to)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
