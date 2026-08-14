from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.connectors.motive_vehicle_utilization import (
    PARSER_VERSION,
    MotiveVehicleUtilizationParseError,
    MotiveVehicleUtilizationRequestContext,
    associate_vehicle_utilization_rollup,
    associate_vehicle_utilization_rollups,
    parse_vehicle_utilization_rollups,
)
from app.database.database import Base
from app.database.models import register_models
from app.models.motive import MotiveSyncCheckpoint, MotiveVehicleRecord, MotiveVehicleUtilizationRecord

register_models()


def _payload(**overrides: Any) -> dict[str, Any]:
    rollup = {
        "driving_fuel": 19.47,
        "driving_time": 240.25,
        "idle_fuel": 1.75,
        "idle_time": 38.5,
        "utilization": 83.23,
        "ignored_extra": "safe-unused-value",
        "vehicle": {
            "id": "provider-vehicle-secret",
            "make": "SyntheticMake",
            "metric_units": True,
            "model": "SyntheticModel",
            "number": "unit-should-not-retain",
            "vin": "vin-should-not-retain",
            "year": 2024,
        },
    }
    rollup.update(overrides)
    return {"vehicle_idle_rollups": [{"vehicle_idle_rollup": rollup}], "pagination": {"total": 1, "page_no": 1, "per_page": 1}}


def _parse(payload: Any, *, request_context: MotiveVehicleUtilizationRequestContext | None = None):
    return parse_vehicle_utilization_rollups(
        payload,
        organization_id="org-a",
        organization_slug="org-a",
        request_context=request_context,
    )


def test_vehicle_utilization_parser_normalizes_production_rollup_without_period_claims(caplog: pytest.LogCaptureFixture) -> None:
    context = MotiveVehicleUtilizationRequestContext(request_start_date=date(2026, 8, 8), request_end_date=date(2026, 8, 9))

    rollups = _parse(_payload(), request_context=context)

    assert len(rollups) == 1
    rollup = rollups[0]
    assert rollup.organization_id == "org-a"
    assert rollup.organization_slug == "org-a"
    assert rollup.provider == "motive"
    assert rollup.source_endpoint == "/v1/vehicle_utilization"
    assert rollup.provider_vehicle_id == "provider-vehicle-secret"
    assert rollup.utilization_percent == Decimal("83.23")
    assert rollup.idle_time == Decimal("38.5")
    assert rollup.driving_time == Decimal("240.25")
    assert rollup.idle_fuel == Decimal("1.75")
    assert rollup.driving_fuel == Decimal("19.47")
    assert rollup.metric_units is True
    assert rollup.request_start_date == date(2026, 8, 8)
    assert rollup.request_end_date == date(2026, 8, 9)
    assert not hasattr(rollup, "reporting_period_start")
    assert not hasattr(rollup, "reporting_period_end")
    assert rollup.parser_version == PARSER_VERSION
    assert rollup.source_keys == ("driving_fuel", "driving_time", "idle_fuel", "idle_time", "ignored_extra", "utilization", "vehicle")

    rendered = json.dumps(asdict(rollup), sort_keys=True, default=str)
    assert "vin-should-not-retain" not in rendered
    assert "unit-should-not-retain" not in rendered
    assert "SyntheticMake" not in rendered
    assert "SyntheticModel" not in rendered
    assert "provider-vehicle-secret" not in caplog.text
    assert "83.23" not in caplog.text


def test_vehicle_utilization_parser_preserves_zero_and_null_metric_values() -> None:
    rollup = _parse(
        _payload(
            utilization=0,
            idle_time=0.0,
            driving_time=None,
            idle_fuel="0",
            driving_fuel="12.500",
        )
    )[0]

    assert rollup.utilization_percent == Decimal("0")
    assert rollup.idle_time == Decimal("0.0")
    assert rollup.driving_time is None
    assert rollup.idle_fuel == Decimal("0")
    assert rollup.driving_fuel == Decimal("12.500")


