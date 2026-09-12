"""Persist conservative maintenance lifecycle memory from certified Motive readiness observations."""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.motive_maintenance import MotiveMaintenanceIssueEvent, MotiveMaintenanceIssueMemory

EXPLICIT_RESOLVED_STATUSES = {"repaired", "no_repair_needed"}


def persist_maintenance_memory(
    *,
    session: Session,
    organization_id: str,
    organization_slug: str,
    maintenance: dict[str, Any],
) -> dict[str, Any]:
    """Upsert issue memory and append de-duplicated evidence; never resolve by disappearance."""
    issues_touched = 0
    events_added = 0
    reopen_events_added = 0
    resolved_events_added = 0
    pending_fingerprints: set[str] = set()

    for classification in maintenance.get("classifications", []):
        if not isinstance(classification, dict):
            continue
        truck_number = str(classification.get("truck_number") or "").strip()
        if not truck_number:
            continue

        observations = _issue_observations(classification)
        for identity, rows in observations.items():
            issue = _find_issue(
                session=session,
                organization_id=organization_id,
                truck_number=truck_number,
                identity=identity,
            )
            has_open_observation = any(_norm(row.get("status")) == "open" for row in rows)
            if issue is None and not has_open_observation:
                # Do not invent historical issues from resolution-only observations.
                continue
            if issue is None:
                issue = _create_issue(
                    session=session,
                    organization_id=organization_id,
                    organization_slug=organization_slug,
                    truck_number=truck_number,
                    identity=identity,
                    source_window_days=int(
                        classification.get("provider_window_days") or maintenance.get("provider_window_days") or 7
                    ),
                )

            issue_changed = False
            for row in sorted(rows, key=_observation_sort_key):
                structured_status = _norm(row.get("status"))
                if structured_status not in {"open", *EXPLICIT_RESOLVED_STATUSES}:
                    continue
                event_type = "observed_open" if structured_status == "open" else "explicit_resolution"
                report_date = _parse_date(row.get("report_date"))
                report_time = _parse_datetime(row.get("report_time"))
                odometer = _safe_int(row.get("odometer"))
                fingerprint = _fingerprint(
                    organization_id=organization_id,
                    truck_number=truck_number,
                    identity_key=issue.identity_key,
                    event_type=event_type,
                    status=structured_status,
                    report_date=row.get("report_date"),
                    report_time=row.get("report_time"),
                    odometer=row.get("odometer"),
                )
                if fingerprint in pending_fingerprints or _event_exists(session, organization_id, fingerprint):
                    continue

                _add_event(
                    session=session,
                    issue=issue,
                    organization_id=organization_id,
                    truck_number=truck_number,
                    event_type=event_type,
                    structured_status=structured_status,
                    report_date=report_date,
                    report_time=report_time,
                    odometer=odometer,
                    fingerprint=fingerprint,
                )
                pending_fingerprints.add(fingerprint)
                events_added += 1
                issue_changed = True

                if structured_status == "open":
                    was_resolved = issue.lifecycle_state == "resolved"
                    if issue.first_open_date is None or (report_date and report_date < issue.first_open_date):
                        issue.first_open_date = report_date
                    issue.open_observation_count += 1
                    if was_resolved:
                        issue.lifecycle_state = "reopened"
                        issue.last_reopened_date = report_date
                        issue.reopen_count += 1
                        reopen_fingerprint = _fingerprint(
                            organization_id=organization_id,
                            truck_number=truck_number,
                            identity_key=issue.identity_key,
                            event_type="reopened",
                            status=structured_status,
                            report_date=row.get("report_date"),
                            report_time=row.get("report_time"),
                            odometer=row.get("odometer"),
                        )
                        if (
                            reopen_fingerprint not in pending_fingerprints
                            and not _event_exists(session, organization_id, reopen_fingerprint)
                        ):
                            _add_event(
                                session=session,
                                issue=issue,
                                organization_id=organization_id,
                                truck_number=truck_number,
                                event_type="reopened",
                                structured_status=structured_status,
                                report_date=report_date,
                                report_time=report_time,
                                odometer=odometer,
                                fingerprint=reopen_fingerprint,
                            )
                            pending_fingerprints.add(reopen_fingerprint)
                            events_added += 1
                            reopen_events_added += 1
                    elif issue.lifecycle_state != "reopened":
                        issue.lifecycle_state = "open"
                    _update_last_seen(issue, report_date, report_time, odometer)
                elif structured_status in EXPLICIT_RESOLVED_STATUSES and issue.first_open_date is not None:
                    # Only an explicit structured resolution can resolve durable memory.
                    if report_date is None or issue.first_open_date <= report_date:
                        issue.lifecycle_state = "resolved"
                        issue.explicit_resolution_status = structured_status
                        issue.explicit_resolution_date = report_date
                        _update_last_seen(issue, report_date, report_time, odometer)
                        resolved_events_added += 1

            if issue_changed:
                issue.source_snapshot = {
                    "source": "motive_inspection_reports",
                    "window_bounded": True,
                    "disappearance_means_resolved": False,
                    "last_sync_as_of_date": maintenance.get("as_of_date"),
                }
                issues_touched += 1

    session.commit()
    return {
        "issues_touched": issues_touched,
        "events_added": events_added,
        "explicit_resolution_events_added": resolved_events_added,
        "reopen_transitions_added": reopen_events_added,
        "provider_writes_performed": False,
        "disappearance_means_resolved": False,
        "durable_maintenance_history_enabled": True,
    }


