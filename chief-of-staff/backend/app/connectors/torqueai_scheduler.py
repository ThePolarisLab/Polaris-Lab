"""Disabled-by-default scheduled TorqueAI dispatch synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import os
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.connectors.torqueai import TORQUEAI_ORGANIZATION_SLUG_ENV
from app.connectors.torqueai_ingestion import (
    TORQUEAI_INGEST_PAGE_SIZE,
    TorqueAIDispatchIngestionError,
    ingest_torqueai_dispatches,
)
from app.models.torqueai import TorqueAIDispatchSyncRun
from app.organizations.models import Organization, OrganizationStatus

SCHEDULED_SYNC_ENABLED_ENV_VAR = "POLARIS_TORQUEAI_SCHEDULED_SYNC_ENABLED"
SCHEDULED_ORGANIZATION_ENV_VAR = "POLARIS_TORQUEAI_SCHEDULED_ORGANIZATION_SLUG"
TRIGGER_MODE = "scheduled"


class TorqueAIScheduledSyncError(RuntimeError):
    """Sanitized scheduler configuration or durable-claim failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ScheduledTorqueAISyncResult:
    status: str
    trigger_slot: str
    date_from: str
    date_to: str
    dispatch_claimed: bool
    scheduler_enabled: bool
    pages_fetched: int | None = None
    provider_total_count: int | None = None
    rows_validated: int | None = None
    rows_inserted: int | None = None
    rows_updated: int | None = None
    rows_unchanged: int | None = None
    error_code: str | None = None
    tenant_scope_validated: bool = False

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status,
            "provider": "torqueai",
            "trigger_mode": TRIGGER_MODE,
            "trigger_slot": self.trigger_slot,
            "request": {"from": self.date_from, "to": self.date_to},
            "dispatch_claimed": self.dispatch_claimed,
            "scheduler_enabled": self.scheduler_enabled,
            "tenant_scope_validated": self.tenant_scope_validated,
            "raw_dispatches_returned": False,
            "secrets_exposed": False,
        }
        for key, value in (
            ("pages_fetched", self.pages_fetched),
            ("provider_total_count", self.provider_total_count),
            ("rows_validated", self.rows_validated),
            ("rows_inserted", self.rows_inserted),
            ("rows_updated", self.rows_updated),
            ("rows_unchanged", self.rows_unchanged),
        ):
            if value is not None:
                payload[key] = value
        if self.error_code is not None:
            payload["error_code"] = self.error_code
        return payload


