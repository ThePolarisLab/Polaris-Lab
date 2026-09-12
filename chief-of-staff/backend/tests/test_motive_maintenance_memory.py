from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database.database import Base
from app.models.motive_maintenance import MotiveMaintenanceIssueEvent, MotiveMaintenanceIssueMemory
from app.motive.maintenance_memory import list_maintenance_memory, persist_maintenance_memory
from app.organizations.models import Organization


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add(Organization(id="org-1", slug="mor", display_name="MOR Logistics"))
    db.add(Organization(id="org-2", slug="other", display_name="Other"))
    db.commit()
    return db


def _open_detail(day: int, odometer: int) -> dict:
    d = f"2026-09-{day:02d}"
    return {
        "report_date": d,
        "report_time": f"{d}T12:00:00Z",
        "part_category": "18 - Lamps/Reflectors",
        "part_type": "minor",
        "part_name": None,
        "part_status": "open",
        "odometer": odometer,
    }


def _maintenance(*, details=None, transitions=None, as_of="2026-09-12") -> dict:
    group = {
        "part_category": "18 - Lamps/Reflectors",
        "part_type": "minor",
        "part_name": None,
        "status_transitions": transitions or [],
    }
    return {
        "as_of_date": as_of,
        "classifications": [
            {
                "truck_number": "M2214",
                "provider_window_days": 7,
                "inspection_issue_details": details or [],
                "inspection_resolution_groups": [group] if transitions is not None else [],
            }
        ],
    }


def test_open_history_is_durable_and_idempotent():
    db = _session()
    details = [_open_detail(day, 690000 + day) for day in range(7, 13)]
    result = persist_maintenance_memory(
        session=db,
        organization_id="org-1",
        organization_slug="mor",
        maintenance=_maintenance(details=details, transitions=[{
            "report_date": "2026-09-12",
            "report_time": "2026-09-12T12:00:00Z",
            "status": "open",
            "odometer": 690012,
        }]),
    )
    assert result["events_added"] == 6
    issue = db.scalar(select(MotiveMaintenanceIssueMemory))
    assert issue is not None
    assert issue.lifecycle_state == "open"
    assert issue.first_open_date.isoformat() == "2026-09-07"
    assert issue.last_seen_date.isoformat() == "2026-09-12"
    assert issue.open_observation_count == 6
    assert db.query(MotiveMaintenanceIssueEvent).count() == 6

    second = persist_maintenance_memory(
        session=db,
        organization_id="org-1",
        organization_slug="mor",
        maintenance=_maintenance(details=details, transitions=[{
            "report_date": "2026-09-12",
            "report_time": "2026-09-12T12:00:00Z",
            "status": "open",
            "odometer": 690012,
        }]),
    )
    assert second["events_added"] == 0
    assert issue.open_observation_count == 6


def test_existing_issue_can_resolve_after_open_ages_out_then_reopen():
    db = _session()
    persist_maintenance_memory(
        session=db,
        organization_id="org-1",
        organization_slug="mor",
        maintenance=_maintenance(details=[_open_detail(7, 690007)], transitions=[]),
    )
    resolved = persist_maintenance_memory(
        session=db,
        organization_id="org-1",
        organization_slug="mor",
        maintenance=_maintenance(
            details=[],
            transitions=[{
                "report_date": "2026-09-13",
                "report_time": "2026-09-13T12:00:00Z",
                "status": "repaired",
                "odometer": 694000,
            }],
            as_of="2026-09-13",
        ),
    )
    issue = db.scalar(select(MotiveMaintenanceIssueMemory))
    assert issue.lifecycle_state == "resolved"
    assert issue.explicit_resolution_status == "repaired"
    assert issue.explicit_resolution_date.isoformat() == "2026-09-13"
    assert resolved["explicit_resolution_events_added"] == 1

    reopened = persist_maintenance_memory(
        session=db,
        organization_id="org-1",
        organization_slug="mor",
        maintenance=_maintenance(details=[_open_detail(14, 694500)], transitions=[], as_of="2026-09-14"),
    )
    assert issue.lifecycle_state == "reopened"
    assert issue.last_reopened_date.isoformat() == "2026-09-14"
    assert issue.reopen_count == 1
    assert reopened["reopen_transitions_added"] == 1
    assert db.query(MotiveMaintenanceIssueEvent).filter_by(event_type="reopened").count() == 1


def test_resolution_only_does_not_invent_issue_and_disappearance_does_not_resolve():
    db = _session()
    persist_maintenance_memory(
        session=db,
        organization_id="org-1",
        organization_slug="mor",
        maintenance=_maintenance(
            details=[],
            transitions=[{
                "report_date": "2026-09-12",
                "report_time": "2026-09-12T12:00:00Z",
                "status": "repaired",
                "odometer": 693500,
            }],
        ),
    )
    assert db.query(MotiveMaintenanceIssueMemory).count() == 0

    persist_maintenance_memory(
        session=db,
        organization_id="org-1",
        organization_slug="mor",
        maintenance=_maintenance(details=[_open_detail(12, 693506)], transitions=[]),
    )
    persist_maintenance_memory(
        session=db,
        organization_id="org-1",
        organization_slug="mor",
        maintenance={"as_of_date": "2026-09-20", "classifications": [{"truck_number": "M2214", "inspection_issue_details": [], "inspection_resolution_groups": []}]},
    )
    issue = db.scalar(select(MotiveMaintenanceIssueMemory))
    assert issue.lifecycle_state == "open"
    assert issue.disappearance_means_resolved is False


def test_memory_read_is_tenant_scoped():
    db = _session()
    persist_maintenance_memory(
        session=db,
        organization_id="org-1",
        organization_slug="mor",
        maintenance=_maintenance(details=[_open_detail(12, 693506)], transitions=[]),
    )
    assert len(list_maintenance_memory(session=db, organization_id="org-1", truck_number="M2214")) == 1
    assert list_maintenance_memory(session=db, organization_id="org-2", truck_number="M2214") == []
