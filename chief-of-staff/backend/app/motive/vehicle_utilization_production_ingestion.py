"""Bounded production ingestion for Motive vehicle-utilization rollups.

This is the first runtime production-ingestion gate certified by
``MOTIVE_UTILIZATION_PRODUCTION_INGESTION_GATE_DESIGN.md`` and the subsequent
provider timezone/unit clarification. It is deliberately narrow:

* disabled by default;
* latest seven completed ``America/Chicago`` calendar days only;
* at most 100 organization-owned vehicles;
* exactly one provider page/call per day (maximum seven calls per run);
* explicit ``X-Metric-Units: false`` / US Imperial request mode;
* returned ``vehicle.metric_units`` must be ``False`` or the existing writer
  fails closed;
* one durable writer transaction per day;
* one sanitized sync-history row per orchestrated run;
* checkpoint advances only on an all-seven-day success, atomically with the
  history row;
* no scheduler, cron, retry loop, Dashboard, Daily Brief, or key rotation.

Provider omissions remain omissions only. They are never synthesized as zero
utilization or inactivity.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import logging
import os
import threading
from typing import Callable, Iterator
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.connectors.motive import MotiveConnectorError
from app.connectors.motive_vehicle_utilization import (
    MotiveVehicleUtilizationParseError,
    MotiveVehicleUtilizationRequestContext,
    parse_vehicle_utilization_rollups,
)
from app.connectors.motive_vehicle_utilization_pagination import (
    MOTIVE_VEHICLE_UTILIZATION_PAGINATION_CANONICAL_WRITER_PAGE_SIZE,
    MotiveVehicleUtilizationPaginationError,
    parse_pagination_metadata,
    request_vehicle_utilization_page,
)
from app.database.database import SessionLocal
from app.models.motive import MotiveSyncCheckpoint, MotiveSyncHistory, MotiveVehicleRecord
from app.motive.vehicle_utilization_unit_policy import MotiveVehicleUtilizationUnitRequestMode
from app.motive.vehicle_utilization_writer import (
    MotiveVehicleUtilizationWriterError,
    write_vehicle_utilization_transaction,
)

logger = logging.getLogger(__name__)

RESOURCE = "vehicle_utilization"
RUN_MODE = "production_recent_window_ingestion"
PRODUCTION_INGESTION_ENABLED_ENV_VAR = "MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED"
PRODUCTION_SCHEDULER_ENABLED_ENV_VAR = "MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED"
PRODUCTION_TIME_ZONE = "America/Chicago"
PRODUCTION_HORIZON_DAYS = 7
PRODUCTION_MAX_VEHICLES = 100
PRODUCTION_MAX_PROVIDER_CALLS = 7
PRODUCTION_PAGE_SIZE = MOTIVE_VEHICLE_UTILIZATION_PAGINATION_CANONICAL_WRITER_PAGE_SIZE
PRODUCTION_UNIT_REQUEST_MODE = MotiveVehicleUtilizationUnitRequestMode.IMPERIAL
PRODUCTION_FUEL_UNIT = "gallons"
CHECKPOINT_RESOURCE = "vehicle_utilization"
LOCK_RESOURCE = "vehicle_utilization_production_lock"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}

# Process-local exclusion provides deterministic fail-fast behavior in tests
# and within one worker. The database row lock below is the cross-process /
# cross-instance guard in production.
_PROCESS_LOCKS: dict[str, threading.Lock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()


class MotiveVehicleUtilizationProductionIngestionError(RuntimeError):
    """Sanitized production-ingestion failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class FailedProductionWindow:
    window_start: str
    window_end: str
    error_code: str


