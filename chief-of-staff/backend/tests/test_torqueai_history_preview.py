"""Synthetic-only regression coverage; never invokes production/provider infrastructure."""
from datetime import date, datetime, timezone
import json
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session

from app.connectors.torqueai import TorqueAIConnector, TorqueAIDispatchPage
from app.connectors.torqueai_history_preview import _select_only_connection, preview_torqueai_history
from app.connectors.torqueai_ingestion import TorqueAIDispatchIngestionError
from app.connectors.torqueai_operational_ingestion import ingest_torqueai_dispatches
from app.models.torqueai import (
    TorqueAIDispatch, TorqueAIDispatchOperational, TorqueAIDispatchStop,
    TorqueAIDispatchSyncRun, TorqueAIDispatchSyncState,
)
from app.organizations.models import Organization

DAY = date(2025, 6, 1)
TABLES = [Organization.__table__, TorqueAIDispatch.__table__, TorqueAIDispatchOperational.__table__,
          TorqueAIDispatchStop.__table__, TorqueAIDispatchSyncRun.__table__, TorqueAIDispatchSyncState.__table__]


def dispatch(load=1, order="A", **overrides):
    raw = {"loadNumber": load, "orderNumber": order, "customerName": "Synthetic Customer",
           "shipDate": DAY.isoformat(), "stops": [
               {"job": "Pick Up", "city": "Winnipeg", "province": "MB", "country": "CAN"},
               {"job": "Drop Off", "city": "Laredo", "province": "TX", "country": "USA"}]}
    raw.update(overrides)
    return raw


class Provider:
    organization_slug = "mor-logistics"

    def __init__(self, records, *, total=None, size=100, changed_total=False):
        self.records = records
        self.total = len(records) if total is None else total
        self.size = size
        self.calls = []
        self.changed_total = changed_total

    def fetch_dispatches(self, *, date_from, date_to, page, limit):
        self.calls.append((date_from, date_to, page, limit))
        data = self.records[(page - 1) * self.size:page * self.size]
        return TorqueAIDispatchPage(tuple(data), self.total + int(self.changed_total and page > 1),
                                    page, self.size, date_from, date_to)


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'preview.db'}")
    for table in TABLES:
        table.create(engine)
    with engine.begin() as connection:
        connection.execute(Organization.__table__.insert(), [
            {"id": "mor", "slug": "mor-logistics", "display_name": "MOR", "status": "active"},
            {"id": "other", "slug": "other", "display_name": "Other", "status": "active"}])
    monkeypatch.setenv("POLARIS_TORQUEAI_ORGANIZATION_SLUG", "mor-logistics")
    yield engine
    engine.dispose()


def seed(engine, records, tenant="mor"):
    with Session(engine, autoflush=False) as session:
        ingest_torqueai_dispatches(session, organization_id=tenant, organization_slug="mor-logistics",
                                  date_from=DAY, date_to=DAY, connector=Provider(records))


def snapshot(engine):
    with engine.connect() as connection:
        return {table.name: [tuple(row) for row in connection.execute(select(table))] for table in TABLES}


def preview(engine, records, **kwargs):
    return preview_torqueai_history(engine, date_from=DAY, date_to=DAY,
                                   connector=Provider(records), **kwargs)


def test_classification_and_all_database_state_unchanged(database):
    seed(database, [dispatch(1), dispatch(2), dispatch(3)])
    before = snapshot(database)
    statements = []

    def inspect_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
        assert statement.lstrip().upper().startswith("SELECT ")

    event.listen(database, "before_cursor_execute", inspect_sql)
    try:
        result = preview(database, [dispatch(1), dispatch(2, customerName="Changed"),
                                    dispatch(3, stops=None), dispatch(4)])
    finally:
        event.remove(database, "before_cursor_execute", inspect_sql)
    assert result["status"] == "success"
    assert (result["would_insert"], result["would_update"], result["unchanged"]) == (1, 2, 1)
    assert result["missing_usable_lane_stops"] == 1
    assert snapshot(database) == before  # Includes fingerprints, stops, checkpoint and run claims.
    assert all("sync_state" not in statement and "sync_runs" not in statement for statement in statements)


def test_composite_identity_is_tenant_scoped(database):
    seed(database, [dispatch(1, "B")], tenant="other")
    result = preview(database, [dispatch(1, "A")])
    assert result["would_insert"] == 1
    assert result["identity_conflicts"] == 0


