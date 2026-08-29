"""Bounded manual TorqueAI dispatch ingestion into durable tenant-scoped storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import logging
from math import ceil
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.connectors.torqueai import TorqueAIConnector, TorqueAIConnectorError, TorqueAIDispatchPage
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchSyncRun, TorqueAIDispatchSyncState

logger = logging.getLogger(__name__)

TORQUEAI_INGEST_PAGE_SIZE = 100
TORQUEAI_INGEST_MAX_PAGES = 10
TORQUEAI_INGEST_MAX_ROWS = 1000
TORQUEAI_INGEST_MAX_RANGE_DAYS = 7


class TorqueAIDispatchIngestionError(RuntimeError):
    """Sanitized ingestion error with no provider record values."""

    def __init__(self, code: str, message: str, *, provider_http_status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.provider_http_status = provider_http_status
        self.retryable = False


@dataclass(frozen=True, slots=True)
class _NormalizedDispatch:
    provider_load_number: str
    provider_order_number: str
    status: str | None
    order_date_text: str | None
    ship_date_text: str | None
    delivery_date_text: str | None
    customer_name: str | None
    dispatcher_name: str | None
    driver_name: str | None
    carrier_name: str | None
    truck_number: str | None
    trailer_number: str | None
    loaded_miles: Decimal | None
    source_fingerprint: str

    @property
    def identity(self) -> tuple[str, str]:
        return self.provider_load_number, self.provider_order_number


def ingest_torqueai_dispatches(
    session: Session,
    *,
    organization_id: str,
    organization_slug: str,
    date_from: date,
    date_to: date,
    connector: TorqueAIConnector | None = None,
) -> dict[str, Any]:
    """Fetch all bounded pages, validate them, then atomically persist minimized rows."""
    _validate_window(date_from, date_to)
    run_id = f"torqueai-{uuid4().hex}"
    started_at = datetime.now(timezone.utc)
    provider = connector or TorqueAIConnector(organization_slug=organization_slug)
    pages_fetched = 0
    provider_total_count: int | None = None
    rows_validated = 0

    logger.info(
        "TORQUEAI DISPATCH INGEST START",
        extra={
            "torqueai_run_id": run_id,
            "organization_id": organization_id,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
    )

    try:
        first_page = provider.fetch_dispatches(
            date_from=date_from,
            date_to=date_to,
            page=1,
            limit=TORQUEAI_INGEST_PAGE_SIZE,
        )
        pages_fetched = 1
        provider_total_count = first_page.total_count
        required_pages = _required_pages(first_page)
        if provider_total_count > TORQUEAI_INGEST_MAX_ROWS or required_pages > TORQUEAI_INGEST_MAX_PAGES:
            raise TorqueAIDispatchIngestionError(
                "ingestion_bound_exceeded",
                "TorqueAI dispatch result exceeds the approved ingestion bound",
            )

        pages = [first_page]
        for page_number in range(2, required_pages + 1):
            page = provider.fetch_dispatches(
                date_from=date_from,
                date_to=date_to,
                page=page_number,
                limit=TORQUEAI_INGEST_PAGE_SIZE,
            )
            pages_fetched += 1
            if page.total_count != provider_total_count or page.items_per_page != first_page.items_per_page:
                raise TorqueAIDispatchIngestionError(
                    "provider_contract_error",
                    "TorqueAI pagination contract changed within the ingestion run",
                )
            pages.append(page)

        normalized = _normalize_pages(pages)
        rows_validated = len(normalized)
        if rows_validated != provider_total_count:
            raise TorqueAIDispatchIngestionError(
                "provider_contract_error",
                "TorqueAI pagination did not produce the certified total row count",
            )
    except TorqueAIConnectorError as exc:
        _record_failed_run(
            session,
            run_id=run_id,
            organization_id=organization_id,
            date_from=date_from,
            date_to=date_to,
            started_at=started_at,
            pages_fetched=pages_fetched,
            provider_total_count=provider_total_count,
            rows_validated=rows_validated,
            error_code=exc.code,
        )
        raise TorqueAIDispatchIngestionError(
            exc.code,
            "TorqueAI dispatch ingestion failed",
            provider_http_status=exc.http_status,
        ) from exc
    except TorqueAIDispatchIngestionError as exc:
        _record_failed_run(
            session,
            run_id=run_id,
            organization_id=organization_id,
            date_from=date_from,
            date_to=date_to,
            started_at=started_at,
            pages_fetched=pages_fetched,
            provider_total_count=provider_total_count,
            rows_validated=rows_validated,
            error_code=exc.code,
        )
        raise

    observed_at = datetime.now(timezone.utc)
    inserted = 0
    updated = 0
    unchanged = 0
    try:
        existing = {
            (row.provider_load_number, row.provider_order_number): row
            for row in session.query(TorqueAIDispatch)
            .filter(TorqueAIDispatch.organization_id == organization_id)
            .all()
        }

        for item in normalized:
            row = existing.get(item.identity)
            if row is None:
                row = TorqueAIDispatch(
                    organization_id=organization_id,
                    first_observed_at=observed_at,
                    last_changed_at=observed_at,
                    **_persisted_values(item),
                )
                session.add(row)
                existing[item.identity] = row
                inserted += 1
                continue

            if row.source_fingerprint == item.source_fingerprint:
                unchanged += 1
                continue

            for field, value in _persisted_values(item).items():
                setattr(row, field, value)
            row.last_changed_at = observed_at
            updated += 1

        completed_at = datetime.now(timezone.utc)
        session.add(
            TorqueAIDispatchSyncRun(
                run_id=run_id,
                organization_id=organization_id,
                requested_from=date_from,
                requested_to=date_to,
                page_size=TORQUEAI_INGEST_PAGE_SIZE,
                status="success",
                pages_fetched=pages_fetched,
                provider_total_count=provider_total_count,
                rows_validated=rows_validated,
                rows_inserted=inserted,
                rows_updated=updated,
                rows_unchanged=unchanged,
                error_code=None,
                started_at=started_at,
                completed_at=completed_at,
            )
        )
        state = (
            session.query(TorqueAIDispatchSyncState)
            .filter(TorqueAIDispatchSyncState.organization_id == organization_id)
            .one_or_none()
        )
        if state is None:
            state = TorqueAIDispatchSyncState(
                organization_id=organization_id,
                last_successful_window_start=date_from,
                last_successful_window_end=date_to,
                last_successful_run_id=run_id,
                last_successful_completed_at=completed_at,
            )
            session.add(state)
        else:
            state.last_successful_window_start = date_from
            state.last_successful_window_end = date_to
            state.last_successful_run_id = run_id
            state.last_successful_completed_at = completed_at

        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise TorqueAIDispatchIngestionError(
            "database_write_failed",
            "TorqueAI dispatch persistence transaction failed",
        ) from exc

    logger.info(
        "TORQUEAI DISPATCH INGEST SUCCESS",
        extra={
            "torqueai_run_id": run_id,
            "organization_id": organization_id,
            "pages_fetched": pages_fetched,
            "rows_validated": rows_validated,
            "rows_inserted": inserted,
            "rows_updated": updated,
            "rows_unchanged": unchanged,
        },
    )
    return {
        "status": "success",
        "provider": "torqueai",
        "request": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "pages_fetched": pages_fetched,
        "provider_total_count": provider_total_count,
        "rows_validated": rows_validated,
        "rows_inserted": inserted,
        "rows_updated": updated,
        "rows_unchanged": unchanged,
        "tenant_scope_validated": True,
        "raw_dispatches_returned": False,
        "secrets_exposed": False,
    }


def _validate_window(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise TorqueAIDispatchIngestionError("invalid_request", "TorqueAI from date must not be after to date")
    if (date_to - date_from).days + 1 > TORQUEAI_INGEST_MAX_RANGE_DAYS:
        raise TorqueAIDispatchIngestionError("invalid_request", "TorqueAI ingestion range must not exceed 7 days")


def _required_pages(page: TorqueAIDispatchPage) -> int:
    if page.items_per_page < 1:
        raise TorqueAIDispatchIngestionError("provider_contract_error", "TorqueAI page size was invalid")
    return max(1, ceil(page.total_count / page.items_per_page))


def _normalize_pages(pages: list[TorqueAIDispatchPage]) -> list[_NormalizedDispatch]:
    normalized: list[_NormalizedDispatch] = []
    seen: set[tuple[str, str]] = set()
    for page in pages:
        for raw in page.data:
            item = _normalize_dispatch(raw)
            if item.identity in seen:
                raise TorqueAIDispatchIngestionError(
                    "provider_duplicate_identity",
                    "TorqueAI returned a duplicate provisional dispatch identity",
                )
            seen.add(item.identity)
            normalized.append(item)
    return normalized


def _normalize_dispatch(raw: dict[str, Any]) -> _NormalizedDispatch:
    load_number = raw.get("loadNumber")
    if isinstance(load_number, bool) or not isinstance(load_number, int):
        raise TorqueAIDispatchIngestionError("provider_contract_error", "TorqueAI dispatch identity was malformed")
    order_number = raw.get("orderNumber")
    if not isinstance(order_number, str) or not order_number.strip() or len(order_number.strip()) > 255:
        raise TorqueAIDispatchIngestionError("provider_contract_error", "TorqueAI dispatch identity was malformed")

    approved = {
        "provider_load_number": str(load_number),
        "provider_order_number": order_number.strip(),
        "status": _optional_text(raw.get("status"), 120),
        "order_date_text": _optional_text(raw.get("orderDate"), 120),
        "ship_date_text": _optional_text(raw.get("shipDate"), 120),
        "delivery_date_text": _optional_text(raw.get("deliveryDate"), 120),
        "customer_name": _optional_text(raw.get("customerName"), 255),
        "dispatcher_name": _optional_text(raw.get("dispatcherName"), 255),
        "driver_name": _optional_text(raw.get("driverName"), 255),
        "carrier_name": _optional_text(raw.get("carrierName"), 255),
        "truck_number": _optional_text(raw.get("truckNumber"), 120),
        "trailer_number": _optional_text(raw.get("trailerNumber"), 120),
        "loaded_miles": _optional_decimal(raw.get("loadedMiles")),
    }
    fingerprint_payload = {
        key: _canonical_value(value)
        for key, value in approved.items()
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode("utf-8")
    ).hexdigest()
    return _NormalizedDispatch(**approved, source_fingerprint=fingerprint)


def _optional_text(value: Any, maximum_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TorqueAIDispatchIngestionError("provider_contract_error", "TorqueAI approved text field had an invalid type")
    normalized = value.strip()
    if len(normalized) > maximum_length:
        raise TorqueAIDispatchIngestionError("provider_contract_error", "TorqueAI approved text field exceeded its bound")
    return normalized


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise TorqueAIDispatchIngestionError("provider_contract_error", "TorqueAI loaded miles had an invalid type")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise TorqueAIDispatchIngestionError("provider_contract_error", "TorqueAI loaded miles was invalid") from exc
    if not result.is_finite() or result < 0:
        raise TorqueAIDispatchIngestionError("provider_contract_error", "TorqueAI loaded miles was invalid")
    return result


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    return value


def _persisted_values(item: _NormalizedDispatch) -> dict[str, Any]:
    return {
        "provider_load_number": item.provider_load_number,
        "provider_order_number": item.provider_order_number,
        "status": item.status,
        "order_date_text": item.order_date_text,
        "ship_date_text": item.ship_date_text,
        "delivery_date_text": item.delivery_date_text,
        "customer_name": item.customer_name,
        "dispatcher_name": item.dispatcher_name,
        "driver_name": item.driver_name,
        "carrier_name": item.carrier_name,
        "truck_number": item.truck_number,
        "trailer_number": item.trailer_number,
        "loaded_miles": item.loaded_miles,
        "source_fingerprint": item.source_fingerprint,
    }


def _record_failed_run(
    session: Session,
    *,
    run_id: str,
    organization_id: str,
    date_from: date,
    date_to: date,
    started_at: datetime,
    pages_fetched: int,
    provider_total_count: int | None,
    rows_validated: int,
    error_code: str,
) -> None:
    session.rollback()
    try:
        session.add(
            TorqueAIDispatchSyncRun(
                run_id=run_id,
                organization_id=organization_id,
                requested_from=date_from,
                requested_to=date_to,
                page_size=TORQUEAI_INGEST_PAGE_SIZE,
                status="failed",
                pages_fetched=pages_fetched,
                provider_total_count=provider_total_count,
                rows_validated=rows_validated,
                rows_inserted=0,
                rows_updated=0,
                rows_unchanged=0,
                error_code=error_code,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
    except SQLAlchemyError:
        session.rollback()
