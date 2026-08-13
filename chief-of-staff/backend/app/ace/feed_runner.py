"""ACE Outlook feed execution and safe run-state recording."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.ace.outlook_import import import_latest_ace_outlook_report
from app.connectors.outlook import OutlookConnector
from app.connectors.outlook_credentials import OutlookCredentialStore
from app.models.ace import AceFeedRun
from app.organizations.models import Organization, OrganizationStatus

logger = logging.getLogger(__name__)

SUCCESS_STATUSES = {"import_success", "already_processed", "no_source_found"}
FAILURE_STATUSES = {"source_contract_error", "import_failed"}


class AceFeedConfigurationError(RuntimeError):
    """Controlled configuration failure for automated ACE feed execution."""


@dataclass(frozen=True)
class AceFeedExecution:
    status: str
    exit_code: int
    source_found: bool
    replayed: bool
    records_read: int
    records_inserted: int
    records_updated: int
    exceptions_created: int
    completed_at: datetime


def resolve_configured_organization(db: Session) -> Organization:
    slug = str(os.getenv("POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG") or "").strip()
    if not slug:
        raise AceFeedConfigurationError("missing_organization_configuration")
    organization = (
        db.query(Organization)
        .filter(Organization.slug == slug, Organization.status == OrganizationStatus.ACTIVE.value)
        .one_or_none()
    )
    if organization is None:
        raise AceFeedConfigurationError("organization_not_found")
    return organization


def run_ace_daily_import(
    db: Session,
    organization_id: str,
    *,
    connector: OutlookConnector | None = None,
    mode: str = "automatic",
) -> AceFeedExecution:
    connector = connector or OutlookConnector(credential_store=OutlookCredentialStore(organization_id))
    result = import_latest_ace_outlook_report(db, organization_id, connector=connector)
    status = _status(result)
    completed_at = datetime.now(timezone.utc)
    feed_run = AceFeedRun(
        organization_id=organization_id,
        mode=mode,
        status=status,
        source_found=bool(result.get("source_found", False)),
        replayed=bool(result.get("replayed", False)),
        records_read=_safe_int(result.get("records_read")),
        records_inserted=_safe_int(result.get("records_inserted")),
        records_updated=_safe_int(result.get("records_updated")),
        exceptions_created=_safe_int(result.get("exceptions_created")),
        error_category=None if status in SUCCESS_STATUSES else status,
        started_at=_safe_datetime(result.get("started_at")) or completed_at,
        completed_at=completed_at,
    )
    db.add(feed_run)
    db.commit()
    logger.info(
        "ACE feed run completed",
        extra={
            "operation": "ace_feed_run",
            "organization_id": organization_id,
            "mode": mode,
            "status_category": status,
            "source_found": feed_run.source_found,
            "replayed": feed_run.replayed,
            "records_read": feed_run.records_read,
            "records_inserted": feed_run.records_inserted,
            "records_updated": feed_run.records_updated,
            "exceptions_created": feed_run.exceptions_created,
        },
    )
    return AceFeedExecution(
        status=status,
        exit_code=0 if status in SUCCESS_STATUSES else 1,
        source_found=feed_run.source_found,
        replayed=feed_run.replayed,
        records_read=feed_run.records_read,
        records_inserted=feed_run.records_inserted,
        records_updated=feed_run.records_updated,
        exceptions_created=feed_run.exceptions_created,
        completed_at=completed_at,
    )


def ace_feed_health(db: Session, organization_id: str) -> dict[str, Any]:
    latest = (
        db.query(AceFeedRun)
        .filter(AceFeedRun.organization_id == organization_id)
        .order_by(AceFeedRun.completed_at.desc().nullslast(), AceFeedRun.id.desc())
        .first()
    )
    latest_success = (
        db.query(AceFeedRun)
        .filter(AceFeedRun.organization_id == organization_id, AceFeedRun.status.in_(["import_success", "already_processed"]))
        .order_by(AceFeedRun.completed_at.desc().nullslast(), AceFeedRun.id.desc())
        .first()
    )
    threshold_hours = _freshness_threshold_hours()
    health = "unknown"
    if latest is not None:
        health = "healthy" if latest.status in {"import_success", "already_processed"} else "warning"
        if latest.status in FAILURE_STATUSES:
            health = "error"
        if latest.status == "no_source_found":
            health = "warning" if _older_than(latest.completed_at, threshold_hours) else "no_new_report_yet"
    if latest_success is not None and _older_than(latest_success.completed_at, threshold_hours):
        health = "warning" if health != "error" else health
    return {
        "status": health,
        "source": "Outlook scheduled report",
        "latest_check_at": latest.completed_at if latest else None,
        "latest_check_status": latest.status if latest else None,
        "latest_successful_import_at": latest_success.completed_at if latest_success else None,
        "latest_successful_mode": latest_success.mode if latest_success else None,
        "records_read": latest_success.records_read if latest_success else 0,
        "records_inserted": latest_success.records_inserted if latest_success else 0,
        "records_updated": latest_success.records_updated if latest_success else 0,
        "exceptions_created": latest_success.exceptions_created if latest_success else 0,
        "freshness_threshold_hours": threshold_hours,
        "secrets_exposed": False,
    }


def _status(result: dict[str, Any]) -> str:
    status = str(result.get("status") or "import_failed")
    if status in SUCCESS_STATUSES | FAILURE_STATUSES:
        return status
    return "import_failed"


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _safe_datetime(value: Any) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _freshness_threshold_hours() -> int:
    try:
        value = int(os.getenv("POLARIS_ACE_FEED_FRESHNESS_HOURS", "36"))
    except ValueError:
        return 36
    return max(1, min(value, 168))


def _older_than(value: datetime | None, threshold_hours: int) -> bool:
    if value is None:
        return True
    comparable = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return comparable < datetime.now(timezone.utc) - timedelta(hours=threshold_hours)
