from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api import assignment_intelligence
from app.database.database import SessionLocal
from app.main import app
from app.models.motive import MotiveDriverRecord, MotiveVehicleRecord
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchStop
from tests.auth_helpers import seed_principal

NOW = datetime.now(timezone.utc)


class FakeMotiveConnector:
    def __init__(self, *, organization_id: str) -> None:
        self.organization_id = organization_id
        self.calls: list[tuple[str, dict, str]] = []

    def _request_json(self, endpoint: str, *, params: dict, operation: str):
        self.calls.append((endpoint, params, operation))
        if endpoint == "/v1/hours_of_service":
            return {
                "hours_of_services": [
                    {
                        "hours_of_service": {
                            "date": params["start_date"],
                            "driver": {"id": 101, "first_name": "Driver", "last_name": "Near", "status": "active"},
                            "driving_duration": 1000,
                            "on_duty_duration": 2000,
                            "off_duty_duration": 5000,
                            "sleeper_duration": 3000,
                            "waiting_duration": 100,
                        }
                    },
                    {
                        "hours_of_service": {
                            "date": params["start_date"],
                            "driver": {"id": 102, "first_name": "Driver", "last_name": "Busy", "status": "active"},
                            "driving_duration": 5000,
                            "on_duty_duration": 7000,
                            "off_duty_duration": 1000,
                            "sleeper_duration": 500,
                            "waiting_duration": 0,
                        }
                    },
                ]
            }
        if endpoint == "/v1/vehicles/lookup":
            if params["number"] == "M-NEAR":
                return {
                    "vehicle": {
                        "number": "M-NEAR",
                        "current_driver": {"id": 101, "first_name": "Driver", "last_name": "Near", "status": "active"},
                        "availability_details": {"availability_status": "in_service"},
                    }
                }
            if params["number"] == "M-FAR":
                return {
                    "vehicle": {
                        "number": "M-FAR",
                        "current_driver": {"id": 102, "first_name": "Driver", "last_name": "Busy", "status": "active"},
                        "availability_details": {"availability_status": "in_service"},
                    }
                }
        if endpoint.endswith("veh-near"):
            return {
                "vehicle_locations": [
                    {"vehicle_location": {"lat": 49.90, "lon": -97.14, "located_at": NOW.isoformat(), "speed": 0, "fuel_primary_remaining_percentage": 75}}
                ]
            }
        if endpoint.endswith("veh-far"):
            return {
                "vehicle_locations": [
                    {"vehicle_location": {"lat": 50.45, "lon": -104.62, "located_at": NOW.isoformat(), "speed": 80, "fuel_primary_remaining_percentage": 55}}
                ]
            }
        return {"vehicle_locations": []}