@dataclass(frozen=True, slots=True)
class ProductionIngestionResult:
    status: str
    resource: str
    run_mode: str
    horizon_days: int
    request_timezone: str
    unit_request_mode: str
    fuel_unit: str
    x_metric_units: bool
    selected_vehicle_count: int
    windows_attempted: int
    windows_completed: int
    windows_failed: int
    provider_calls_attempted: int
    provider_calls_completed: int
    rollups_returned: int
    missing_requested_vehicle_count: int
    records_inserted: int
    records_unchanged: int
    records_updated: int
    reconciled_fields_count: int
    checkpoint_advanced: bool
    sync_history_written: bool
    scheduled_ingestion_enabled: bool = False
    secrets_exposed: bool = False
    failed_units: tuple[FailedProductionWindow, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "resource": self.resource,
            "run_mode": self.run_mode,
            "horizon_days": self.horizon_days,
            "request_timezone": self.request_timezone,
            "unit_request_mode": self.unit_request_mode,
            "fuel_unit": self.fuel_unit,
            "x_metric_units": self.x_metric_units,
            "selected_vehicle_count": self.selected_vehicle_count,
            "windows_attempted": self.windows_attempted,
            "windows_completed": self.windows_completed,
            "windows_failed": self.windows_failed,
            "provider_calls_attempted": self.provider_calls_attempted,
            "provider_calls_completed": self.provider_calls_completed,
            "rollups_returned": self.rollups_returned,
            "missing_requested_vehicle_count": self.missing_requested_vehicle_count,
            "records_inserted": self.records_inserted,
            "records_unchanged": self.records_unchanged,
            "records_updated": self.records_updated,
            "reconciled_fields_count": self.reconciled_fields_count,
            "checkpoint_advanced": self.checkpoint_advanced,
            "sync_history_written": self.sync_history_written,
            "scheduled_ingestion_enabled": False,
            "secrets_exposed": False,
            "failed_units": [
                {
                    "window_start": unit.window_start,
                    "window_end": unit.window_end,
                    "error_code": unit.error_code,
                }
                for unit in self.failed_units
            ],
        }


def production_ingestion_enabled() -> bool:
    value = os.getenv(PRODUCTION_INGESTION_ENABLED_ENV_VAR)
    return value is not None and value.strip().lower() in _TRUTHY_ENV_VALUES


def production_scheduler_enabled() -> bool:
    """Configuration visibility only; no scheduler exists in this gate."""
    value = os.getenv(PRODUCTION_SCHEDULER_ENABLED_ENV_VAR)
    return value is not None and value.strip().lower() in _TRUTHY_ENV_VALUES


def _latest_completed_day() -> date:
    return datetime.now(ZoneInfo(PRODUCTION_TIME_ZONE)).date() - timedelta(days=1)


def _day_windows(*, end_date: date | None = None) -> list[tuple[date, date]]:
    resolved_end = end_date or _latest_completed_day()
    return [
        (resolved_end - timedelta(days=offset), resolved_end - timedelta(days=offset))
        for offset in range(PRODUCTION_HORIZON_DAYS - 1, -1, -1)
    ]


def _select_provider_vehicle_ids(session: Session, organization_id: str) -> list[str]:
    rows = (
        session.query(MotiveVehicleRecord)
        .filter(MotiveVehicleRecord.organization_id == organization_id)
        .order_by(MotiveVehicleRecord.id.asc())
        .limit(PRODUCTION_MAX_VEHICLES + 1)
        .all()
    )
    if len(rows) > PRODUCTION_MAX_VEHICLES:
        raise MotiveVehicleUtilizationProductionIngestionError(
            "production_vehicle_limit_exceeded",
            "Motive vehicle-utilization production ingestion supports at most 100 eligible vehicles in this gate.",
        )
    if not rows:
        raise MotiveVehicleUtilizationProductionIngestionError(
            "no_eligible_vehicles",
            "Motive vehicle-utilization production ingestion found no eligible stored vehicles.",
        )
    provider_ids: list[str] = []
    for row in rows:
        if not isinstance(row.provider_vehicle_id, str) or not row.provider_vehicle_id.strip():
            raise MotiveVehicleUtilizationProductionIngestionError(
                "invalid_stored_vehicle_identity",
                "A stored Motive vehicle did not contain a valid provider identity.",
            )
        provider_ids.append(row.provider_vehicle_id)
    if len(set(provider_ids)) != len(provider_ids):
        raise MotiveVehicleUtilizationProductionIngestionError(
            "duplicate_stored_vehicle_identity",
            "Stored Motive vehicle identities were not unique for the organization.",
        )
    return provider_ids


