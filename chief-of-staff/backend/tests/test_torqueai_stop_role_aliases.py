from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.database.database import SessionLocal
from app.main import app
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchStop
from tests.auth_helpers import seed_principal


def _add_dispatch(*, organization_id: str, load_number: str, stops: list[dict[str, str]]) -> None:
    observed = datetime.now(timezone.utc)
    session = SessionLocal()
    try:
        row = TorqueAIDispatch(
            organization_id=organization_id,
            provider_load_number=load_number,
            provider_order_number=f"ORD-{load_number}",
            status="Dispatched",
            order_date_text="2026-09-10",
            ship_date_text="2026-09-11",
            delivery_date_text="2026-09-12",
            source_fingerprint=(load_number.zfill(64))[-64:],
            first_observed_at=observed,
            last_changed_at=observed,
        )
        session.add(row)
        session.flush()
        for index, stop in enumerate(stops):
            session.add(
                TorqueAIDispatchStop(
                    organization_id=organization_id,
                    dispatch_id=row.id,
                    stop_index=index,
                    job=stop["job"],
                    city=stop["city"],
                    province=stop["province"],
                    country=stop["country"],
                    scheduled_pickup_date_text=stop["date"],
                    source_fingerprint=(f"{load_number}-{index}".encode("utf-8").hex().ljust(64, "0"))[:64],
                    first_observed_at=observed,
                    last_changed_at=observed,
                )
            )
        session.commit()
    finally:
        session.close()


def test_pickup_alias_matches_only_same_manitoba_pickup_stop() -> None:
    organization, _identity, headers = seed_principal("owner")
    _add_dispatch(
        organization_id=organization["id"],
        load_number="91001",
        stops=[
            {"job": "Pick Up", "city": "Winnipeg", "province": "MB", "country": "Canada", "date": "2026-09-11"},
            {"job": "Drop Off", "city": "Laredo", "province": "TX", "country": "USA", "date": "2026-09-12"},
        ],
    )
    _add_dispatch(
        organization_id=organization["id"],
        load_number="91002",
        stops=[
            {"job": "Pick Up", "city": "Regina", "province": "SK", "country": "Canada", "date": "2026-09-11"},
            {"job": "Drop Off", "city": "Winnipeg", "province": "MB", "country": "Canada", "date": "2026-09-11"},
        ],
    )

    response = TestClient(app).get(
        "/api/v1/torqueai/dispatches?stop_role=pickup&stop_province=mb&stop_date=2026-09-11",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request"]["stop_role"] == "pickup"
    assert payload["request"]["stop_date"] == "2026-09-11"
    assert payload["total_count"] == 1
    assert payload["data"][0]["load_number"] == "91001"
    assert payload["provider_called"] is False
    assert payload["tenant_scope_validated"] is True


def test_delivery_alias_maps_to_certified_drop_off_value() -> None:
    organization, _identity, headers = seed_principal("owner")
    _add_dispatch(
        organization_id=organization["id"],
        load_number="92001",
        stops=[
            {"job": "Pick Up", "city": "Brandon", "province": "MB", "country": "Canada", "date": "2026-09-11"},
            {"job": "Drop Off", "city": "Winnipeg", "province": "MB", "country": "Canada", "date": "2026-09-12"},
        ],
    )

    response = TestClient(app).get(
        "/api/v1/torqueai/dispatches?stop_role=delivery&stop_city=winnipeg&stop_date=2026-09-12",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 1
    assert payload["data"][0]["load_number"] == "92001"


def test_stop_role_is_case_insensitive_and_unknown_role_fails_closed() -> None:
    organization, _identity, headers = seed_principal("owner")
    _add_dispatch(
        organization_id=organization["id"],
        load_number="93001",
        stops=[
            {"job": "Pick Up", "city": "Winnipeg", "province": "MB", "country": "Canada", "date": "2026-09-11"},
        ],
    )

    valid = TestClient(app).get(
        "/api/v1/torqueai/dispatches?stop_role=PiCkUp&stop_province=MB",
        headers=headers,
    )
    invalid = TestClient(app).get(
        "/api/v1/torqueai/dispatches?stop_role=transfer",
        headers=headers,
    )

    assert valid.status_code == 200
    assert valid.json()["total_count"] == 1
    assert invalid.status_code == 422
    assert "pickup" in invalid.text
    assert "delivery" in invalid.text


def test_raw_stop_job_remains_backward_compatible_but_cannot_mix_with_role_alias() -> None:
    organization, _identity, headers = seed_principal("owner")
    _add_dispatch(
        organization_id=organization["id"],
        load_number="94001",
        stops=[
            {"job": "Pick Up", "city": "Winnipeg", "province": "MB", "country": "Canada", "date": "2026-09-11"},
        ],
    )

    raw = TestClient(app).get(
        "/api/v1/torqueai/dispatches?stop_job=pick%20up&stop_province=mb",
        headers=headers,
    )
    mixed = TestClient(app).get(
        "/api/v1/torqueai/dispatches?stop_job=Pick%20Up&stop_role=pickup",
        headers=headers,
    )

    assert raw.status_code == 200
    assert raw.json()["total_count"] == 1
    assert mixed.status_code == 422