def _seed_assignment_data(organization: dict[str, str], *, load_number: str = "9101") -> None:
    session = SessionLocal()
    try:
        dispatch = TorqueAIDispatch(
            organization_id=organization["id"],
            provider_load_number=load_number,
            provider_order_number=f"ORD-{load_number}",
            status="Open",
            order_date_text="2026-09-10",
            ship_date_text="2026-09-12",
            delivery_date_text="2026-09-13",
            customer_name="Assignment Customer",
            dispatcher_name="Dispatcher",
            carrier_name="MOR Logistics",
            source_fingerprint=(load_number * 64)[:64],
            first_observed_at=NOW,
            last_changed_at=NOW,
        )
        session.add(dispatch)
        session.flush()
        session.add(
            TorqueAIDispatchStop(
                organization_id=organization["id"],
                dispatch_id=dispatch.id,
                stop_index=0,
                sequence=Decimal("1"),
                job="Pick Up",
                name="Winnipeg Origin",
                city="Winnipeg",
                province="MB",
                country="Canada",
                latitude=Decimal("49.8951"),
                longitude=Decimal("-97.1384"),
                scheduled_pickup_date_text="2026-09-12",
                scheduled_pickup_time_text="09:00",
                source_fingerprint=("p" + load_number * 64)[:64],
                first_observed_at=NOW,
                last_changed_at=NOW,
            )
        )
        session.add_all(
            [
                MotiveVehicleRecord(
                    organization_id=organization["id"],
                    organization_slug=organization["slug"],
                    provider_vehicle_id="veh-far",
                    unit_number="M-FAR",
                    status="active",
                    observed_at=NOW,
                ),
                MotiveVehicleRecord(
                    organization_id=organization["id"],
                    organization_slug=organization["slug"],
                    provider_vehicle_id="veh-near",
                    unit_number="M-NEAR",
                    status="active",
                    observed_at=NOW,
                ),
                MotiveDriverRecord(
                    organization_id=organization["id"],
                    organization_slug=organization["slug"],
                    provider_driver_id="101",
                    name="Driver Near",
                    status="active",
                    observed_at=NOW,
                ),
                MotiveDriverRecord(
                    organization_id=organization["id"],
                    organization_slug=organization["slug"],
                    provider_driver_id="102",
                    name="Driver Busy",
                    status="active",
                    observed_at=NOW,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()


def test_assignment_candidates_pair_truck_and_driver_authoritatively(monkeypatch) -> None:
    organization, _identity, headers = seed_principal("owner")
    _seed_assignment_data(organization)
    monkeypatch.setattr(assignment_intelligence, "MotiveConnector", FakeMotiveConnector)

    response = TestClient(app).get(
        "/api/v1/assignment-intelligence/candidates?load_number=9101&hos_date=2026-09-10",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["truck_candidates"][0]["truck_number"] == "M-NEAR"
    assert payload["truck_candidates"][0]["current_driver"] == {"name": "Driver Near", "status": "active"}
    assert payload["truck_candidates"][0]["current_driver_authoritative"] is True
    assert payload["truck_candidates"][0]["current_driver_source"] == "motive_vehicle_lookup_current_driver"
    assert payload["truck_candidates"][0]["current_driver_hos_observed"]["driving_duration_seconds"] == 1000
    assert payload["truck_candidates"][0]["current_driver_hos_observed"]["is_legal_remaining_hours"] is False
    assert payload["truck_candidates"][0]["dispatch_availability_status"] == "in_service"
    assert payload["driver_candidates"][0]["duration_unit"] == "seconds"
    assert payload["driver_candidates"][0]["duration_unit_certified"] is True
    assert payload["decision_guardrails"]["truck_driver_pairing_inferred"] is False
    assert payload["decision_guardrails"]["authoritative_truck_driver_pairs_present"] is True
    assert payload["decision_guardrails"]["hos_is_legal_remaining_hours"] is False
    assert payload["decision_guardrails"]["hos_duration_unit_certified"] is True
    assert payload["provider_calls"]["motive_vehicle_lookup"] is True
    assert payload["secrets_exposed"] is False


def test_assignment_candidates_flag_stale_top_truck(monkeypatch) -> None:
    organization, _identity, headers = seed_principal("owner")
    _seed_assignment_data(organization, load_number="9151")
    monkeypatch.setattr(assignment_intelligence, "MotiveConnector", FakeMotiveConnector)
    monkeypatch.setattr(assignment_intelligence, "_freshness_minutes", lambda _value: 480.0)

    response = TestClient(app).get(
        "/api/v1/assignment-intelligence/candidates?load_number=9151&hos_date=2026-09-10",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["truck_candidates"][0]["location_confidence"] == "low"
    assert payload["truck_candidates"][0]["location_stale"] is True
    assert payload["truck_candidates"][0]["location_verification_required"] is True
    assert payload["decision_guardrails"]["top_truck_requires_location_verification"] is True


def test_assignment_candidates_are_tenant_scoped(monkeypatch) -> None:
    organization, _identity, headers = seed_principal("owner")
    other, _other_identity, _other_headers = seed_principal("owner")
    _seed_assignment_data(organization, load_number="9201")
    _seed_assignment_data(other, load_number="9999")
    monkeypatch.setattr(assignment_intelligence, "MotiveConnector", FakeMotiveConnector)

    response = TestClient(app).get(
        "/api/v1/assignment-intelligence/candidates?load_number=9999&hos_date=2026-09-10",
        headers=headers,
    )
    assert response.status_code == 404

    own = TestClient(app).get(
        "/api/v1/assignment-intelligence/candidates?load_number=9201&hos_date=2026-09-10",
        headers=headers,
    )
    assert own.status_code == 200
    assert own.json()["tenant_scope_validated"] is True