def _read_one_production_page(
    *,
    organization_id: str,
    organization_slug: str,
    provider_vehicle_ids: list[str],
    window_start: date,
    window_end: date,
):
    """Make exactly one provider request and fail closed if page 2 would be needed."""
    payload, _status = request_vehicle_utilization_page(
        organization_id=organization_id,
        provider_vehicle_ids=provider_vehicle_ids,
        start_date=window_start,
        end_date=window_end,
        page_no=1,
        per_page=PRODUCTION_PAGE_SIZE,
        unit_request_mode=PRODUCTION_UNIT_REQUEST_MODE,
    )
    metadata = parse_pagination_metadata(payload, expected_page_no=1, expected_per_page=PRODUCTION_PAGE_SIZE)
    if metadata.total > PRODUCTION_PAGE_SIZE:
        raise MotiveVehicleUtilizationPaginationError(
            "production_pagination_requires_second_page",
            "Motive vehicle-utilization production response would require more than the one authorized page.",
        )
    try:
        rollups = parse_vehicle_utilization_rollups(
            payload,
            organization_id=organization_id,
            organization_slug=organization_slug,
            request_context=MotiveVehicleUtilizationRequestContext(
                request_start_date=window_start,
                request_end_date=window_end,
            ),
        )
    except MotiveVehicleUtilizationParseError as exc:
        raise MotiveVehicleUtilizationPaginationError(
            exc.code,
            "Motive vehicle-utilization production response did not match the certified provider schema.",
        ) from exc

    if len(rollups) != metadata.total:
        raise MotiveVehicleUtilizationPaginationError(
            "production_pagination_total_mismatch",
            "Motive vehicle-utilization production page item count did not match pagination.total.",
        )
    selected = set(provider_vehicle_ids)
    seen: set[str] = set()
    for rollup in rollups:
        if rollup.provider_vehicle_id in seen:
            raise MotiveVehicleUtilizationPaginationError(
                "duplicate_vehicle_observed",
                "Motive vehicle-utilization production response returned a duplicate vehicle rollup.",
            )
        seen.add(rollup.provider_vehicle_id)
        if rollup.provider_vehicle_id not in selected:
            raise MotiveVehicleUtilizationPaginationError(
                "unexpected_vehicle_observed",
                "Motive vehicle-utilization production response returned a vehicle outside the selected set.",
            )
    return rollups


def _checkpoint_snapshot(session: Session, organization_id: str) -> dict[str, object]:
    row = (
        session.query(MotiveSyncCheckpoint)
        .filter(
            MotiveSyncCheckpoint.organization_id == organization_id,
            MotiveSyncCheckpoint.provider_resource == CHECKPOINT_RESOURCE,
        )
        .one_or_none()
    )
    if row is None:
        return {"status": "not_started", "completed_through": None}
    position = row.last_successful_position if isinstance(row.last_successful_position, dict) else {}
    return {
        "status": row.checkpoint_status,
        "completed_through": position.get("completed_through"),
        "request_timezone": position.get("request_timezone"),
        "unit_request_mode": position.get("unit_request_mode"),
    }