def scheduled_sync_enabled() -> bool:
    return str(os.getenv(SCHEDULED_SYNC_ENABLED_ENV_VAR) or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def resolve_scheduled_organization(session: Session) -> Organization:
    slug = str(os.getenv(SCHEDULED_ORGANIZATION_ENV_VAR) or "").strip()
    if not slug:
        raise TorqueAIScheduledSyncError(
            "missing_organization_configuration",
            "TorqueAI scheduled organization is not configured.",
        )
    try:
        organization = (
            session.query(Organization)
            .filter(
                Organization.slug == slug,
                Organization.status == OrganizationStatus.ACTIVE.value,
            )
            .one_or_none()
        )
    except SQLAlchemyError as exc:
        session.rollback()
        raise TorqueAIScheduledSyncError(
            "organization_lookup_failed",
            "TorqueAI scheduled organization lookup failed.",
        ) from exc
    if organization is None:
        raise TorqueAIScheduledSyncError(
            "organization_not_found",
            "TorqueAI scheduled organization was not found.",
        )
    return organization


def validate_connector_organization_scope(organization_slug: str) -> None:
    configured_slug = str(os.getenv(TORQUEAI_ORGANIZATION_SLUG_ENV) or "").strip()
    if not configured_slug:
        raise TorqueAIScheduledSyncError(
            "organization_not_configured",
            "TorqueAI connector organization scope is not configured.",
        )
    if configured_slug != organization_slug:
        raise TorqueAIScheduledSyncError(
            "organization_scope_mismatch",
            "TorqueAI connector organization scope does not match the scheduled organization.",
        )


def _slot_and_window(trigger_timestamp: int) -> tuple[str, date, date]:
    if isinstance(trigger_timestamp, bool) or not isinstance(trigger_timestamp, int) or trigger_timestamp < 0:
        raise TorqueAIScheduledSyncError("invalid_trigger_timestamp", "TorqueAI trigger timestamp is invalid.")
    try:
        triggered_at = datetime.fromtimestamp(trigger_timestamp, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise TorqueAIScheduledSyncError("invalid_trigger_timestamp", "TorqueAI trigger timestamp is invalid.") from exc
    slot = triggered_at.replace(minute=0, second=0, microsecond=0)
    date_to = triggered_at.date()
    date_from = date_to - timedelta(days=6)
    return slot.strftime("%Y-%m-%dT%H:00:00Z"), date_from, date_to


def _claim_scheduled_run(
    session: Session,
    *,
    organization: Organization,
    trigger_slot: str,
    date_from: date,
    date_to: date,
) -> str | None:
    run_id = f"torqueai-scheduled-{uuid4().hex}"
    started_at = datetime.now(timezone.utc)
    try:
        session.add(
            TorqueAIDispatchSyncRun(
                run_id=run_id,
                organization_id=organization.id,
                requested_from=date_from,
                requested_to=date_to,
                page_size=TORQUEAI_INGEST_PAGE_SIZE,
                status="claimed",
                trigger_mode=TRIGGER_MODE,
                trigger_slot=trigger_slot,
                pages_fetched=0,
                provider_total_count=None,
                rows_validated=0,
                rows_inserted=0,
                rows_updated=0,
                rows_unchanged=0,
                error_code=None,
                started_at=started_at,
                completed_at=None,
            )
        )
        session.commit()
        return run_id
    except IntegrityError:
        session.rollback()
        try:
            existing = (
                session.query(TorqueAIDispatchSyncRun)
                .filter(
                    TorqueAIDispatchSyncRun.organization_id == organization.id,
                    TorqueAIDispatchSyncRun.trigger_mode == TRIGGER_MODE,
                    TorqueAIDispatchSyncRun.trigger_slot == trigger_slot,
                )
                .one_or_none()
            )
        except SQLAlchemyError as exc:
            session.rollback()
            raise TorqueAIScheduledSyncError(
                "scheduler_dispatch_claim_failed",
                "TorqueAI scheduled dispatch claim could not be verified.",
            ) from exc
        if existing is not None:
            return None
        raise TorqueAIScheduledSyncError(
            "scheduler_dispatch_claim_failed",
            "TorqueAI scheduled dispatch could not be claimed safely.",
        )
    except SQLAlchemyError as exc:
        session.rollback()
        raise TorqueAIScheduledSyncError(
            "scheduler_dispatch_claim_failed",
            "TorqueAI scheduled dispatch could not be claimed safely.",
        ) from exc


def run_scheduled_torqueai_dispatch_sync(
    session: Session,
    *,
    trigger_timestamp: int,
) -> ScheduledTorqueAISyncResult:
    """Run one signed scheduler-path attempt with no provider retry behavior."""
    trigger_slot, date_from, date_to = _slot_and_window(trigger_timestamp)

    if not scheduled_sync_enabled():
        return ScheduledTorqueAISyncResult(
            status="disabled",
            trigger_slot=trigger_slot,
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            dispatch_claimed=False,
            scheduler_enabled=False,
            error_code="scheduler_disabled",
        )

    organization = resolve_scheduled_organization(session)
    validate_connector_organization_scope(organization.slug)

    run_id = _claim_scheduled_run(
        session,
        organization=organization,
        trigger_slot=trigger_slot,
        date_from=date_from,
        date_to=date_to,
    )
    if run_id is None:
        return ScheduledTorqueAISyncResult(
            status="already_claimed",
            trigger_slot=trigger_slot,
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            dispatch_claimed=False,
            scheduler_enabled=True,
            tenant_scope_validated=True,
        )

    try:
        result = ingest_torqueai_dispatches(
            session,
            organization_id=organization.id,
            organization_slug=organization.slug,
            date_from=date_from,
            date_to=date_to,
            claimed_run_id=run_id,
        )
    except TorqueAIDispatchIngestionError as exc:
        return ScheduledTorqueAISyncResult(
            status="failed",
            trigger_slot=trigger_slot,
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            dispatch_claimed=True,
            scheduler_enabled=True,
            error_code=exc.code,
            tenant_scope_validated=True,
        )

    return ScheduledTorqueAISyncResult(
        status="executed",
        trigger_slot=trigger_slot,
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        dispatch_claimed=True,
        scheduler_enabled=True,
        pages_fetched=int(result["pages_fetched"]),
        provider_total_count=int(result["provider_total_count"]),
        rows_validated=int(result["rows_validated"]),
        rows_inserted=int(result["rows_inserted"]),
        rows_updated=int(result["rows_updated"]),
        rows_unchanged=int(result["rows_unchanged"]),
        tenant_scope_validated=True,
    )
