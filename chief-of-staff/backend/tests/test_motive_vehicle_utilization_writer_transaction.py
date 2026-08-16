"""Tests for the internal, all-or-nothing Motive vehicle-utilization writer
transaction primitive.

This gate proves ``write_vehicle_utilization_transaction`` (see
``app/motive/vehicle_utilization_writer.py``):

- makes zero Motive HTTP calls;
- validates the ENTIRE incoming batch before staging any row (whole-batch,
  all-or-nothing);
- owns exactly one commit per successful call and rolls back on any failure;
- persists only returned rollups that resolve to an existing tenant-owned
  ``MotiveVehicleRecord``;
- never auto-creates a vehicle, never touches ``MotiveSyncCheckpoint`` or
  ``MotiveSyncHistory``;
- treats identical replays as no-ops, fails closed on conflicting replays,
  and never updates an existing row in this gate (``records_updated`` stays
  0);
- never exposes provider vehicle IDs, VIN, unit numbers, or metric values in
  its result type, its errors, or its logging.

No live Motive provider call is made anywhere in this module.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.connectors.motive_vehicle_utilization import MotiveVehicleUtilizationRollup
from app.database.database import Base
from app.database.models import register_models
from app.models.motive import (
    MotiveSyncCheckpoint,
    MotiveSyncHistory,
    MotiveVehicleRecord,
    MotiveVehicleUtilizationRecord,
)
from app.motive import vehicle_utilization_writer as writer_module
from app.motive.vehicle_utilization_unit_policy import VehicleUtilizationUnitPersistenceReadiness
from app.motive.vehicle_utilization_writer import (
    CERTIFIED_PARSER_VERSION,
    CERTIFIED_SOURCE_ENDPOINT,
    MotiveVehicleUtilizationWriterError,
    VehicleUtilizationWriteResult,
    write_vehicle_utilization_transaction,
)
from app.organizations.models import Organization

register_models()

WINDOW_START = date(2026, 8, 12)
WINDOW_END = date(2026, 8, 13)

UNSAFE_PROVIDER_VEHICLE_ID = "provider-vehicle-should-not-leak-9911"


# ---------------------------------------------------------------------------
# 2026-08-16 unit-context reconciliation gate.
#
# Motive's returned vehicle.metric_units Boolean semantics are now unresolved
# (see app/motive/vehicle_utilization_unit_policy.py): the writer's step-6
# unit-context readiness gate fails closed for EVERY returned value -- True
# included -- until that relationship is explicitly certified. The dedicated
# unit-readiness tests below (marked ``unit_readiness_gate``) exercise that
# real, fail-closed behavior directly.
#
# The rest of this suite tests batching, tenancy, replay, and provenance
# concerns that are orthogonal to unit-indicator semantics. Those tests are
# transparently bypassed past the still-unresolved unit gate below so they
# can keep exercising the specific step (duplicate detection, tenant
# resolution, parser/source provenance, replay conflict, whole-batch
# rollback, database-uniqueness) they were written to prove.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _bypass_unresolved_unit_gate_for_unrelated_concerns(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    if request.node.get_closest_marker("unit_readiness_gate") is not None:
        yield
        return
    monkeypatch.setattr(
        writer_module,
        "validate_vehicle_utilization_unit_persistence_readiness",
        lambda returned_metric_units: VehicleUtilizationUnitPersistenceReadiness(ready_for_durable_persistence=True),
    )
    yield


def _session_factory(tmp_path, name: str = "writer"):
    database_url = f"sqlite:///{(tmp_path / f'{name}.db').as_posix()}"
    engine = create_engine(database_url)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession


def _seed(
    TestingSession,
    *,
    organization_id: str = "org-a",
    organization_slug: str = "org-a",
    provider_vehicle_ids: tuple[str, ...] = ("veh-1",),
) -> None:
    with TestingSession.begin() as session:
        if session.get(Organization, organization_id) is None:
            session.add(Organization(id=organization_id, slug=organization_slug, display_name=organization_id))
        for provider_vehicle_id in provider_vehicle_ids:
            session.add(
                MotiveVehicleRecord(
                    organization_id=organization_id,
                    organization_slug=organization_slug,
                    provider_vehicle_id=provider_vehicle_id,
                )
            )


def _rollup(
    provider_vehicle_id: str,
    *,
    organization_id: str = "org-a",
    organization_slug: str = "org-a",
    utilization_percent: Decimal | None = Decimal("50.0000"),
    idle_time: Decimal | None = Decimal("100.0000"),
    driving_time: Decimal | None = Decimal("200.0000"),
    idle_fuel: Decimal | None = Decimal("1.0000"),
    driving_fuel: Decimal | None = Decimal("2.0000"),
    metric_units=True,
    request_start_date: date | None = WINDOW_START,
    request_end_date: date | None = WINDOW_END,
    source_endpoint: str = CERTIFIED_SOURCE_ENDPOINT,
    parser_version: str = CERTIFIED_PARSER_VERSION,
) -> MotiveVehicleUtilizationRollup:
    return MotiveVehicleUtilizationRollup(
        organization_id=organization_id,
        organization_slug=organization_slug,
        provider_vehicle_id=provider_vehicle_id,
        source_endpoint=source_endpoint,
        utilization_percent=utilization_percent,
        idle_time=idle_time,
        driving_time=driving_time,
        idle_fuel=idle_fuel,
        driving_fuel=driving_fuel,
        metric_units=metric_units,
        request_start_date=request_start_date,
        request_end_date=request_end_date,
        parser_version=parser_version,
    )


def _row_count(TestingSession) -> int:
    with TestingSession() as session:
        return session.query(MotiveVehicleUtilizationRecord).count()


def _checkpoint_and_history_counts(TestingSession) -> tuple[int, int]:
    with TestingSession() as session:
        return (
            session.query(MotiveSyncCheckpoint).count(),
            session.query(MotiveSyncHistory).count(),
        )


# ---------------------------------------------------------------------------
# Section 30 — successful insert.
# ---------------------------------------------------------------------------
def test_successful_insert_persists_exactly_one_certified_row(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))
    checkpoints_before, history_before = _checkpoint_and_history_counts(TestingSession)

    with TestingSession() as session:
        result = write_vehicle_utilization_transaction(
            session,
            organization_id="org-a",
            organization_slug="org-a",
            selected_provider_vehicle_ids=["veh-1"],
            request_window_start=WINDOW_START,
            request_window_end=WINDOW_END,
            rollups=[_rollup("veh-1")],
        )

    assert result == VehicleUtilizationWriteResult(
        committed=True,
        requested_vehicle_count=1,
        returned_rollup_count=1,
        records_inserted=1,
        records_unchanged=0,
        records_updated=0,
        missing_requested_vehicle_count=0,
    )

    with TestingSession() as session:
        rows = session.query(MotiveVehicleUtilizationRecord).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.organization_id == "org-a"
        assert row.organization_slug == "org-a"
        assert row.provider == "motive"
        assert row.provider_vehicle_id == "veh-1"
        assert row.motive_vehicle_id is not None
        assert row.request_window_start == WINDOW_START
        assert row.request_window_end == WINDOW_END
        assert row.metric_units is True
        assert row.parser_version == CERTIFIED_PARSER_VERSION
        assert row.source_endpoint == CERTIFIED_SOURCE_ENDPOINT
        assert row.reporting_period_start is None
        assert row.reporting_period_end is None
        assert row.observed_at is None
        assert row.distance is None
        assert row.engine_hours is None

    checkpoints_after, history_after = _checkpoint_and_history_counts(TestingSession)
    assert checkpoints_after == checkpoints_before
    assert history_after == history_before


def test_writer_transaction_commits_exactly_once(tmp_path, monkeypatch) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2"))

    with TestingSession() as session:
        commit_calls = []
        original_commit = session.commit

        def counted_commit():
            commit_calls.append(1)
            return original_commit()

        monkeypatch.setattr(session, "commit", counted_commit)
        write_vehicle_utilization_transaction(
            session,
            organization_id="org-a",
            organization_slug="org-a",
            selected_provider_vehicle_ids=["veh-1", "veh-2"],
            request_window_start=WINDOW_START,
            request_window_end=WINDOW_END,
            rollups=[_rollup("veh-1"), _rollup("veh-2")],
        )
        assert len(commit_calls) == 1


# ---------------------------------------------------------------------------
# Section 31 — multi-row atomic success.
# ---------------------------------------------------------------------------
def test_multi_row_atomic_success_with_one_missing_selected_vehicle(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    checkpoints_before, history_before = _checkpoint_and_history_counts(TestingSession)

    with TestingSession() as session:
        result = write_vehicle_utilization_transaction(
            session,
            organization_id="org-a",
            organization_slug="org-a",
            selected_provider_vehicle_ids=["veh-1", "veh-2", "veh-3"],
            request_window_start=WINDOW_START,
            request_window_end=WINDOW_END,
            # veh-2 not returned by Motive.
            rollups=[_rollup("veh-1"), _rollup("veh-3")],
        )

    assert result.records_inserted == 2
    assert result.records_unchanged == 0
    assert result.records_updated == 0
    assert result.missing_requested_vehicle_count == 1
    assert _row_count(TestingSession) == 2
    checkpoints_after, history_after = _checkpoint_and_history_counts(TestingSession)
    assert checkpoints_after == checkpoints_before
    assert history_after == history_before


# ---------------------------------------------------------------------------
# Section 32 — identical replay.
# ---------------------------------------------------------------------------
def test_identical_replay_is_a_no_op(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2"))

    kwargs = dict(
        organization_id="org-a",
        organization_slug="org-a",
        selected_provider_vehicle_ids=["veh-1", "veh-2"],
        request_window_start=WINDOW_START,
        request_window_end=WINDOW_END,
        rollups=[_rollup("veh-1"), _rollup("veh-2")],
    )

    with TestingSession() as session:
        first = write_vehicle_utilization_transaction(session, **kwargs)
    assert first.records_inserted == 2
    assert _row_count(TestingSession) == 2

    with TestingSession() as session:
        second = write_vehicle_utilization_transaction(session, **kwargs)
    assert second.records_inserted == 0
    assert second.records_unchanged == 2
    assert second.records_updated == 0
    assert _row_count(TestingSession) == 2


# ---------------------------------------------------------------------------
# Section 33 — conflicting replay (several dimensions).
# ---------------------------------------------------------------------------
def test_conflicting_replay_metric_value_fails_closed(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        write_vehicle_utilization_transaction(
            session,
            organization_id="org-a",
            organization_slug="org-a",
            selected_provider_vehicle_ids=["veh-1"],
            request_window_start=WINDOW_START,
            request_window_end=WINDOW_END,
            rollups=[_rollup("veh-1", idle_time=Decimal("100.0000"))],
        )

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1", idle_time=Decimal("999.0000"))],
            )
    assert exc_info.value.code == "conflicting_existing_identity"
    assert _row_count(TestingSession) == 1
    with TestingSession() as session:
        row = session.query(MotiveVehicleUtilizationRecord).one()
        assert row.idle_time == Decimal("100.0000")


def test_conflicting_replay_incompatible_existing_unit_context_fails_closed(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession.begin() as session:
        vehicle = session.query(MotiveVehicleRecord).filter_by(provider_vehicle_id="veh-1").one()
        # Simulate a legacy row that predates the certified writer contract:
        # it carries an incompatible (non-True) unit context on the certified
        # identity key.
        session.add(
            MotiveVehicleUtilizationRecord(
                organization_id="org-a",
                organization_slug="org-a",
                provider_vehicle_id="veh-1",
                motive_vehicle_id=vehicle.id,
                source_endpoint=CERTIFIED_SOURCE_ENDPOINT,
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                utilization_percent=Decimal("50.0000"),
                idle_time=Decimal("100.0000"),
                driving_time=Decimal("200.0000"),
                idle_fuel=Decimal("1.0000"),
                driving_fuel=Decimal("2.0000"),
                metric_units=False,
                parser_version=CERTIFIED_PARSER_VERSION,
            )
        )

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1")],
            )
    assert exc_info.value.code == "conflicting_existing_identity"
    assert _row_count(TestingSession) == 1
    with TestingSession() as session:
        row = session.query(MotiveVehicleUtilizationRecord).one()
        assert row.metric_units is False


def test_conflicting_replay_incompatible_existing_source_provenance_fails_closed(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession.begin() as session:
        vehicle = session.query(MotiveVehicleRecord).filter_by(provider_vehicle_id="veh-1").one()
        session.add(
            MotiveVehicleUtilizationRecord(
                organization_id="org-a",
                organization_slug="org-a",
                provider_vehicle_id="veh-1",
                motive_vehicle_id=vehicle.id,
                # Incompatible/ambiguous provenance: different source endpoint.
                source_endpoint="/v2/vehicle_utilization",
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                utilization_percent=Decimal("50.0000"),
                idle_time=Decimal("100.0000"),
                driving_time=Decimal("200.0000"),
                idle_fuel=Decimal("1.0000"),
                driving_fuel=Decimal("2.0000"),
                metric_units=True,
                parser_version=CERTIFIED_PARSER_VERSION,
            )
        )

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1")],
            )
    assert exc_info.value.code == "conflicting_existing_identity"
    assert _row_count(TestingSession) == 1


# ---------------------------------------------------------------------------
# Section 34 — unknown vehicle.
# ---------------------------------------------------------------------------
def test_unknown_vehicle_fails_closed_with_no_partial_writes(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    # veh-1 is stored; veh-2 is selected but never persisted as a vehicle.
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1", "veh-2"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1"), _rollup("veh-2")],
            )
    assert exc_info.value.code == "unknown_vehicle"
    assert _row_count(TestingSession) == 0
    with TestingSession() as session:
        assert session.query(MotiveVehicleRecord).filter_by(provider_vehicle_id="veh-2").count() == 0


# ---------------------------------------------------------------------------
# Section 35 — cross-tenant vehicle.
# ---------------------------------------------------------------------------
def test_cross_tenant_vehicle_is_unknown_for_caller_organization(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, organization_id="org-a", organization_slug="org-a", provider_vehicle_ids=())
    _seed(TestingSession, organization_id="org-b", organization_slug="org-b", provider_vehicle_ids=("shared-vehicle-id",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["shared-vehicle-id"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("shared-vehicle-id")],
            )
    assert exc_info.value.code == "unknown_vehicle"
    assert "shared-vehicle-id" not in str(exc_info.value)
    assert _row_count(TestingSession) == 0

    with TestingSession() as session:
        org_a_rows = (
            session.query(MotiveVehicleUtilizationRecord).filter(MotiveVehicleUtilizationRecord.organization_id == "org-a").count()
        )
        assert org_a_rows == 0


# ---------------------------------------------------------------------------
# Section 36 — unexpected vehicle (not in selected set).
# ---------------------------------------------------------------------------
def test_unexpected_returned_vehicle_fails_closed_before_write(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2"))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1"), _rollup("veh-2")],
            )
    assert exc_info.value.code == "unexpected_returned_vehicle"
    assert _row_count(TestingSession) == 0


# ---------------------------------------------------------------------------
# Section 37 — duplicate returned rollup.
# ---------------------------------------------------------------------------
def test_duplicate_returned_rollup_fails_closed_no_dedup(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1", idle_time=Decimal("1")), _rollup("veh-1", idle_time=Decimal("2"))],
            )
    assert exc_info.value.code == "duplicate_returned_rollup"
    assert _row_count(TestingSession) == 0


# ---------------------------------------------------------------------------
# Section 38 — unit policy (2026-08-16: redesigned persistence-readiness
# gate). True, False, and None all currently fail closed with the SAME
# neutral "unresolved" code -- none of these tests may assert or imply what
# a returned False or None *means*.
# ---------------------------------------------------------------------------
@pytest.mark.unit_readiness_gate
def test_metric_units_true_does_not_automatically_certify_and_fails_closed(tmp_path) -> None:
    """Returned True must never be treated as automatically certified --
    zero rows are written even though the returned Boolean matches the
    requested Boolean."""
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1", metric_units=True)],
            )
    assert exc_info.value.code == "provider_unit_indicator_semantics_unresolved"
    assert _row_count(TestingSession) == 0


@pytest.mark.unit_readiness_gate
def test_metric_units_false_fails_closed_without_being_interpreted_as_imperial(tmp_path) -> None:
    """Returned False fails closed using the SAME neutral code as True and
    None -- it is never interpreted as imperial or as evidence the header
    was ignored."""
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1", metric_units=False)],
            )
    assert exc_info.value.code == "provider_unit_indicator_semantics_unresolved"
    assert _row_count(TestingSession) == 0


@pytest.mark.unit_readiness_gate
def test_metric_units_none_remains_unresolved_and_fails_closed(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1", metric_units=None)],
            )
    assert exc_info.value.code == "provider_unit_indicator_semantics_unresolved"
    assert _row_count(TestingSession) == 0


@pytest.mark.unit_readiness_gate
def test_no_returned_unit_value_is_ready_for_durable_persistence_in_this_gate(tmp_path) -> None:
    """Writer persists zero rows in this state, for every observed returned
    value, no checkpoint/history writes either way."""
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2", "veh-3"))
    checkpoints_before, history_before = _checkpoint_and_history_counts(TestingSession)

    for provider_vehicle_id, metric_units in (("veh-1", True), ("veh-2", False), ("veh-3", None)):
        with TestingSession() as session:
            with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
                write_vehicle_utilization_transaction(
                    session,
                    organization_id="org-a",
                    organization_slug="org-a",
                    selected_provider_vehicle_ids=[provider_vehicle_id],
                    request_window_start=WINDOW_START,
                    request_window_end=WINDOW_END,
                    rollups=[_rollup(provider_vehicle_id, metric_units=metric_units)],
                )
        assert exc_info.value.code == "provider_unit_indicator_semantics_unresolved"

    assert _row_count(TestingSession) == 0
    checkpoints_after, history_after = _checkpoint_and_history_counts(TestingSession)
    assert checkpoints_after == checkpoints_before
    assert history_after == history_before


@pytest.mark.unit_readiness_gate
def test_malformed_returned_unit_type_fails_closed_with_a_distinct_code(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1", metric_units="metric-value-should-not-retain")],
            )
    assert exc_info.value.code == "provider_unit_context_invalid_type"
    assert _row_count(TestingSession) == 0


# ---------------------------------------------------------------------------
# Section 39 — window validation.
# ---------------------------------------------------------------------------
def test_rollup_missing_request_start_date_fails_closed(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1", request_start_date=None)],
            )
    assert exc_info.value.code == "request_window_missing"
    assert _row_count(TestingSession) == 0


def test_rollup_missing_request_end_date_fails_closed(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1", request_end_date=None)],
            )
    assert exc_info.value.code == "request_window_missing"
    assert _row_count(TestingSession) == 0


def test_rollup_window_differs_from_caller_window_fails_closed(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1", request_start_date=date(2026, 8, 1))],
            )
    assert exc_info.value.code == "request_window_invalid"
    assert _row_count(TestingSession) == 0


def test_caller_start_after_end_fails_closed_before_touching_rollups(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_END,
                request_window_end=WINDOW_START,
                rollups=[_rollup("veh-1")],
            )
    assert exc_info.value.code == "request_window_invalid"
    assert _row_count(TestingSession) == 0


# ---------------------------------------------------------------------------
# Section 40 — parser / source certification.
# ---------------------------------------------------------------------------
def test_incompatible_parser_version_fails_closed(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1", parser_version="motive_vehicle_idle_rollup_v2")],
            )
    assert exc_info.value.code == "parser_version_not_certified"
    assert _row_count(TestingSession) == 0


def test_incompatible_source_endpoint_fails_closed(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1", source_endpoint="/v2/vehicle_utilization")],
            )
    assert exc_info.value.code == "source_endpoint_not_certified"
    assert _row_count(TestingSession) == 0


# ---------------------------------------------------------------------------
# Section 41 — zero-result transaction.
# ---------------------------------------------------------------------------
def test_zero_returned_rollups_is_a_successful_no_op(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2"))
    checkpoints_before, history_before = _checkpoint_and_history_counts(TestingSession)

    with TestingSession() as session:
        result = write_vehicle_utilization_transaction(
            session,
            organization_id="org-a",
            organization_slug="org-a",
            selected_provider_vehicle_ids=["veh-1", "veh-2"],
            request_window_start=WINDOW_START,
            request_window_end=WINDOW_END,
            rollups=[],
        )

    assert result.committed is True
    assert result.records_inserted == 0
    assert result.records_unchanged == 0
    assert result.records_updated == 0
    assert result.missing_requested_vehicle_count == 2
    assert _row_count(TestingSession) == 0
    checkpoints_after, history_after = _checkpoint_and_history_counts(TestingSession)
    assert checkpoints_after == checkpoints_before
    assert history_after == history_before


# ---------------------------------------------------------------------------
# Section 42 — whole-batch rollback.
# ---------------------------------------------------------------------------
def test_whole_batch_rollback_when_second_rollup_fails_late(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    # veh-1 is stored and fully valid. veh-2 is selected but has no stored
    # MotiveVehicleRecord, so batch resolution fails at step 8 -- after both
    # rollups already passed structural/window/duplicate/unit/parser checks.
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1", "veh-2"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1"), _rollup("veh-2")],
            )
    assert exc_info.value.code == "unknown_vehicle"
    assert _row_count(TestingSession) == 0


def test_whole_batch_rollback_when_second_rollup_conflicts_at_replay_check(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1", "veh-2"))

    with TestingSession() as session:
        write_vehicle_utilization_transaction(
            session,
            organization_id="org-a",
            organization_slug="org-a",
            selected_provider_vehicle_ids=["veh-2"],
            request_window_start=WINDOW_START,
            request_window_end=WINDOW_END,
            rollups=[_rollup("veh-2", idle_time=Decimal("100.0000"))],
        )
    assert _row_count(TestingSession) == 1

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1", "veh-2"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                # veh-1 would be a brand-new valid insert; veh-2 conflicts.
                rollups=[_rollup("veh-1"), _rollup("veh-2", idle_time=Decimal("999.0000"))],
            )
    assert exc_info.value.code == "conflicting_existing_identity"
    # The veh-1 insert must NOT have been committed even though it was valid.
    assert _row_count(TestingSession) == 1
    with TestingSession() as session:
        assert session.query(MotiveVehicleUtilizationRecord).filter_by(provider_vehicle_id="veh-1").count() == 0


# ---------------------------------------------------------------------------
# Section 43 — database uniqueness constraint as the final concurrency guard.
# ---------------------------------------------------------------------------
def test_database_identity_conflict_final_guard_rolls_back_and_is_sanitized(tmp_path, monkeypatch) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        write_vehicle_utilization_transaction(
            session,
            organization_id="org-a",
            organization_slug="org-a",
            selected_provider_vehicle_ids=["veh-1"],
            request_window_start=WINDOW_START,
            request_window_end=WINDOW_END,
            rollups=[_rollup("veh-1")],
        )
    assert _row_count(TestingSession) == 1

    # Simulate the race window described in section 22/43: the application
    # preflight query does not see the (already-committed) existing row, so
    # the writer attempts to insert a duplicate and must rely on the real
    # database uniqueness constraint as the final guard.
    monkeypatch.setattr(writer_module, "_load_existing_identity_rows", lambda *args, **kwargs: {})

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1")],
            )
    assert exc_info.value.code == "database_identity_conflict"
    assert "veh-1" not in str(exc_info.value)
    # No partial/duplicate row, no retry-created row.
    assert _row_count(TestingSession) == 1
    checkpoints, history = _checkpoint_and_history_counts(TestingSession)
    assert checkpoints == 0
    assert history == 0


# ---------------------------------------------------------------------------
# Section 44 — public contract security / sanitized errors.
# ---------------------------------------------------------------------------
def test_errors_never_leak_provider_vehicle_ids_or_metrics(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[
                    _rollup(UNSAFE_PROVIDER_VEHICLE_ID, utilization_percent=Decimal("13.3700")),
                ],
            )
    rendered = str(exc_info.value)
    assert UNSAFE_PROVIDER_VEHICLE_ID not in rendered
    assert "13.3700" not in rendered


def test_write_result_carries_only_sanitized_counts(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=(UNSAFE_PROVIDER_VEHICLE_ID,))

    with TestingSession() as session:
        result = write_vehicle_utilization_transaction(
            session,
            organization_id="org-a",
            organization_slug="org-a",
            selected_provider_vehicle_ids=[UNSAFE_PROVIDER_VEHICLE_ID],
            request_window_start=WINDOW_START,
            request_window_end=WINDOW_END,
            rollups=[_rollup(UNSAFE_PROVIDER_VEHICLE_ID, utilization_percent=Decimal("13.3700"))],
        )
    rendered = repr(result)
    assert UNSAFE_PROVIDER_VEHICLE_ID not in rendered
    assert "13.3700" not in rendered
    assert {field.name for field in dataclasses.fields(result)} == {
        "committed",
        "requested_vehicle_count",
        "returned_rollup_count",
        "records_inserted",
        "records_unchanged",
        "records_updated",
        "missing_requested_vehicle_count",
    }


# ---------------------------------------------------------------------------
# Section 45 — logging.
# ---------------------------------------------------------------------------
def test_success_log_record_is_sanitized(tmp_path, caplog) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=(UNSAFE_PROVIDER_VEHICLE_ID,))

    with caplog.at_level(logging.INFO, logger="app.motive.vehicle_utilization_writer"):
        with TestingSession() as session:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=[UNSAFE_PROVIDER_VEHICLE_ID],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup(UNSAFE_PROVIDER_VEHICLE_ID, utilization_percent=Decimal("13.3700"))],
            )

    write_records = [record for record in caplog.records if record.name == "app.motive.vehicle_utilization_writer"]
    assert write_records, "expected at least one sanitized writer log record"
    for record in write_records:
        rendered = record.getMessage() + " ".join(str(v) for v in vars(record).values())
        assert UNSAFE_PROVIDER_VEHICLE_ID not in rendered
        assert "13.3700" not in rendered
    assert write_records[0].organization_id == "org-a"
    assert write_records[0].records_inserted == 1


# ---------------------------------------------------------------------------
# Additional structural / request-context guards.
# ---------------------------------------------------------------------------
def test_empty_selected_vehicle_set_fails_closed(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=[],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[],
            )
    assert exc_info.value.code == "invalid_writer_request"


def test_duplicate_selected_vehicle_ids_fail_closed(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1", "veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[],
            )
    assert exc_info.value.code == "invalid_writer_request"


def test_rollup_organization_mismatch_fails_closed(tmp_path) -> None:
    TestingSession = _session_factory(tmp_path)
    _seed(TestingSession, provider_vehicle_ids=("veh-1",))

    with TestingSession() as session:
        with pytest.raises(MotiveVehicleUtilizationWriterError) as exc_info:
            write_vehicle_utilization_transaction(
                session,
                organization_id="org-a",
                organization_slug="org-a",
                selected_provider_vehicle_ids=["veh-1"],
                request_window_start=WINDOW_START,
                request_window_end=WINDOW_END,
                rollups=[_rollup("veh-1", organization_id="org-b")],
            )
    assert exc_info.value.code == "organization_context_mismatch"
    assert _row_count(TestingSession) == 0