def _persist_history_and_checkpoint(
    session: Session,
    *,
    organization_id: str,
    organization_slug: str,
    started_at: datetime,
    result_status: str,
    selected_vehicle_count: int,
    windows_attempted: int,
    windows_completed: int,
    windows_failed: int,
    provider_calls_attempted: int,
    provider_calls_completed: int,
    rollups_returned: int,
    missing_requested_vehicle_count: int,
    records_inserted: int,
    records_unchanged: int,
    records_updated: int,
    reconciled_fields_count: int,
    failed_units: tuple[FailedProductionWindow, ...],
    checkpoint_before: dict[str, object],
    completed_through: date,
) -> tuple[bool, bool]:
    """Persist exactly one history row; checkpoint is atomic with it on success."""
    completed_at = datetime.now(timezone.utc)
    all_success = result_status == "success"
    checkpoint_after = dict(checkpoint_before)
    if all_success:
        checkpoint_after = {
            "status": "success",
            "completed_through": completed_through.isoformat(),
            "request_timezone": PRODUCTION_TIME_ZONE,
            "unit_request_mode": PRODUCTION_UNIT_REQUEST_MODE.value,
        }

    first_error = failed_units[0].error_code if failed_units else None
    history = MotiveSyncHistory(
        organization_id=organization_id,
        organization_slug=organization_slug,
        provider="motive",
        provider_resource=RESOURCE,
        mode=RUN_MODE,
        status="partial" if result_status == "partial_success" else result_status,
        run_id=f"motive-util-prod-{uuid4().hex}",
        started_at=started_at,
        completed_at=completed_at,
        records_read=rollups_returned,
        records_written=records_inserted + records_updated,
        error_code=first_error,
        error_message_sanitized=(
            None if result_status == "success" else "One or more bounded vehicle-utilization production windows failed."
        ),
        checkpoint_before=checkpoint_before,
        checkpoint_after=checkpoint_after,
        resource_counts={
            "horizon_days": PRODUCTION_HORIZON_DAYS,
            "request_timezone": PRODUCTION_TIME_ZONE,
            "unit_request_mode": PRODUCTION_UNIT_REQUEST_MODE.value,
            "fuel_unit": PRODUCTION_FUEL_UNIT,
            "x_metric_units": False,
            "selected_vehicle_count": selected_vehicle_count,
            "windows_attempted": windows_attempted,
            "windows_completed": windows_completed,
            "windows_failed": windows_failed,
            "provider_calls_attempted": provider_calls_attempted,
            "provider_calls_completed": provider_calls_completed,
            "rollups_returned": rollups_returned,
            "missing_requested_vehicle_count": missing_requested_vehicle_count,
            "records_inserted": records_inserted,
            "records_unchanged": records_unchanged,
            "records_updated": records_updated,
            "reconciled_fields_count": reconciled_fields_count,
            "failed_unit_count": len(failed_units),
            "checkpoint_advanced": all_success,
            "scheduled_ingestion_enabled": False,
            "secrets_exposed": False,
        },
    )

    try:
        session.add(history)
        if all_success:
            checkpoint = (
                session.query(MotiveSyncCheckpoint)
                .filter(
                    MotiveSyncCheckpoint.organization_id == organization_id,
                    MotiveSyncCheckpoint.provider_resource == CHECKPOINT_RESOURCE,
                )
                .one_or_none()
            )
            if checkpoint is None:
                checkpoint = MotiveSyncCheckpoint(
                    organization_id=organization_id,
                    organization_slug=organization_slug,
                    provider="motive",
                    provider_resource=CHECKPOINT_RESOURCE,
                )
                session.add(checkpoint)
            checkpoint.organization_slug = organization_slug
            checkpoint.cursor = None
            checkpoint.page_number = None
            checkpoint.updated_after_watermark = completed_through.isoformat()
            checkpoint.last_successful_position = {
                "completed_through": completed_through.isoformat(),
                "request_timezone": PRODUCTION_TIME_ZONE,
                "unit_request_mode": PRODUCTION_UNIT_REQUEST_MODE.value,
                "fuel_unit": PRODUCTION_FUEL_UNIT,
            }
            checkpoint.checkpoint_status = "success"
            checkpoint.last_successful_sync_at = completed_at
        # History and success checkpoint become durable in the same final
        # metadata transaction. Any failure rolls both back, so checkpoint
        # can never advance without its parent history row.
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise MotiveVehicleUtilizationProductionIngestionError(
            "production_metadata_persistence_failed",
            "Motive vehicle-utilization production run metadata could not be persisted.",
        ) from exc
    return True, all_success


def _process_lock(organization_id: str) -> threading.Lock:
    with _PROCESS_LOCKS_GUARD:
        return _PROCESS_LOCKS.setdefault(organization_id, threading.Lock())