def test_same_load_different_orders_never_merge(database):
    seed(database, [dispatch(4882, "131592017")])
    result = preview(database, [dispatch(4882, "131592017"), dispatch(4882, "VOID - 131592017"),
                                dispatch(10, "ONE"), dispatch(10, "TWO")])
    assert result["identity_conflicts"] == 4
    assert result["would_insert"] == result["would_update"] == result["unchanged"] == 0
    assert result["identities"][0]["exact_identity_present"] is True
    assert result["identities"][1]["exact_identity_present"] is False
    assert len(result["identities"]) == 4


@pytest.mark.parametrize("scope", ["other", "", "MOR-LOGISTICS"])
def test_wrong_configured_tenant_denied_before_provider(database, monkeypatch, scope):
    monkeypatch.setenv("POLARIS_TORQUEAI_ORGANIZATION_SLUG", scope)
    provider = Provider([dispatch()])
    result = preview_torqueai_history(database, date_from=DAY, date_to=DAY, connector=provider)
    assert result["validation_failures"] == [{"code": "organization_scope_mismatch"}]
    assert provider.calls == []


def test_inactive_tenant_and_wrong_provider_are_denied(database):
    provider = Provider([dispatch()])
    provider.organization_slug = "other"
    assert preview_torqueai_history(database, date_from=DAY, date_to=DAY, connector=provider)["status"] == "failed"
    assert not provider.calls
    with database.begin() as connection:
        connection.execute(Organization.__table__.update().where(Organization.id == "mor").values(status="suspended"))
    assert preview(database, [dispatch()])["validation_failures"] == [{"code": "organization_scope_mismatch"}]


@pytest.mark.parametrize("end", [date(2025, 6, 8), date(2025, 5, 31), "not-a-date"])
def test_invalid_window_never_calls_provider(database, end):
    provider = Provider([])
    result = preview_torqueai_history(database, date_from=DAY, date_to=end, connector=provider)
    assert result["status"] == "failed"
    assert not provider.calls


def test_seven_days_and_date_semantics_evidence(database):
    provider = Provider([dispatch(1, shipDate="2025-05-01"), dispatch(2, shipDate="2025-06-10"),
                         dispatch(3, shipDate=None), dispatch(4, shipDate="invalid"), dispatch(5)])
    result = preview_torqueai_history(database, date_from=DAY, date_to=date(2025, 6, 7), connector=provider)
    assert result["status"] == "success"
    assert result["returned_ship_dates"] == {"minimum": "2025-05-01", "maximum": "2025-06-10",
                                             "outside_requested_window": 2, "missing_or_invalid": 2}
    assert result["validated_records"] == 5  # Out-of-window dates are evidence, not discarded rows.


def test_pagination_keeps_exact_limits(database):
    provider = Provider([dispatch(i, str(i)) for i in range(1000)])
    result = preview_torqueai_history(database, date_from=DAY, date_to=DAY, connector=provider)
    assert result["status"] == "success"
    assert result["would_insert"] == result["validated_records"] == 1000
    assert len(provider.calls) == 10
    assert {call[3] for call in provider.calls} == {100}


@pytest.mark.parametrize("provider,code", [
    (Provider([], total=1001), "ingestion_bound_exceeded"),
    (Provider([], total=11, size=1), "ingestion_bound_exceeded"),
    (Provider([dispatch(i, str(i)) for i in range(101)], changed_total=True), "provider_contract_error"),
    (Provider([dispatch()], total=2), "provider_contract_error"),
    (Provider([dispatch(), dispatch()]), "provider_duplicate_identity"),
    (Provider([dispatch(order=" A ")]), "identity_not_exact"),
    (Provider([dispatch(load=True)]), "provider_contract_error"),
    (Provider([dispatch(stops={})]), "provider_contract_error"),
])
def test_failures_are_sanitized_and_never_persist(database, provider, code):
    before = snapshot(database)
    result = preview_torqueai_history(database, date_from=DAY, date_to=DAY, connector=provider)
    assert result["status"] == "failed"
    assert result["validation_failures"] == [{"code": code}]
    assert result["identities"] == []
    assert snapshot(database) == before


@pytest.mark.parametrize("stops", [None, [], [{"job": "Pickup", "city": "Winnipeg", "province": "MB", "country": "CAN"}],
                                       [{"job": "Pick Up", "city": "", "province": "MB", "country": "CAN"}]])
def test_missing_lane_stops_do_not_infer_aliases(database, stops):
    assert preview(database, [dispatch(stops=stops)])["missing_usable_lane_stops"] == 1