def list_maintenance_memory(
    *, session: Session, organization_id: str, truck_number: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    stmt = select(MotiveMaintenanceIssueMemory).where(MotiveMaintenanceIssueMemory.organization_id == organization_id)
    if truck_number and truck_number.strip():
        stmt = stmt.where(MotiveMaintenanceIssueMemory.truck_number == truck_number.strip())
    stmt = stmt.order_by(MotiveMaintenanceIssueMemory.updated_at.desc()).limit(limit)
    rows = session.scalars(stmt).all()
    return [_serialize_issue(row) for row in rows]


def _issue_observations(classification: dict[str, Any]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for detail in classification.get("inspection_issue_details", []):
        if not isinstance(detail, dict) or _norm(detail.get("part_status")) != "open":
            continue
        identity = _identity(detail)
        if identity is None:
            continue
        grouped.setdefault(identity, []).append(
            {
                "status": "open",
                "report_date": detail.get("report_date"),
                "report_time": detail.get("report_time"),
                "odometer": detail.get("odometer"),
            }
        )

    for group in classification.get("inspection_resolution_groups", []):
        if not isinstance(group, dict):
            continue
        identity = _identity(group)
        if identity is None:
            continue
        for transition in group.get("status_transitions", []):
            if not isinstance(transition, dict):
                continue
            status_value = _norm(transition.get("status"))
            if status_value not in {"open", *EXPLICIT_RESOLVED_STATUSES}:
                continue
            grouped.setdefault(identity, []).append(
                {
                    "status": status_value,
                    "report_date": transition.get("report_date"),
                    "report_time": transition.get("report_time"),
                    "odometer": transition.get("odometer"),
                }
            )
    return grouped


def _identity(value: dict[str, Any]) -> tuple[str, str, str] | None:
    category = str(value.get("part_category") or "").strip()
    part_type = str(value.get("part_type") or "").strip()
    name = str(value.get("part_name") or "").strip()
    normalized = (_norm(category), _norm(part_type), _norm(name))
    if not any(normalized):
        return None
    return category, part_type, name


def _find_issue(
    *, session: Session, organization_id: str, truck_number: str, identity: tuple[str, str, str]
) -> MotiveMaintenanceIssueMemory | None:
    return session.scalar(
        select(MotiveMaintenanceIssueMemory).where(
            MotiveMaintenanceIssueMemory.organization_id == organization_id,
            MotiveMaintenanceIssueMemory.truck_number == truck_number,
            MotiveMaintenanceIssueMemory.identity_key == _identity_key(identity),
        )
    )


def _create_issue(
    *,
    session: Session,
    organization_id: str,
    organization_slug: str,
    truck_number: str,
    identity: tuple[str, str, str],
    source_window_days: int,
) -> MotiveMaintenanceIssueMemory:
    category, part_type, name = identity
    issue = MotiveMaintenanceIssueMemory(
        organization_id=organization_id,
        organization_slug=organization_slug,
        truck_number=truck_number,
        identity_key=_identity_key(identity),
        part_category=category or None,
        part_type=part_type or None,
        part_name=name or None,
        lifecycle_state="open",
        source_window_days=source_window_days,
        disappearance_means_resolved=False,
    )
    session.add(issue)
    session.flush()
    return issue


def _add_event(
    *,
    session: Session,
    issue: MotiveMaintenanceIssueMemory,
    organization_id: str,
    truck_number: str,
    event_type: str,
    structured_status: str,
    report_date: date | None,
    report_time: datetime | None,
    odometer: int | None,
    fingerprint: str,
) -> None:
    session.add(
        MotiveMaintenanceIssueEvent(
            organization_id=organization_id,
            issue=issue,
            truck_number=truck_number,
            identity_key=issue.identity_key,
            event_type=event_type,
            structured_status=structured_status,
            report_date=report_date,
            report_time=report_time,
            odometer=odometer,
            source_fingerprint=fingerprint,
            provider_write_performed=False,
        )
    )


def _event_exists(session: Session, organization_id: str, fingerprint: str) -> bool:
    return session.scalar(
        select(MotiveMaintenanceIssueEvent.id).where(
            MotiveMaintenanceIssueEvent.organization_id == organization_id,
            MotiveMaintenanceIssueEvent.source_fingerprint == fingerprint,
        )
    ) is not None


def _identity_key(identity: tuple[str, str, str]) -> str:
    return sha256("\x1f".join(_norm(value) for value in identity).encode("utf-8")).hexdigest()


def _fingerprint(**values: Any) -> str:
    ordered = "\x1f".join(str(values.get(key) or "") for key in sorted(values))
    return sha256(ordered.encode("utf-8")).hexdigest()


def _update_last_seen(
    issue: MotiveMaintenanceIssueMemory,
    report_date: date | None,
    report_time: datetime | None,
    odometer: int | None,
) -> None:
    if report_date is not None and (issue.last_seen_date is None or report_date >= issue.last_seen_date):
        issue.last_seen_date = report_date
        if report_time is not None:
            issue.last_seen_at = report_time
        if odometer is not None:
            issue.last_odometer = odometer


def _serialize_issue(issue: MotiveMaintenanceIssueMemory) -> dict[str, Any]:
    return {
        "truck_number": issue.truck_number,
        "part_category": issue.part_category,
        "part_type": issue.part_type,
        "part_name": issue.part_name,
        "lifecycle_state": issue.lifecycle_state,
        "first_open_date": issue.first_open_date.isoformat() if issue.first_open_date else None,
        "last_seen_date": issue.last_seen_date.isoformat() if issue.last_seen_date else None,
        "last_seen_at": issue.last_seen_at.isoformat() if issue.last_seen_at else None,
        "last_odometer": issue.last_odometer,
        "explicit_resolution_status": issue.explicit_resolution_status,
        "explicit_resolution_date": issue.explicit_resolution_date.isoformat() if issue.explicit_resolution_date else None,
        "last_reopened_date": issue.last_reopened_date.isoformat() if issue.last_reopened_date else None,
        "reopen_count": issue.reopen_count,
        "open_observation_count": issue.open_observation_count,
        "source_window_days": issue.source_window_days,
        "disappearance_means_resolved": issue.disappearance_means_resolved,
    }


def _observation_sort_key(value: dict[str, Any]) -> tuple[str, str]:
    return str(value.get("report_date") or ""), str(value.get("report_time") or "")


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()
