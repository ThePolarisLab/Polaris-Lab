"""End-to-end durable ingestion -> real authenticated MCP transport."""
from datetime import datetime, timedelta, timezone
import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import validate
import pytest
from sqlalchemy import event

from app.chatgpt_mcp.loaded_trailers import LOADED_SCOPE, LOADED_OUTPUT_SCHEMA
from app.chatgpt_mcp import security
from app.models.motive import MotiveVehicleRecord
from app.models.motive_location import MotiveLocationObservation
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchStop
from app.motive import location_sync
from app.services import loaded_trailer_intelligence as intelligence
from tests.test_chatgpt_mcp import setup, keys, add, rpc, token
from tests import auth_helpers


class LocationProvider:
    def __init__(self, now, city="Winnipeg", province="MB", driver="Driver One", age=5):
        self.now, self.city, self.province, self.driver, self.age = now, city, province, driver, age
        self.calls = []

    def _request_json(self, path, *, params, operation):
        self.calls.append(path)
        if path == "/v3/vehicle_locations":
            assert params == {"vehicle_ids[]": "101", "per_page": 2, "page_no": 1}
            return {"vehicles": [{"vehicle": {"id": 101, "number": "2218", "vin": "SECRET-VIN",
                    "current_location": {"lat": 49.89, "lon": -97.13, "city": self.city,
                        "state": self.province, "located_at": (self.now - timedelta(minutes=self.age)).isoformat()}}}]}
        assert path == "/v1/vehicles/lookup"
        return {"vehicle": {"id": 101, "number": "2218", "current_driver": {
            "id": 22, "first_name": self.driver, "last_name": "", "status": "active", "email": "SECRET-EMAIL"}}}


def seed(setup, *, status="In Transit", trailer="R-34", city="Winnipeg", province="MB", age=5, driver="Driver One"):
    now = datetime.now(timezone.utc)
    add(setup, trailer=trailer, pickup_date=(now - timedelta(days=1)).date().isoformat())
    with setup["factory"].begin() as session:
        row = session.query(TorqueAIDispatch).one()
        row.status, row.last_observed_at, row.last_changed_at = status, now, now - timedelta(minutes=max(10, age + 5))
        session.add(MotiveVehicleRecord(organization_id=setup["org"], organization_slug="mor-logistics",
                    provider_vehicle_id="101", unit_number="2218", status="active"))
    provider = LocationProvider(now, city, province, driver, age)
    with setup["factory"]() as session:
        result = location_sync.sync_locations(session, organization_id=setup["org"], connector=provider, now=now)
        assert result["locations_observed"] == 1
    return provider


def call(setup, arguments=None, scope=None, headers=None):
    auth = {"Authorization": "Bearer " + token(setup, scope=scope or LOADED_SCOPE)}
    auth.update(headers or {})
    response = rpc(setup, name="get_loaded_trailers", arguments=arguments or {"city": "Winnipeg", "province": "Manitoba", "country": "Canada"}, headers=auth)
    if response.status_code == 200:
        value = response.json()["result"]["structuredContent"]
        validate(value, LOADED_OUTPUT_SCHEMA)
        assert json.loads(response.json()["result"]["content"][0]["text"]) == value
    return response


def result(setup, **kwargs):
    response = call(setup, **kwargs)
    assert response.status_code == 200, response.text
    return response.json()["result"]["structuredContent"]