def test_vehicle_utilization_parser_ignores_unverified_metric_units_type() -> None:
    rollup = _parse(_payload(vehicle={"id": "provider-vehicle-secret", "metric_units": "metric-value-should-not-retain"}))[0]

    assert rollup.metric_units is None
    assert "metric-value-should-not-retain" not in json.dumps(asdict(rollup), sort_keys=True, default=str)


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ([], "invalid_envelope"),
        ({}, "missing_container"),
        ({"vehicle_idle_rollups": {}}, "invalid_container"),
        ({"vehicle_idle_rollups": ["bad"]}, "invalid_item"),
        ({"vehicle_idle_rollups": [{}]}, "missing_wrapper"),
        ({"vehicle_idle_rollups": [{"vehicle_idle_rollup": []}]}, "invalid_wrapper"),
        ({"vehicle_idle_rollups": [{"vehicle_idle_rollup": {}}]}, "missing_vehicle"),
        ({"vehicle_idle_rollups": [{"vehicle_idle_rollup": {"vehicle": {}}}]}, "missing_vehicle_id"),
        ({"vehicle_idle_rollups": [{"vehicle_idle_rollup": {"vehicle": {"id": None}}}]}, "missing_vehicle_id"),
        ({"vehicle_idle_rollups": [{"vehicle_idle_rollup": {"vehicle": {"id": " "}}}]}, "missing_vehicle_id"),
        ({"vehicle_idle_rollups": [{"vehicle_idle_rollup": {"vehicle": {"id": {"bad": "shape"}}}}]}, "invalid_vehicle_id"),
    ],
)
def test_vehicle_utilization_parser_fails_closed_for_malformed_envelopes(payload: Any, code: str) -> None:
    with pytest.raises(MotiveVehicleUtilizationParseError) as exc_info:
        _parse(payload)

    assert exc_info.value.code == code
    assert "provider-vehicle-secret" not in str(exc_info.value)


@pytest.mark.parametrize("value", [True, False, {"bad": "shape"}, [1], "", "not-a-number", "NaN", "Infinity", float("nan"), float("inf")])
def test_vehicle_utilization_parser_rejects_invalid_metric_types(value: Any) -> None:
    with pytest.raises(MotiveVehicleUtilizationParseError) as exc_info:
        _parse(_payload(utilization=value))

    assert exc_info.value.code == "invalid_metric_type"


def test_vehicle_utilization_parser_rejects_legacy_fixture_shape() -> None:
    with pytest.raises(MotiveVehicleUtilizationParseError) as exc_info:
        _parse({"vehicle_utilization": [{"vehicle": {"id": "provider-vehicle-secret"}}], "pagination": {"total": 1}})

    assert exc_info.value.code == "missing_container"