@pytest.mark.parametrize("statement", [
    text("UPDATE torqueai_dispatches SET customer_name='bad'"),
    TorqueAIDispatch.__table__.insert().values(organization_id="mor"),
    text("WITH x AS (SELECT 1) DELETE FROM torqueai_dispatches"),
])
def test_database_guard_rejects_writes(database, statement):
    before = snapshot(database)
    with pytest.raises(TorqueAIDispatchIngestionError, match="SELECT queries only"):
        with _select_only_connection(database) as connection:
            connection.execute(statement)
    assert snapshot(database) == before


def test_existing_get_connector_authentication_and_payload_minimization(database, monkeypatch):
    monkeypatch.setenv("POLARIS_TORQUEAI_BASE_URL", "https://synthetic.example.test")
    monkeypatch.setenv("POLARIS_TORQUEAI_API_TOKEN", "synthetic-secret")
    calls = []

    def handle(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer synthetic-secret"
        assert dict(request.url.params) == {"from": DAY.isoformat(), "to": DAY.isoformat(), "page": "1", "limit": "100"}
        return httpx.Response(200, json={"data": [dispatch()], "totalCount": 1, "page": 1,
                                        "itemsPerPage": 100, "dateRange": {"from": DAY.isoformat(), "to": DAY.isoformat()}})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = TorqueAIConnector(organization_slug="mor-logistics", http_client=client)
        result = preview_torqueai_history(database, date_from=DAY, date_to=DAY, connector=provider)
    assert result["status"] == "success"
    assert len(calls) == 1
    assert "synthetic-secret" not in json.dumps(result)
    assert "customerName" not in json.dumps(result)


def test_scheduled_claim_row_is_untouched(database):
    seed(database, [dispatch()])
    with database.begin() as connection:
        connection.execute(TorqueAIDispatchSyncRun.__table__.insert().values(
            run_id="scheduled-claim", organization_id="mor", requested_from=DAY, requested_to=DAY,
            page_size=100, status="claimed", trigger_mode="scheduled", trigger_slot="synthetic-slot",
            started_at=datetime.now(timezone.utc)))
    before = snapshot(database)
    assert preview(database, [dispatch(2)])["status"] == "success"
    assert snapshot(database) == before


def test_empty_provider_window_is_successful_without_database_changes(database):
    before = snapshot(database)
    result = preview(database, [])
    assert result["status"] == "success"
    assert result["provider_records_received"] == result["validated_records"] == 0
    assert result["identities"] == []
    assert result["pagination"]["pages_fetched"] == 1
    assert snapshot(database) == before


def test_provider_authorization_failure_does_not_record_failed_run(database, monkeypatch):
    monkeypatch.setenv("POLARIS_TORQUEAI_BASE_URL", "https://synthetic.example.test")
    monkeypatch.setenv("POLARIS_TORQUEAI_API_TOKEN", "synthetic-secret")
    before = snapshot(database)
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401))) as client:
        result = preview_torqueai_history(database, date_from=DAY, date_to=DAY,
            connector=TorqueAIConnector(organization_slug="mor-logistics", http_client=client))
    assert result["status"] == "failed"
    assert result["validation_failures"] == [{"code": "authorization_required"}]
    assert snapshot(database) == before


def test_tenant_suspended_during_provider_request_is_rechecked(database):
    class SuspendProvider(Provider):
        def fetch_dispatches(self, **kwargs):
            with database.begin() as connection:
                connection.execute(Organization.__table__.update().where(Organization.id == "mor").values(status="suspended"))
            return super().fetch_dispatches(**kwargs)

    result = preview_torqueai_history(database, date_from=DAY, date_to=DAY, connector=SuspendProvider([dispatch()]))
    assert result["validation_failures"] == [{"code": "organization_scope_mismatch"}]
    assert result["identities"] == []


def test_postgresql_boundary_sets_readonly_before_queries_and_rolls_back(monkeypatch):
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.dialect.name = "postgresql"
    transaction = connection.begin.return_value.__enter__.return_value
    listeners = []
    monkeypatch.setattr(event, "listen", lambda *args: listeners.append(args))
    removed = []
    monkeypatch.setattr(event, "remove", lambda *args: removed.append(args))
    with _select_only_connection(engine) as selected:
        assert selected is connection
        assert str(connection.execute.call_args.args[0]) == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
        assert listeners[0][:2] == (connection, "before_cursor_execute")
    transaction.rollback.assert_called_once()
    transaction.commit.assert_not_called()
    assert removed == listeners