def test_durable_ingestion_to_confirmed_mcp_and_metadata(setup):
    provider = seed(setup)
    assert provider.calls == ["/v3/vehicle_locations", "/v1/vehicles/lookup"]
    value = result(setup)
    assert value["summary"] == {"confirmed_loaded_trailer_count": 1, "uncertain_loaded_trailer_count": 0}
    trailer = value["trailers"][0]
    assert trailer["location_source"] == "motive_gps" and trailer["confidence"] == "high"
    assert trailer["location_observed_at"] and trailer["dispatch_last_observed_at"]
    assert "trailer_location_via_dispatch_truck_assignment" in trailer["loaded_evidence"]
    tool = rpc(setup, "tools/list").json()["result"]["tools"][1]
    assert tool["name"] == "get_loaded_trailers"
    assert tool["annotations"] == {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
    assert tool["inputSchema"]["required"] == ["city"]
    assert tool["_meta"]["securitySchemes"][0]["scopes"] == [LOADED_SCOPE]


@pytest.mark.parametrize("status", ["Delivered", "Completed", "cancelled", "CANCELED", "Empty", "Unassigned", "Unloaded"])
def test_terminal_and_empty_states_excluded(setup, status):
    seed(setup, status=status)
    assert result(setup)["summary"] == {"confirmed_loaded_trailer_count": 0, "uncertain_loaded_trailer_count": 0}


@pytest.mark.parametrize("trailer", [None, "", "  ", "N/A"])
def test_unassigned_trailer_excluded(setup, trailer):
    seed(setup, trailer=trailer)
    assert not result(setup)["trailers"] and not result(setup)["uncertain_trailers"]


@pytest.mark.parametrize("status", ["Assigned", "Dispatched", "pending", "not loaded", "unknown"])
def test_active_assignment_and_loaded_miles_alone_never_confirm(setup, status):
    seed(setup, status=status)
    value = result(setup)
    assert not value["trailers"]
    assert "loaded_state_not_established" in value["uncertain_trailers"][0]["attention_flags"]


@pytest.mark.parametrize("province", ["MB", "Manitoba", "mB", "manitoba"])
def test_case_and_province_aliases(setup, province):
    seed(setup, city="WINNIPEG", province=province)
    assert result(setup, arguments={"city": " winnipeg ", "province": "mb", "country": "ca"})["summary"]["confirmed_loaded_trailer_count"] == 1


def test_ontario_alias_and_optional_filters(setup):
    seed(setup, city="Toronto", province="Ontario")
    assert result(setup, arguments={"city": "toronto", "province": "ON"})["summary"]["confirmed_loaded_trailer_count"] == 1
    assert result(setup, arguments={"city": "Toronto"})["summary"]["confirmed_loaded_trailer_count"] == 1
    assert not result(setup, arguments={"city": "Toronto", "country": "USA"})["trailers"]


@pytest.mark.parametrize("age,confirmed,confidence", [(30, True, "medium"), (119, True, "medium"), (121, False, "low"), (-10, False, "low")])
def test_location_age_threshold_and_future_rejection(setup, age, confirmed, confidence):
    seed(setup, age=age)
    value = result(setup)
    assert bool(value["trailers"]) is confirmed
    row = (value["trailers"] or value["uncertain_trailers"])[0]
    assert row["confidence"] == confidence


def test_future_winnipeg_stop_does_not_override_gps_elsewhere(setup):
    seed(setup, city="Brandon")
    with setup["factory"].begin() as session:
        session.query(TorqueAIDispatchStop).filter_by(job="Pick Up").one().scheduled_pickup_date_text = "2099-01-01"
    assert result(setup)["summary"] == {"confirmed_loaded_trailer_count": 0, "uncertain_loaded_trailer_count": 0}


def test_schedule_only_is_uncertain_with_no_claimed_current_city(setup):
    seed(setup)
    with setup["factory"].begin() as session:
        session.query(MotiveLocationObservation).delete()
        session.query(TorqueAIDispatchStop).filter_by(job="Pick Up").one().scheduled_pickup_date_text = "2099-01-01"
    value = result(setup)
    assert not value["trailers"]
    row = value["uncertain_trailers"][0]
    assert row["current_city"] is None and row["location_observed_at"] is None
    assert "scheduled_stop_only_not_current_location" in row["attention_flags"]


@pytest.mark.parametrize("field", ["last_observed_at", "pairing_observed_at", "collected_at"])
def test_each_evidence_timestamp_must_be_fresh(setup, field):
    seed(setup)
    with setup["factory"].begin() as session:
        row = session.query(TorqueAIDispatch if field == "last_observed_at" else MotiveLocationObservation).one()
        setattr(row, field, datetime.now(timezone.utc) - timedelta(hours=3))
    assert not result(setup)["trailers"]


def test_current_driver_conflict_is_uncertain(setup):
    seed(setup, driver="Other Driver")
    assert "current_driver_pairing_unverified_or_conflicting" in result(setup)["uncertain_trailers"][0]["attention_flags"]


@pytest.mark.parametrize("new_status", ["Loaded", "Delivered"])
def test_latest_trailer_record_wins_before_city_filter(setup, new_status):
    seed(setup)
    add(setup, load="102", trailer=" r-34 ", pickup_city="Brandon")
    with setup["factory"].begin() as session:
        new = session.query(TorqueAIDispatch).filter_by(provider_load_number="102").one()
        new.last_changed_at = datetime.now(timezone.utc) - timedelta(minutes=7)
        new.last_observed_at = datetime.now(timezone.utc)
        new.status = new_status
    value = result(setup)
    if new_status == "Loaded":
        assert len(value["trailers"]) == 1 and value["trailers"][0]["load_number"] == "102"
    else:
        assert not value["trailers"] and not value["uncertain_trailers"]


def test_two_trailers_on_same_truck_are_not_confirmed(setup):
    seed(setup)
    add(setup, load="102", trailer="R-35")
    assert not result(setup)["trailers"]


def test_tenant_dispatch_vehicle_and_child_isolation(setup):
    seed(setup)
    other, _, _ = auth_helpers.seed_principal()
    add(setup, load="SECRET-LOAD", organization_id=other["id"], trailer="SECRET-TRAILER")
    with setup["factory"].begin() as session:
        observation = session.query(MotiveLocationObservation).one()
        observation.organization_id = other["id"]
        child = session.query(TorqueAIDispatchStop).filter_by(organization_id=setup["org"], job="Pick Up").one()
        child.organization_id = other["id"]
    response = call(setup, headers={"X-Polaris-Organization": other["id"]})
    assert "SECRET" not in response.text
    assert response.json()["result"]["structuredContent"]["summary"] == {"confirmed_loaded_trailer_count": 0, "uncertain_loaded_trailer_count": 0}


def test_read_scope_separation_and_authentication(setup):
    assert call(setup, headers={"Authorization": ""}).status_code == 401
    assert result(setup, scope=security.SCOPE)["error"]["code"] == "FORBIDDEN"
    response = rpc(setup, headers={"Authorization": "Bearer " + token(setup, scope=LOADED_SCOPE)})
    assert response.json()["result"]["structuredContent"]["error"]["code"] == "FORBIDDEN"
    assert result(setup, scope=LOADED_SCOPE + " " + security.SCOPE)["status"] == "success"


@pytest.mark.parametrize("arguments", [{"city": " "}, {"city": 4}, {"province": "MB"}, {"city": "a"*256}, {"city": "Winnipeg", "organization_id": "other"}, {"city": "a\nb"}])
def test_bounded_input(setup, arguments):
    assert result(setup, arguments=arguments)["error"]["code"] == "INVALID_INPUT"


def test_no_provider_calls_writes_or_secrets_in_mcp(setup, monkeypatch):
    seed(setup)
    from app.connectors.motive import MotiveConnector
    from app.connectors.torqueai import TorqueAIConnector
    def forbidden(*args, **kwargs):
        pytest.fail("provider called from MCP")
    monkeypatch.setattr(MotiveConnector, "__init__", forbidden)
    monkeypatch.setattr(TorqueAIConnector, "__init__", forbidden)
    statements = []
    def record(conn, cursor, statement, *args):
        statements.append(statement)
    event.listen(setup["engine"], "before_cursor_execute", record)
    try:
        response = call(setup)
    finally:
        event.remove(setup["engine"], "before_cursor_execute", record)
    assert response.json()["result"]["structuredContent"]["summary"]["confirmed_loaded_trailer_count"] == 1
    assert statements and all(s.lstrip().upper().startswith("SELECT ") for s in statements)
    assert not any(term in response.text for term in ("SECRET", "current_driver_name", '"vin"', "provider_payload", "credential"))
    assert result(setup, arguments={"city": "' OR 1=1 --"})["summary"]["confirmed_loaded_trailer_count"] == 0


def test_limit_fails_instead_of_reporting_partial_count(setup, monkeypatch):
    seed(setup)
    monkeypatch.setattr(intelligence, "MAX_DISPATCHES", 0)
    assert result(setup)["error"]["code"] == "RESULT_LIMIT_EXCEEDED"


def test_failed_sync_invalidates_previous_confirmation(setup):
    seed(setup)
    class Failed:
        def _request_json(self, *args, **kwargs):
            raise RuntimeError("SECRET")
    with setup["factory"]() as session:
        value = location_sync.sync_locations(session, organization_id=setup["org"], connector=Failed())
    assert value["status"] == "degraded" and "SECRET" not in str(value)
    assert not result(setup)["trailers"]


def test_sync_machine_auth_flag_and_no_caller_tenant(setup, monkeypatch):
    from app.api import internal_motive
    from app.security.job_auth import sign_job_request
    app = FastAPI(); app.include_router(internal_motive.router)
    client = TestClient(app)
    path = "/api/v1/internal/motive/location-observations/run"
    assert client.post(path).status_code == 401
    monkeypatch.setenv(internal_motive.MOTIVE_CRON_SECRET_ENV_VAR, "test-machine-secret")
    timestamp = str(int(time.time()))
    headers = {"X-Polaris-Job-Timestamp": timestamp, "X-Polaris-Job-Signature": sign_job_request(method="POST", path=path, body=b"", timestamp=timestamp, secret="test-machine-secret")}
    monkeypatch.delenv("POLARIS_MOTIVE_LOCATION_SYNC_ENABLED", raising=False)
    assert client.post(path, headers=headers).status_code == 503
    assert client.post(path + "?organization_id=other", headers=headers).status_code == 400
    monkeypatch.setenv("POLARIS_MOTIVE_LOCATION_SYNC_ENABLED", "true")
    monkeypatch.setenv("POLARIS_MOTIVE_UTILIZATION_SCHEDULED_ORGANIZATION_SLUG", "mor-logistics")
    monkeypatch.setattr(internal_motive, "SessionLocal", setup["factory"])
    # No fleet rows: no provider construction should be necessary in production.
    monkeypatch.setattr(internal_motive, "sync_locations", lambda session, organization_id: {"status": "success"})
    assert client.post(path, headers=headers).status_code == 200


@pytest.mark.parametrize("change", ["identity", "coordinates", "envelope", "timestamp", "lookup_identity"])
def test_malformed_provider_evidence_cannot_confirm(setup, change):
    provider = seed(setup)
    class Malformed:
        def _request_json(self, path, **kwargs):
            payload = provider._request_json(path, **kwargs)
            if path == "/v3/vehicle_locations":
                vehicle = payload["vehicles"][0]["vehicle"]
                if change == "identity": vehicle["id"] = 202
                if change == "coordinates": vehicle["current_location"]["lat"] = float("nan")
                if change == "timestamp": vehicle["current_location"]["located_at"] = "2026-09-12T00:00:00"
                if change == "envelope": return {"other": payload}
            elif change == "lookup_identity":
                payload["vehicle"]["id"] = 202
            return payload
    with setup["factory"]() as session:
        location_sync.sync_locations(session, organization_id=setup["org"], connector=Malformed())
    assert not result(setup)["trailers"]


def test_stop_conflict_and_future_pickup_prevent_confirmation(setup):
    seed(setup)
    with setup["factory"].begin() as session:
        stop = session.query(TorqueAIDispatchStop).filter_by(job="Pick Up").one()
        stop.trailer_number = "OTHER"
        stop.scheduled_pickup_date_text = "2099-01-01"
    flags = result(setup)["uncertain_trailers"][0]["attention_flags"]
    assert "stop_assignment_conflicts_with_dispatch" in flags and "pickup_schedule_in_future" in flags


def test_duplicate_vehicle_number_prevents_confirmation(setup):
    seed(setup)
    with setup["factory"].begin() as session:
        session.add(MotiveVehicleRecord(organization_id=setup["org"], organization_slug="mor-logistics",
                    provider_vehicle_id="202", unit_number="2218", status="active"))
    assert "ambiguous_vehicle_number" in result(setup)["uncertain_trailers"][0]["attention_flags"]


def test_sync_bound_checked_before_provider_calls(setup, monkeypatch):
    provider = seed(setup)
    monkeypatch.setattr(location_sync, "MAX_VEHICLES", 0)
    provider.calls.clear()
    with setup["factory"]() as session, pytest.raises(location_sync.LocationSyncError):
        location_sync.sync_locations(session, organization_id=setup["org"], connector=provider)
    assert not provider.calls


def test_older_collection_cannot_replace_newer_evidence(setup):
    provider = seed(setup)
    with setup["factory"]() as session:
        location_sync.sync_locations(session, organization_id=setup["org"], connector=provider,
                                     now=provider.now - timedelta(hours=3))
    assert result(setup)["summary"]["confirmed_loaded_trailer_count"] == 1


def test_location_age_boundaries_are_inclusive():
    from app.services.location_evidence import fresh, location_confidence, age_minutes
    now = datetime.now(timezone.utc)
    assert fresh(now - timedelta(minutes=120), now)
    assert not fresh(now - timedelta(minutes=120, seconds=1), now)
    assert location_confidence(age_minutes(now - timedelta(minutes=30), now)) == "high"
    assert not fresh(now + timedelta(seconds=1), now)


def test_changed_vehicle_number_invalidates_older_observation(setup):
    seed(setup)
    with setup["factory"].begin() as session:
        session.query(MotiveVehicleRecord).one().unit_number = "RENAMED"
        session.query(TorqueAIDispatch).one().truck_number = "RENAMED"
    flags = result(setup)["uncertain_trailers"][0]["attention_flags"]
    assert "vehicle_number_changed_since_observation" in flags


def test_gps_before_dispatch_assignment_is_uncertain(setup):
    seed(setup)
    with setup["factory"].begin() as session:
        session.query(TorqueAIDispatch).one().last_changed_at = datetime.now(timezone.utc)
    flags = result(setup)["uncertain_trailers"][0]["attention_flags"]
    assert "gps_predates_dispatch_assignment_evidence" in flags


def test_simultaneous_conflicting_assignment_is_uncertain(setup):
    seed(setup)
    add(setup, load="102", truck="OTHER")
    with setup["factory"].begin() as session:
        old, new = session.query(TorqueAIDispatch).order_by(TorqueAIDispatch.id).all()
        new.last_changed_at = old.last_changed_at
        new.status = old.status
        new.last_observed_at = old.last_observed_at
    value = result(setup)
    assert not value["trailers"]
    assert "latest_trailer_assignment_ambiguous" in value["uncertain_trailers"][0]["attention_flags"]


def test_torqueai_unchanged_sync_refreshes_only_returned_rows(setup):
    from app.connectors.torqueai import TorqueAIDispatchPage
    from app.connectors.torqueai_ingestion import ingest_torqueai_dispatches
    from tests.test_torqueai_dispatch_ingestion import _dispatch
    class Provider:
        def fetch_dispatches(self, *, date_from, date_to, page, limit):
            return TorqueAIDispatchPage(data=[_dispatch(5001, "ORD-5001", status="In Transit")],
                total_count=1, page=page, items_per_page=limit, date_from=date_from, date_to=date_to)
    now = datetime.now(timezone.utc)
    with setup["factory"]() as session:
        kwargs = dict(organization_id=setup["org"], organization_slug="mor-logistics",
                      date_from=now.date(), date_to=now.date(), connector=Provider())
        ingest_torqueai_dispatches(session, **kwargs)
        row = session.query(TorqueAIDispatch).one()
        changed, first = row.last_changed_at, row.first_observed_at
        row.last_observed_at = now - timedelta(hours=3)
        session.commit()
        value = ingest_torqueai_dispatches(session, **kwargs)
        session.refresh(row)
        assert value["rows_unchanged"] == 1
        assert row.last_changed_at == changed and row.first_observed_at == first
        assert intelligence.fresh(row.last_observed_at, datetime.now(timezone.utc))