def test_vehicle_utilization_association_matches_known_org_vehicle_without_writes(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    rollup = _parse(_payload())[0]

    with TestingSession() as session:
        session.add(MotiveVehicleRecord(id=10, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-secret"))
        session.add(MotiveVehicleRecord(id=20, organization_id="org-b", organization_slug="org-b", provider_vehicle_id="provider-vehicle-secret"))
        session.commit()

        def fail_commit() -> None:
            raise AssertionError("association must not commit")

        def fail_flush(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("association must not flush")

        monkeypatch.setattr(session, "commit", fail_commit)
        monkeypatch.setattr(session, "flush", fail_flush)
        association = associate_vehicle_utilization_rollup(session, organization_id="org-a", rollup=rollup)

        assert association.outcome == "matched"
        assert association.motive_vehicle_id == 10
        with session.no_autoflush:
            assert session.query(MotiveVehicleUtilizationRecord).count() == 0

    assert "provider-vehicle-secret" not in caplog.text


def test_vehicle_utilization_association_returns_unknown_for_missing_or_cross_tenant_vehicle(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    rollup = _parse(_payload())[0]

    with TestingSession() as session:
        session.add(MotiveVehicleRecord(id=20, organization_id="org-b", organization_slug="org-b", provider_vehicle_id="provider-vehicle-secret"))
        session.commit()

        def fail_commit() -> None:
            raise AssertionError("association must not commit")

        def fail_flush(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("association must not flush")

        monkeypatch.setattr(session, "commit", fail_commit)
        monkeypatch.setattr(session, "flush", fail_flush)
        association = associate_vehicle_utilization_rollup(session, organization_id="org-a", rollup=rollup)

        assert association.outcome == "unknown_vehicle"
        assert association.motive_vehicle_id is None
        with session.no_autoflush:
            assert session.query(MotiveVehicleRecord).filter_by(organization_id="org-a").count() == 0
            assert session.query(MotiveVehicleUtilizationRecord).count() == 0


def test_vehicle_utilization_association_handles_multiple_rollups() -> None:
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    rollups = [
        _parse(_payload(vehicle={"id": "known-vehicle", "metric_units": True}))[0],
        _parse(_payload(vehicle={"id": "unknown-vehicle", "metric_units": True}))[0],
    ]

    with TestingSession() as session:
        session.add(MotiveVehicleRecord(id=10, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="known-vehicle"))
        session.commit()
        associations = associate_vehicle_utilization_rollups(session, organization_id="org-a", rollups=rollups)

    assert [association.outcome for association in associations] == ["matched", "unknown_vehicle"]
    assert [association.motive_vehicle_id for association in associations] == [10, None]


def test_vehicle_utilization_persistence_shape_preserves_zero_and_null_metric_values() -> None:
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestingSession() as session:
        vehicle = MotiveVehicleRecord(
            id=10,
            organization_id="org-a",
            organization_slug="org-a",
            provider_vehicle_id="known-vehicle",
        )
        session.add(vehicle)
        session.add(
            MotiveVehicleUtilizationRecord(
                organization_id="org-a",
                organization_slug="org-a",
                provider_vehicle_id="known-vehicle",
                motive_vehicle_id=vehicle.id,
                request_window_start=date(2026, 8, 8),
                request_window_end=date(2026, 8, 9),
                reporting_period_start=None,
                reporting_period_end=None,
                utilization_percent=Decimal("0"),
                idle_time=Decimal("0.0000"),
                driving_time=None,
                idle_fuel=Decimal("0.0000"),
                driving_fuel=None,
                metric_units=False,
                observed_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
                parser_version=PARSER_VERSION,
                provider_payload_metadata={"parser_version": PARSER_VERSION, "source": "schema_hardening_test"},
            )
        )
        session.commit()

        saved = session.query(MotiveVehicleUtilizationRecord).one()
        assert saved.organization_id == "org-a"
        assert saved.provider_vehicle_id == "known-vehicle"
        assert saved.motive_vehicle_id == 10
        assert saved.utilization_percent == Decimal("0.0000")
        assert saved.idle_time == Decimal("0.0000")
        assert saved.driving_time is None
        assert saved.idle_fuel == Decimal("0.0000")
        assert saved.driving_fuel is None
        assert saved.metric_units is False
        assert saved.parser_version == PARSER_VERSION


def test_vehicle_utilization_schema_keeps_request_window_separate_from_reporting_period() -> None:
    record = MotiveVehicleUtilizationRecord(
        organization_id="org-a",
        organization_slug="org-a",
        provider_vehicle_id="known-vehicle",
        request_window_start=date(2026, 8, 8),
        request_window_end=date(2026, 8, 9),
        reporting_period_start=None,
        reporting_period_end=None,
    )

    assert record.request_window_start == date(2026, 8, 8)
    assert record.request_window_end == date(2026, 8, 9)
    assert record.reporting_period_start is None
    assert record.reporting_period_end is None


def test_vehicle_utilization_schema_supports_known_vehicle_reference_without_auto_create() -> None:
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestingSession() as session:
        vehicle = MotiveVehicleRecord(
            id=10,
            organization_id="org-a",
            organization_slug="org-a",
            provider_vehicle_id="known-vehicle",
        )
        session.add(vehicle)
        session.commit()

        session.add(
            MotiveVehicleUtilizationRecord(
                organization_id="org-a",
                organization_slug="org-a",
                provider_vehicle_id="known-vehicle",
                motive_vehicle_id=vehicle.id,
                request_window_start=date(2026, 8, 8),
                request_window_end=date(2026, 8, 9),
            )
        )
        session.commit()

        assert session.query(MotiveVehicleRecord).filter_by(organization_id="org-a").count() == 1
        assert session.query(MotiveVehicleRecord).filter_by(organization_id="org-b").count() == 0
        saved = session.query(MotiveVehicleUtilizationRecord).one()
        assert saved.motive_vehicle_id == 10
        assert saved.motive_vehicle.provider_vehicle_id == "known-vehicle"


def test_vehicle_utilization_parser_and_association_do_not_mutate_checkpoint_or_utilization_tables() -> None:
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    rollup = _parse(_payload())[0]

    with TestingSession() as session:
        session.add(MotiveVehicleRecord(id=10, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="provider-vehicle-secret"))
        session.commit()

        association = associate_vehicle_utilization_rollup(session, organization_id="org-a", rollup=rollup)

        assert association.outcome == "matched"
        assert session.query(MotiveVehicleUtilizationRecord).count() == 0
        assert session.query(MotiveSyncCheckpoint).count() == 0