def _ensure_lock_anchor(lock_session: Session, *, organization_id: str, organization_slug: str) -> None:
    existing = (
        lock_session.query(MotiveSyncCheckpoint)
        .filter(
            MotiveSyncCheckpoint.organization_id == organization_id,
            MotiveSyncCheckpoint.provider_resource == LOCK_RESOURCE,
        )
        .one_or_none()
    )
    if existing is not None:
        return
    lock_session.add(
        MotiveSyncCheckpoint(
            organization_id=organization_id,
            organization_slug=organization_slug,
            provider="motive",
            provider_resource=LOCK_RESOURCE,
            checkpoint_status="lock_anchor",
            last_successful_position={},
        )
    )
    try:
        lock_session.commit()
    except IntegrityError:
        # Another process may have created the same unique anchor between the
        # query and insert. Roll back and continue to row-lock that anchor.
        lock_session.rollback()
    except SQLAlchemyError as exc:
        lock_session.rollback()
        raise MotiveVehicleUtilizationProductionIngestionError(
            "production_lock_database_error",
            "Motive vehicle-utilization production lock could not be prepared.",
        ) from exc


def _is_lock_not_available(exc: OperationalError) -> bool:
    original = getattr(exc, "orig", None)
    code = getattr(original, "pgcode", None) or getattr(original, "sqlstate", None)
    if code == "55P03":
        return True
    return "locked" in str(original).lower() if original is not None else False


@contextmanager
def _organization_run_lock(
    *,
    organization_id: str,
    organization_slug: str,
    lock_session_factory: Callable[[], Session] = SessionLocal,
) -> Iterator[None]:
    process_lock = _process_lock(organization_id)
    if not process_lock.acquire(blocking=False):
        raise MotiveVehicleUtilizationProductionIngestionError(
            "production_run_already_in_progress",
            "A Motive vehicle-utilization production run is already in progress for this organization.",
        )

    lock_session = lock_session_factory()
    try:
        _ensure_lock_anchor(lock_session, organization_id=organization_id, organization_slug=organization_slug)
        try:
            (
                lock_session.query(MotiveSyncCheckpoint)
                .filter(
                    MotiveSyncCheckpoint.organization_id == organization_id,
                    MotiveSyncCheckpoint.provider_resource == LOCK_RESOURCE,
                )
                .with_for_update(nowait=True)
                .one()
            )
        except OperationalError as exc:
            lock_session.rollback()
            if _is_lock_not_available(exc):
                raise MotiveVehicleUtilizationProductionIngestionError(
                    "production_run_already_in_progress",
                    "A Motive vehicle-utilization production run is already in progress for this organization.",
                ) from exc
            raise MotiveVehicleUtilizationProductionIngestionError(
                "production_lock_database_error",
                "Motive vehicle-utilization production lock could not be acquired.",
            ) from exc
        except SQLAlchemyError as exc:
            lock_session.rollback()
            raise MotiveVehicleUtilizationProductionIngestionError(
                "production_lock_database_error",
                "Motive vehicle-utilization production lock could not be acquired.",
            ) from exc
        yield
    finally:
        # Releasing/rolling back the dedicated lock transaction releases the
        # PostgreSQL row lock. This session never performs utilization writes.
        try:
            lock_session.rollback()
        finally:
            lock_session.close()
            process_lock.release()


