"""Synthetic review evidence only: no provider or production access."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import MetaData, select, update, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql

from app.connectors.torqueai_backfill_control import ControlError, _ledger_connection
from app.connectors.torqueai_update_evidence import (
    FIELDS, EvidenceError, current_matches_before, digest, validate_record, validate_review,
)
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchOperational
from app.models.torqueai_backfill import UPDATE_EVIDENCE, ATTEMPT, IDENTITY
from test_torqueai_backfill_control import database, plan, preview, rows
from test_torqueai_history_preview import dispatch, seed, snapshot
from test_torqueai_history_certification import enabled, client, request


def capture(database):
    seed(database, [dispatch(1), dispatch(2), dispatch(3, 'OLD')])
    service, _, window = plan(database)
    before = snapshot(database)
    result = preview(service, window, [dispatch(1, status='cancelled'), dispatch(2), dispatch(3, 'NEW'), dispatch(4)])
    assert snapshot(database) == before
    return service, result, rows(database, UPDATE_EVIDENCE)[0]


def test_capture_diff_links_and_immutable_retry(database):
    service, result, row = capture(database)
    assert (result['would_update'], result['unchanged'], result['identity_conflicts'], result['would_insert']) == (1, 1, 1, 1)
    assert len(rows(database, UPDATE_EVIDENCE)) == 1
    review = row['evidence']['review']
    assert review['changed_fields'] == ['status']
    assert review['before_image']['status'] is None and review['proposed_image']['status'] == 'cancelled'
    assert set(review['before_image']) == set(FIELDS)
    assert review['before_hash'] == digest(review['before_image'])
    assert review['proposed_hash'] == digest(review['proposed_image'])
    validate_record(row)
    summary = service.update_evidence_summary(row['attempt_id'])
    assert summary == {'update_evidence_count': 1, 'update_evidence_integrity_valid': True,
                       'changed_field_count_total': 1, 'rollback_preconditions_recorded': True}
    from test_torqueai_history_preview import Provider
    provider = Provider([])
    service.preview(row['window_id'], request_key='preview', operator='operator', code_sha='a'*40, connector=provider)
    assert provider.calls == [] and rows(database, UPDATE_EVIDENCE) == [row]


@pytest.mark.parametrize('field', ['before_image', 'proposed_image', 'changed_fields', 'before_hash',
                                  'proposed_hash', 'current_source_fingerprint', 'dispatch_id', 'organization_id'])
def test_tampering_rejected(database, field):
    _, _, row = capture(database)
    altered = deepcopy(row)
    review = altered['evidence']['review']
    if field.endswith('_image'):
        review[field]['status'] = 'tampered'
    elif field == 'changed_fields':
        review[field] = []
    elif field == 'dispatch_id':
        review[field] += 1
    else:
        review[field] = 'tampered'
    with pytest.raises(EvidenceError):
        validate_record(altered)


def test_order_invariance_and_extra_fields_rejected(database):
    _, _, row = capture(database)
    payload = row['evidence']
    assert digest(payload) == digest(dict(reversed(list(payload.items()))))
    for prohibited in ('billing_total', 'total_charge', 'address', 'raw_payload', 'secret'):
        review = deepcopy(payload['review'])
        review['proposed_image'][prohibited] = 'DO_NOT_RETAIN'
        with pytest.raises(EvidenceError):
            validate_review(review)


def test_precondition_refuses_later_changes_and_load_only(database):
    _, _, row = capture(database)
    with database.connect() as connection:
        current = dict(connection.execute(select(TorqueAIDispatch.__table__).where(
            TorqueAIDispatch.id == row['dispatch_id'])).mappings().one())
        current['operational_fingerprint'] = connection.execute(select(TorqueAIDispatchOperational.source_fingerprint).where(
            TorqueAIDispatchOperational.dispatch_id == row['dispatch_id'])).scalar_one()
    assert current_matches_before(row, current)
    for key, value in [('status', 'later'), ('id', 999), ('organization_id', 'other'),
                       ('provider_order_number', 'NEW'), ('operational_fingerprint', 'b'*64)]:
        changed = dict(current, **{key: value})
        assert not current_matches_before(row, changed)


def test_insert_only_and_stored_tamper_detected(database):
    service, _, row = capture(database)
    with pytest.raises(ControlError), _ledger_connection(database) as connection:
        connection.execute(update(UPDATE_EVIDENCE).values(evidence_fingerprint='b'*64))
    # Deliberate synthetic DBA corruption is detected, never silently certified.
    with database.begin() as connection:
        connection.execute(update(UPDATE_EVIDENCE).values(evidence_fingerprint='b'*64))
    assert service.update_evidence_summary(row['attempt_id'])['update_evidence_integrity_valid'] is False


def test_operational_only_change_is_hash_only(database):
    seed(database, [dispatch(1)])
    service, _, window = plan(database)
    before = snapshot(database)
    preview(service, window, [dispatch(1, stops=None, arbitraryDeferred='DO_NOT_RETAIN')])
    row = rows(database, UPDATE_EVIDENCE)[0]
    review = row['evidence']['review']
    assert review['changed_fields'] == []
    assert review['current_operational_fingerprint'] != review['proposed_operational_fingerprint']
    assert 'DO_NOT_RETAIN' not in str(row)
    assert snapshot(database) == before


def test_signed_certification_aggregates_no_business_values(enabled, database):
    client, provider = enabled
    seed(database, [dispatch()])
    before = snapshot(database)
    provider.records = [dispatch(customerName='PRIVATE_REVIEW_VALUE')]
    response = request(client)
    assert response.status_code == 200
    body = response.json()
    assert body['update_evidence_count'] == 1
    assert body['changed_field_count_total'] == 1
    assert body['update_evidence_integrity_valid'] is True
    assert body['rollback_preconditions_recorded'] is True
    assert 'PRIVATE_REVIEW_VALUE' not in response.text and 'before_image' not in response.text
    assert snapshot(database) == before


def test_frozen_update_migration_matches_runtime():
    path = Path(__file__).resolve().parents[1] / 'migrations/versions/202610110001_torqueai_update_evidence.py'
    spec = importlib.util.spec_from_file_location('update_migration', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    metadata = MetaData()
    from app.models.torqueai_backfill import define_tables
    # Register FK targets including organizations for PostgreSQL compilation.
    from sqlalchemy import Table, Column, String
    Table('organizations', metadata, Column('id', String, primary_key=True))
    define_tables(metadata)
    frozen = module.define_update_table(metadata)
    assert list(frozen.columns.keys()) == list(UPDATE_EVIDENCE.columns.keys())
    assert str(CreateTable(frozen).compile(dialect=postgresql.dialect()))
    with pytest.raises(RuntimeError):
        module.downgrade()


def test_twenty_seven_exact_updates_no_conflict_evidence(database):
    records = [dispatch(i) for i in range(1, 28)] + [dispatch(100, 'OLD')]
    seed(database, records)
    service, _, window = plan(database)
    before = snapshot(database)
    preview(service, window, [dispatch(i, status='cancelled') for i in range(1, 28)] + [dispatch(100, 'VOID - OLD')])
    updates = rows(database, UPDATE_EVIDENCE)
    assert len(updates) == len({r['dispatch_id'] for r in updates}) == 27
    assert all(r['provider_load_number'] != '100' for r in updates)
    assert service.update_evidence_summary(updates[0]['attempt_id'])['update_evidence_integrity_valid'] is True
    assert snapshot(database) == before


def test_database_uniqueness_and_tenant_parent_linkage(database):
    _, _, row = capture(database)
    duplicate = dict(row, id='duplicate')
    with pytest.raises(IntegrityError), database.begin() as connection:
        connection.execute(insert(UPDATE_EVIDENCE).values(**duplicate))
    cross_tenant = dict(row, id='cross-tenant', organization_id='other')
    with pytest.raises(IntegrityError), database.begin() as connection:
        connection.execute(insert(UPDATE_EVIDENCE).values(**cross_tenant))
    from app.connectors.torqueai_backfill_control import BackfillControl
    with pytest.raises(ControlError):
        BackfillControl(database, organization_id='other').update_evidence_summary(row['attempt_id'])


def test_legacy_completed_attempt_preserved(database):
    from app.connectors.torqueai_backfill_control import fingerprint
    from app.connectors.torqueai_history_preview import preview_torqueai_history
    from test_torqueai_history_preview import Provider, DAY
    seed(database, [dispatch(1, 'OLD')])
    service, _, window = plan(database)
    attempt = service.begin_preview(window, request_key='legacy', operator='operator', code_sha='a'*40)
    report = preview_torqueai_history(database, date_from=DAY, date_to=DAY, connector=Provider([dispatch(1, 'VOID - OLD')]))
    service.finish_preview(window, attempt, report)
    before_attempt, before_identity = rows(database, ATTEMPT), rows(database, IDENTITY)
    assert 'update_review_fingerprints' not in before_attempt[0]['evidence']
    assert rows(database, UPDATE_EVIDENCE) == []
    assert service.update_evidence_summary(attempt)['update_evidence_integrity_valid'] is False
    assert rows(database, ATTEMPT) == before_attempt and rows(database, IDENTITY) == before_identity
