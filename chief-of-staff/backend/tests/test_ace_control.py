import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./polaris-ace-test.db")
os.environ.setdefault("POLARIS_ENV", "test")
os.environ.setdefault("POLARIS_LOCAL_AUTH_SECRET", "test-local-auth-secret-with-enough-length")
os.environ.setdefault("POLARIS_QBO_CLIENT_ID", "client-id")
os.environ.setdefault("POLARIS_QBO_CLIENT_SECRET", "client-secret")
os.environ.setdefault("POLARIS_QBO_REDIRECT_URI", "http://localhost:8000/api/v1/connectors/quickbooks/oauth/callback")
os.environ.setdefault("POLARIS_QBO_OAUTH_STATE_SECRET", "quickbooks-state-secret-with-enough-length")
os.environ.setdefault("POLARIS_QBO_TOKEN_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

from app.ace.service import import_rows, movement_query, normalized_payload
from app.dashboard.service import build_executive_dashboard
from app.database.database import Base, SessionLocal, engine
from app.identity.models import Identity, OrganizationMembership
from app.main import app
from app.models.ace import AceFeedRun, AceImportRun, AceInBondEvent, AceInBondMovement
from app.models.team_note import TeamNote
from app.organizations.models import Organization
from app.security.providers import LocalTokenProvider


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def seed_principal(role: str = "owner", organization_id: str = "org-1", identity_id: str = "identity-1") -> dict[str, str]:
    with SessionLocal.begin() as session:
        session.add(Organization(id=organization_id, slug=organization_id, display_name=organization_id))
        session.add(Identity(id=identity_id, email=f"{identity_id}@example.test", display_name=identity_id))
        session.add(
            OrganizationMembership(
                id=f"membership-{organization_id}-{identity_id}",
                organization_id=organization_id,
                identity_id=identity_id,
                role=role,
            )
        )
    token = LocalTokenProvider().issue(identity_id)
    return {"Authorization": f"Bearer {token}", "X-Polaris-Organization": organization_id}


def ace_row(**overrides):
    row = {
        "inbond_number": "IB-100",
        "bill_of_lading_number": "BOL-100",
        "inbond_type_code": "61",
        "record_status": "Open",
        "shipper_name": "Synthetic Shipper",
        "consignee_name": "Synthetic Consignee",
        "qp_filer_code": "8MH",
        "inbond_carrier_code": "MLVM",
        "bonded_carrier_code": "MLVM",
        "manifest_carrier_code": "ABCD",
        "origination_port_name": "Synthetic Origin",
        "destination_port_name": "Synthetic Destination",
        "create_date": "2026-08-01",
        "arrival_date": None,
        "export_date": None,
        "days_late": 0,
        "days_overdue_for_export": 3,
        "late_in_transit": False,
        "overdue_for_export": True,
        "penalty_indicator": False,
    }
    row.update(overrides)
    return row


def import_request(source_message_id: str, rows: list[dict]):
    return {
        "source_message_id": source_message_id,
        "source_filename": "ace-inbond-bills-of-lading.csv",
        "source_received_at": "2026-08-13T12:00:00Z",
        "rows": rows,
    }


def test_import_run_idempotency_preserves_events_and_multiple_bols(client):
    headers = seed_principal()
    first = client.post(
        "/ace/movements/import",
        headers=headers,
        json=import_request("message-1", [ace_row(), ace_row(bill_of_lading_number="BOL-101")]),
    )
    replay = client.post(
        "/ace/movements/import",
        headers=headers,
        json=import_request("message-1", [ace_row(), ace_row(bill_of_lading_number="BOL-101")]),
    )

    assert first.status_code == 200
    assert first.json()["status"] == "completed"
    assert first.json()["inserted"] == 2
    assert replay.status_code == 200
    assert replay.json()["status"] == "idempotent_replay"

    with SessionLocal() as session:
        assert session.query(AceImportRun).count() == 1
        assert session.query(AceInBondMovement).filter_by(inbond_number="IB-100").count() == 2
        assert session.query(AceInBondEvent).filter_by(event_type="first_seen").count() == 2
        assert session.query(AceInBondEvent).filter_by(event_type="exception_opened").count() == 2


def test_new_daily_import_updates_without_duplicate_exception_event(client):
    headers = seed_principal()
    assert client.post("/ace/movements/import", headers=headers, json=import_request("message-1", [ace_row()])).status_code == 200
    second = client.post(
        "/ace/movements/import",
        headers=headers,
        json=import_request("message-2", [ace_row(days_late=2, late_in_transit=True)]),
    )

    assert second.status_code == 200
    assert second.json()["updated"] == 1
    assert second.json()["exceptions_created"] == 0
    with SessionLocal() as session:
        movement = session.query(AceInBondMovement).one()
        assert movement.days_late == 2
        assert movement.late_in_transit is True
        assert session.query(AceInBondEvent).filter_by(event_type="first_seen").count() == 1
        assert session.query(AceInBondEvent).filter_by(event_type="exception_opened").count() == 1


def test_malformed_normalized_row_records_failed_import_without_movements():
    seed_principal()
    with SessionLocal() as session:
        result = import_rows(
            session,
            "org-1",
            source_message_id="bad-message",
            source_filename="ace.csv",
            source_received_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
            rows=[ace_row(days_late="abc")],
        )

    assert result["status"] == "failed"
    assert result["error_message"] == "ACE import failed validation."
    with SessionLocal() as session:
        assert session.query(AceInBondMovement).count() == 0
        failed = session.query(AceImportRun).one()
        assert failed.status == "failed"
        assert "abc" not in (failed.error_message or "")


def test_normalization_rejects_bad_integer_date_and_boolean_values():
    with pytest.raises(ValueError, match="days_late"):
        normalized_payload(ace_row(days_late="abc"))
    with pytest.raises(ValueError, match="create_date"):
        normalized_payload(ace_row(create_date="not-a-date"))
    with pytest.raises(ValueError, match="late_in_transit"):
        normalized_payload(ace_row(late_in_transit="maybe"))


def test_carrier_and_qp_reviews_do_not_infer_unauthorized(client):
    headers = seed_principal()
    response = client.post("/ace/movements/import", headers=headers, json=import_request("message-1", [ace_row(overdue_for_export=False, days_overdue_for_export=0)]))

    assert response.status_code == 200
    detail = client.get("/ace/movements", headers=headers).json()["items"][0]
    assert detail["review_status"] == "review"
    assert "carrier_mismatch" in detail["review_reason"]
    assert "qp_filer_review" in detail["review_reason"]
    assert detail["authorization_status"] is None
    assert detail["review_status"] != "critical"


def test_ordinary_open_movement_stays_out_of_daily_brief_attention(client):
    headers = seed_principal()
    ordinary_open = ace_row(
        qp_filer_code=None,
        manifest_carrier_code="MLVM",
        overdue_for_export=False,
        days_overdue_for_export=0,
    )
    response = client.post("/ace/movements/import", headers=headers, json=import_request("message-1", [ordinary_open]))

    assert response.status_code == 200
    detail = client.get("/ace/movements", headers=headers).json()["items"][0]
    assert detail["record_status"] == "Open"
    assert detail["review_status"] == "clear"
    with SessionLocal() as session:
        dashboard = build_executive_dashboard(session, organization_id="org-1")
    assert not [item for item in dashboard.needs_attention if item.source == "ACE Bond Control"]
    assert not [item for item in dashboard.watch_items if item.source == "ACE Bond Control"]


def test_unresolved_ace_exceptions_are_aggregated_in_daily_brief_without_raw_shipments(client):
    headers = seed_principal()
    response = client.post(
        "/ace/movements/import",
        headers=headers,
        json=import_request("message-1", [ace_row(), ace_row(bill_of_lading_number="BOL-101")]),
    )
    assert response.status_code == 200

    with SessionLocal() as session:
        dashboard = build_executive_dashboard(session, organization_id="org-1")

    ace_items = [item for item in dashboard.needs_attention if item.source == "ACE Bond Control"]
    assert len(ace_items) == 1
    assert ace_items[0].title == "ACE / Bond Control requires attention"
    assert ace_items[0].severity == "HIGH"
    assert "2 Overdue" in ace_items[0].detail
    assert "2 Carrier review" in ace_items[0].detail
    assert ace_items[0].entity_id == "#executive/ace?counter_filter=exceptions"
    serialized = " ".join([ace_items[0].title, ace_items[0].detail, ace_items[0].entity_id or ""])
    assert "IB-100" not in serialized
    assert "BOL-100" not in serialized
    assert "BOL-101" not in serialized
    assert len(dashboard.daily_brief.needs_attention) == len(dashboard.needs_attention)
    brief_ace = [item for item in dashboard.daily_brief.ace_summary if item.source == "ACE Bond Control"]
    assert len(brief_ace) == 1
    assert "2 Exceptions" in brief_ace[0].detail
    assert "2 Overdue" in brief_ace[0].detail
    assert "IB-100" not in brief_ace[0].detail
    assert "BOL-100" not in brief_ace[0].detail


def test_resolved_ace_exception_disappears_from_daily_brief_and_reopen_returns(client):
    headers = seed_principal()
    client.post("/ace/movements/import", headers=headers, json=import_request("message-1", [ace_row()]))
    movement_id = client.get("/ace/movements", headers=headers).json()["items"][0]["id"]

    with SessionLocal() as session:
        assert [item for item in build_executive_dashboard(session, organization_id="org-1").needs_attention if item.source == "ACE Bond Control"]

    resolved = client.post(f"/ace/movements/{movement_id}/resolve", headers=headers, json={"resolution_notes": "managed"})
    assert resolved.status_code == 200
    with SessionLocal() as session:
        dashboard = build_executive_dashboard(session, organization_id="org-1")
        assert not [item for item in dashboard.needs_attention if item.source == "ACE Bond Control"]
        assert not [item for item in dashboard.daily_brief.needs_attention if item.source == "ACE Bond Control"]

    reopened = client.post(f"/ace/movements/{movement_id}/reopen", headers=headers)
    assert reopened.status_code == 200
    with SessionLocal() as session:
        dashboard = build_executive_dashboard(session, organization_id="org-1")
        assert [item for item in dashboard.needs_attention if item.source == "ACE Bond Control"]
        assert [item for item in dashboard.daily_brief.needs_attention if item.source == "ACE Bond Control"]


def test_continuing_ace_exception_does_not_duplicate_daily_brief_attention_or_events(client):
    headers = seed_principal()
    client.post("/ace/movements/import", headers=headers, json=import_request("message-1", [ace_row()]))
    client.post("/ace/movements/import", headers=headers, json=import_request("message-2", [ace_row(days_overdue_for_export=4)]))

    with SessionLocal() as session:
        dashboard = build_executive_dashboard(session, organization_id="org-1")
        ace_items = [item for item in dashboard.needs_attention if item.source == "ACE Bond Control"]
        assert len(ace_items) == 1
        assert session.query(AceInBondEvent).filter_by(event_type="exception_opened").count() == 1


def test_ace_feed_health_only_surfaces_actionable_daily_brief_items(client):
    seed_principal()
    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as session:
        session.add(AceFeedRun(organization_id="org-1", mode="scheduled", status="import_success", source_found=True, records_read=127, completed_at=now))
    with SessionLocal() as session:
        healthy = build_executive_dashboard(session, organization_id="org-1")
    assert not [item for item in healthy.needs_attention if item.source == "ACE Daily Feed"]
    assert healthy.daily_brief.system_health == ()

    with SessionLocal.begin() as session:
        session.add(AceFeedRun(organization_id="org-1", mode="scheduled", status="source_contract_error", error_category="source_contract_error", completed_at=now + timedelta(minutes=5)))
    with SessionLocal() as session:
        failed = build_executive_dashboard(session, organization_id="org-1")
    feed_items = [item for item in failed.needs_attention if item.source == "ACE Daily Feed"]
    assert len(feed_items) == 1
    assert feed_items[0].severity == "CRITICAL"
    assert "source_contract_error" in feed_items[0].detail
    assert failed.daily_brief.system_health[0].title == "ACE daily feed failed"


def test_daily_brief_prioritizes_critical_before_high_without_ace_flood(client):
    headers = seed_principal()
    client.post("/ace/movements/import", headers=headers, json=import_request("message-1", [ace_row(), ace_row(bill_of_lading_number="BOL-101")]))
    with SessionLocal.begin() as session:
        session.add(
            TeamNote(
                organization_id="org-1",
                author="ops",
                note_type="BLOCKER",
                status="OPEN",
                title="Executive blocker",
                details="Critical management decision required.",
            )
        )

    with SessionLocal() as session:
        dashboard = build_executive_dashboard(session, organization_id="org-1")

    assert dashboard.daily_brief.todays_priority[0].title == "Executive blocker"
    assert len([item for item in dashboard.daily_brief.needs_attention if item.source == "ACE Bond Control"]) == 1


def test_daily_brief_carry_forward_waiting_on_and_duplicate_prevention():
    seed_principal()
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    with SessionLocal.begin() as session:
        session.add(
            TeamNote(
                organization_id="org-1",
                author="ops",
                note_type="ACTION",
                status="OPEN",
                title="Call broker",
                details="Confirm release timing.",
                assigned_to="Broker",
                due_at=tomorrow,
                created_at=yesterday,
            )
        )
        session.add(
            TeamNote(
                organization_id="org-1",
                author="ops",
                note_type="INFORMATION",
                status="OPEN",
                title="Accounting follow-up",
                details="Waiting for reconciliation.",
                assigned_to="Accountant",
                created_at=yesterday,
            )
        )

    with SessionLocal() as session:
        dashboard = build_executive_dashboard(session, organization_id="org-1")

    assert [item for item in dashboard.daily_brief.waiting_on if "Broker" in item.detail]
    assert [item for item in dashboard.daily_brief.waiting_on if "Accountant" in item.detail]
    assert not [item for item in dashboard.daily_brief.carry_forward if item.title == "Call broker"]


def test_daily_brief_remains_organization_scoped(client):
    org1 = seed_principal(organization_id="org-1", identity_id="identity-1")
    seed_principal(organization_id="org-2", identity_id="identity-2")
    client.post("/ace/movements/import", headers=org1, json=import_request("message-1", [ace_row()]))

    with SessionLocal() as session:
        org1_dashboard = build_executive_dashboard(session, organization_id="org-1")
        org2_dashboard = build_executive_dashboard(session, organization_id="org-2")

    assert [item for item in org1_dashboard.daily_brief.needs_attention if item.source == "ACE Bond Control"]
    assert not [item for item in org2_dashboard.daily_brief.needs_attention if item.source == "ACE Bond Control"]
    assert org2_dashboard.daily_brief.ace_summary == ()


def test_manual_unauthorized_resolve_and_reopen_lifecycle(client):
    headers = seed_principal()
    client.post("/ace/movements/import", headers=headers, json=import_request("message-1", [ace_row(overdue_for_export=False, days_overdue_for_export=0)]))
    movement_id = client.get("/ace/movements", headers=headers).json()["items"][0]["id"]

    auth = client.patch(
        f"/ace/movements/{movement_id}/authorization",
        headers=headers,
        json={"authorization_status": "UNAUTHORIZED - NO MOR PERMISSION", "authorization_notes": "synthetic management classification", "evidence_reference": "case-note-1"},
    )
    assert auth.status_code == 200
    assert auth.json()["review_status"] == "critical"
    assert auth.json()["authorization_status"] == "UNAUTHORIZED - NO MOR PERMISSION"

    assert client.get("/ace/exceptions", headers=headers).json()
    resolved = client.post(f"/ace/movements/{movement_id}/resolve", headers=headers, json={"resolution_notes": "synthetic resolved"},)
    assert resolved.status_code == 200
    assert resolved.json()["review_status"] == "resolved"
    assert client.get("/ace/exceptions", headers=headers).json() == []

    reopened = client.post(f"/ace/movements/{movement_id}/reopen", headers=headers)
    assert reopened.status_code == 200
    assert reopened.json()["review_status"] == "critical"


def test_ace_api_is_organization_scoped(client):
    org1 = seed_principal(organization_id="org-1", identity_id="identity-1")
    org2 = seed_principal(organization_id="org-2", identity_id="identity-2")
    client.post("/ace/movements/import", headers=org1, json=import_request("message-1", [ace_row()]))
    movement_id = client.get("/ace/movements", headers=org1).json()["items"][0]["id"]

    assert client.get("/ace/movements", headers=org2).json()["items"] == []
    assert client.get(f"/ace/movements/{movement_id}", headers=org2).status_code == 404
    assert client.post(f"/ace/movements/{movement_id}/resolve", headers=org2, json={"resolution_notes": "nope"}).status_code == 404
    assert client.post("/ace/movements/import", headers=org2, json=import_request("message-1", [ace_row()])).status_code == 200
    with SessionLocal() as session:
        assert session.query(AceImportRun).count() == 2


def test_filters_cover_operational_fields():
    seed_principal()
    with SessionLocal() as session:
        import_rows(session, "org-1", source_message_id="message-1", source_filename="ace.csv", source_received_at=None, rows=[ace_row()])
        filters = {
            "inbond_number": "IB-100",
            "bol": "BOL-100",
            "shipper": "Shipper",
            "consignee": "Consignee",
            "qp_filer": "8MH",
            "inbond_carrier": "MLVM",
            "bonded_carrier": "MLVM",
            "manifest_carrier": "ABCD",
            "origin_port": "Origin",
            "destination_port": "Destination",
            "inbond_type": "61",
            "exception_type": "carrier_mismatch",
            "open_closed": "open",
            "late": False,
            "overdue": True,
            "penalty": False,
            "transfer_of_liability": False,
        }
        query = movement_query(session, "org-1", **filters)
        assert query.count() == 1


def test_counter_filters_match_ace_dashboard_cards():
    seed_principal()
    with SessionLocal() as session:
        import_rows(
            session,
            "org-1",
            source_message_id="message-1",
            source_filename="ace.csv",
            source_received_at=None,
            rows=[
                ace_row(),
                ace_row(
                    inbond_number="IB-200",
                    bill_of_lading_number="BOL-200",
                    qp_filer_code=None,
                    manifest_carrier_code="MLVM",
                    overdue_for_export=False,
                    days_overdue_for_export=0,
                ),
            ],
        )
        assert movement_query(session, "org-1", counter_filter="exceptions").count() == 1
        assert movement_query(session, "org-1", counter_filter="active").count() == 2
        movement = session.query(AceInBondMovement).filter_by(inbond_number="IB-200").one()
        movement.authorization_status = "UNAUTHORIZED - NO MOR PERMISSION"
        movement.review_status, movement.review_reason = ("critical", "unauthorized")
        session.commit()
        assert movement_query(session, "org-1", counter_filter="unauthorized").count() == 1