def run_vehicle_utilization_production_ingestion(
    session: Session,
    *,
    organization_id: str,
    organization_slug: str,
    lock_session_factory: Callable[[], Session] = SessionLocal,
    end_date: date | None = None,
) -> ProductionIngestionResult:
    """Run one bounded seven-day production ingestion attempt."""
    if not production_ingestion_enabled():
        raise MotiveVehicleUtilizationProductionIngestionError(
            "production_ingestion_disabled",
            "Motive vehicle-utilization production ingestion is disabled.",
        )
    if not isinstance(organization_id, str) or not organization_id.strip():
        raise MotiveVehicleUtilizationProductionIngestionError(
            "invalid_organization_context", "Production ingestion requires an organization context."
        )
    if not isinstance(organization_slug, str) or not organization_slug.strip():
        raise MotiveVehicleUtilizationProductionIngestionError(
            "invalid_organization_context", "Production ingestion requires an organization context."
        )

    started_at = datetime.now(timezone.utc)
    with _organization_run_lock(
        organization_id=organization_id,
        organization_slug=organization_slug,
        lock_session_factory=lock_session_factory,
    ):
        checkpoint_before = _checkpoint_snapshot(session, organization_id)
        try:
            provider_vehicle_ids = _select_provider_vehicle_ids(session, organization_id)
        except MotiveVehicleUtilizationProductionIngestionError as exc:
            # Preflight failures still get one sanitized history row when the
            # metadata layer is available, while making zero provider calls.
            failed = (
                FailedProductionWindow(window_start="", window_end="", error_code=exc.code),
            )
            _persist_history_and_checkpoint(
                session,
                organization_id=organization_id,
                organization_slug=organization_slug,
                started_at=started_at,
                result_status="failed",
                selected_vehicle_count=0,
                windows_attempted=0,
                windows_completed=0,
                windows_failed=0,
                provider_calls_attempted=0,
                provider_calls_completed=0,
                rollups_returned=0,
                missing_requested_vehicle_count=0,
                records_inserted=0,
                records_unchanged=0,
                records_updated=0,
                reconciled_fields_count=0,
                failed_units=failed,
                checkpoint_before=checkpoint_before,
                completed_through=end_date or _latest_completed_day(),
            )
            raise

        windows = _day_windows(end_date=end_date)
        if len(windows) != PRODUCTION_HORIZON_DAYS or len(windows) > PRODUCTION_MAX_PROVIDER_CALLS:
            raise MotiveVehicleUtilizationProductionIngestionError(
                "production_call_budget_invariant_violated",
                "Motive vehicle-utilization production call budget invariant was violated before provider access.",
            )

        windows_completed = 0
        provider_calls_attempted = 0
        provider_calls_completed = 0
        rollups_returned = 0
        missing_requested_vehicle_count = 0
        records_inserted = 0
        records_unchanged = 0
        records_updated = 0
        reconciled_fields_count = 0
        failed_units: list[FailedProductionWindow] = []

        known_failures = (
            MotiveConnectorError,
            MotiveVehicleUtilizationPaginationError,
            MotiveVehicleUtilizationWriterError,
        )

        try:
            for window_start, window_end in windows:
                provider_calls_attempted += 1
                try:
                    rollups = _read_one_production_page(
                        organization_id=organization_id,
                        organization_slug=organization_slug,
                        provider_vehicle_ids=provider_vehicle_ids,
                        window_start=window_start,
                        window_end=window_end,
                    )
                    provider_calls_completed += 1
                    write_result = write_vehicle_utilization_transaction(
                        session,
                        organization_id=organization_id,
                        organization_slug=organization_slug,
                        selected_provider_vehicle_ids=provider_vehicle_ids,
                        request_window_start=window_start,
                        request_window_end=window_end,
                        rollups=rollups,
                        unit_request_mode=PRODUCTION_UNIT_REQUEST_MODE,
                    )
                    windows_completed += 1
                    rollups_returned += write_result.returned_rollup_count
                    missing_requested_vehicle_count += write_result.missing_requested_vehicle_count
                    records_inserted += write_result.records_inserted
                    records_unchanged += write_result.records_unchanged
                    records_updated += write_result.records_updated
                    reconciled_fields_count += write_result.reconciled_fields_count
                except known_failures as exc:
                    failed_units.append(
                        FailedProductionWindow(
                            window_start=window_start.isoformat(),
                            window_end=window_end.isoformat(),
                            error_code=getattr(exc, "code", "production_window_failed"),
                        )
                    )
                    continue
        except Exception as exc:
            logger.exception(
                "MOTIVE VEHICLE UTILIZATION PRODUCTION INGESTION UNEXPECTED FAILURE",
                extra={"motive_operation": RUN_MODE, "organization_id": organization_id},
            )
            # Daily writer commits that completed before this unexpected
            # failure remain durable; checkpoint does not advance.
            failed_units.append(
                FailedProductionWindow(window_start="", window_end="", error_code="unexpected_error")
            )
            _persist_history_and_checkpoint(
                session,
                organization_id=organization_id,
                organization_slug=organization_slug,
                started_at=started_at,
                result_status="partial_success" if windows_completed else "failed",
                selected_vehicle_count=len(provider_vehicle_ids),
                windows_attempted=provider_calls_attempted,
                windows_completed=windows_completed,
                windows_failed=max(0, provider_calls_attempted - windows_completed),
                provider_calls_attempted=provider_calls_attempted,
                provider_calls_completed=provider_calls_completed,
                rollups_returned=rollups_returned,
                missing_requested_vehicle_count=missing_requested_vehicle_count,
                records_inserted=records_inserted,
                records_unchanged=records_unchanged,
                records_updated=records_updated,
                reconciled_fields_count=reconciled_fields_count,
                failed_units=tuple(failed_units),
                checkpoint_before=checkpoint_before,
                completed_through=windows[-1][1],
            )
            raise MotiveVehicleUtilizationProductionIngestionError(
                "unexpected_error", "Motive vehicle-utilization production ingestion failed unexpectedly."
            ) from exc

        windows_failed = len(failed_units)
        if windows_completed == PRODUCTION_HORIZON_DAYS and windows_failed == 0:
            result_status = "success"
        elif windows_completed > 0:
            result_status = "partial_success"
        else:
            result_status = "failed"

        history_written, checkpoint_advanced = _persist_history_and_checkpoint(
            session,
            organization_id=organization_id,
            organization_slug=organization_slug,
            started_at=started_at,
            result_status=result_status,
            selected_vehicle_count=len(provider_vehicle_ids),
            windows_attempted=len(windows),
            windows_completed=windows_completed,
            windows_failed=windows_failed,
            provider_calls_attempted=provider_calls_attempted,
            provider_calls_completed=provider_calls_completed,
            rollups_returned=rollups_returned,
            missing_requested_vehicle_count=missing_requested_vehicle_count,
            records_inserted=records_inserted,
            records_unchanged=records_unchanged,
            records_updated=records_updated,
            reconciled_fields_count=reconciled_fields_count,
            failed_units=tuple(failed_units),
            checkpoint_before=checkpoint_before,
            completed_through=windows[-1][1],
        )

        result = ProductionIngestionResult(
            status=result_status,
            resource=RESOURCE,
            run_mode=RUN_MODE,
            horizon_days=PRODUCTION_HORIZON_DAYS,
            request_timezone=PRODUCTION_TIME_ZONE,
            unit_request_mode=PRODUCTION_UNIT_REQUEST_MODE.value,
            fuel_unit=PRODUCTION_FUEL_UNIT,
            x_metric_units=False,
            selected_vehicle_count=len(provider_vehicle_ids),
            windows_attempted=len(windows),
            windows_completed=windows_completed,
            windows_failed=windows_failed,
            provider_calls_attempted=provider_calls_attempted,
            provider_calls_completed=provider_calls_completed,
            rollups_returned=rollups_returned,
            missing_requested_vehicle_count=missing_requested_vehicle_count,
            records_inserted=records_inserted,
            records_unchanged=records_unchanged,
            records_updated=records_updated,
            reconciled_fields_count=reconciled_fields_count,
            checkpoint_advanced=checkpoint_advanced,
            sync_history_written=history_written,
            failed_units=tuple(failed_units),
        )
        logger.info(
            "MOTIVE VEHICLE UTILIZATION PRODUCTION INGESTION COMPLETE",
            extra={
                "motive_operation": RUN_MODE,
                "organization_id": organization_id,
                "status": result.status,
                "windows_completed": result.windows_completed,
                "windows_failed": result.windows_failed,
                "provider_calls_attempted": result.provider_calls_attempted,
                "provider_calls_completed": result.provider_calls_completed,
                "checkpoint_advanced": result.checkpoint_advanced,
            },
        )
        return result
