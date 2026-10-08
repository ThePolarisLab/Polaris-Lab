"""Synthetic signed bridge tests: no production/provider credentials or traffic."""
import json
from pathlib import Path
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import insert, select, text, update

from app.api import internal_torqueai_history as route
from app.connectors import torqueai_history_certification as certification
from app.connectors import torqueai_history_preview as preview_module
from app.connectors.torqueai_backfill_control import BackfillControl, ControlError
from app.models.torqueai import (TorqueAIDispatch, TorqueAIDispatchOperational,
                                TorqueAIDispatchStop, TorqueAIDispatchSyncState,
                                TorqueAIDispatchSyncRun)
from app.models.torqueai_backfill import MANIFEST, WINDOW, ATTEMPT, IDENTITY
from app.security.job_auth import sign_job_request
from test_torqueai_backfill_control import database, rows
from test_torqueai_history_preview import Provider, dispatch, seed, snapshot, DAY

PATH = '/api/v1/internal/torqueai/historical-preview-certification'
SECRET = 'synthetic-machine-secret-not-production'
SHA = 'a' * 40


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    monkeypatch.setenv('POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET', SECRET)
    monkeypatch.delenv(route.FEATURE_FLAG, raising=False)
    return TestClient(app)


def request(client, *, payload=None, body=None, timestamp=None, signature='valid', query=''):
    body = body if body is not None else json.dumps(payload or {
        'date_from': DAY.isoformat(), 'date_to': DAY.isoformat()}).encode()
    timestamp = str(int(time.time())) if timestamp is None else timestamp
    headers = {'Content-Type': 'application/json'}
    if timestamp is not False:
        headers['X-Polaris-Job-Timestamp'] = timestamp
    if signature == 'valid':
        signature = sign_job_request(method='POST', path=PATH, body=body,
                                     timestamp=timestamp, secret=SECRET)
    if signature is not None:
        headers['X-Polaris-Job-Signature'] = signature
    return client.post(PATH + query, content=body, headers=headers)


@pytest.fixture
def enabled(client, database, monkeypatch):
    monkeypatch.setenv(route.FEATURE_FLAG, 'true')
    monkeypatch.setenv('RENDER_GIT_COMMIT', SHA)
    monkeypatch.setenv('POLARIS_TORQUEAI_API_TOKEN', 'synthetic-provider-token')
    monkeypatch.setenv('POLARIS_TORQUEAI_BASE_URL', 'https://synthetic.example')
    monkeypatch.setattr(certification, 'application_engine', database)
    provider = Provider([dispatch()])
    monkeypatch.setattr(preview_module, 'TorqueAIConnector', lambda **kwargs: provider)
    return client, provider


@pytest.mark.parametrize('signature', [None, '', 'bad', 'z' * 64, '0' * 64, 'a' * 65])
def test_bad_auth_no_work(client, database, monkeypatch, signature, caplog):
    monkeypatch.setattr(route, 'certify_history', lambda **kw: pytest.fail('work before authentication'))
    before = snapshot(database)
    response = request(client, signature=signature)
    assert response.status_code == 401
    assert snapshot(database) == before
    assert rows(database, MANIFEST) == []
    assert SECRET not in response.text + caplog.text
    assert 'synthetic-provider-token' not in response.text + caplog.text


@pytest.mark.parametrize('offset', [-301, 301])
def test_stale_future_auth(client, monkeypatch, offset):
    monkeypatch.setattr('app.security.job_auth.time.time', lambda: 1000)
    monkeypatch.setattr(route, 'certify_history', lambda **kw: pytest.fail('unexpected work'))
    assert request(client, timestamp=str(1000 + offset)).status_code == 401


@pytest.mark.parametrize('timestamp', ['not-a-time', '', False])
def test_malformed_timestamp(client, timestamp):
    assert request(client, timestamp=timestamp, signature='0' * 64).status_code == 401


def test_missing_secret(client, monkeypatch):
    monkeypatch.delenv('POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET')
    assert request(client).status_code == 401


@pytest.mark.parametrize('flag', [None, '', 'false', '1', 'yes'])
def test_disabled_no_work(client, database, monkeypatch, flag):
    if flag is not None:
        monkeypatch.setenv(route.FEATURE_FLAG, flag)
    monkeypatch.setattr(route, 'certify_history', lambda **kw: pytest.fail('disabled work'))
    before = snapshot(database)
    response = request(client)
    assert response.status_code == 503
    assert response.json()['detail']['status'] == 'disabled'
    assert snapshot(database) == before
    for table in (MANIFEST, WINDOW, ATTEMPT, IDENTITY):
        assert rows(database, table) == []


@pytest.mark.parametrize('payload', [
    {'date_from': '2026-09-01', 'date_to': '2026-09-08'},
    {'date_from': '2026-09-02', 'date_to': '2026-09-01'},
    {'date_from': '20260901', 'date_to': '2026-09-01'},
    {'date_from': '2026-02-30', 'date_to': '2026-03-01'},
    {'date_from': 20260901, 'date_to': '2026-09-01'}, {}, [],
    *[{'date_from': '2026-09-01', 'date_to': '2026-09-01', key: 'DO_NOT_ECHO'} for key in (
        'organization_id', 'tenant', 'provider_token', 'provider_url', 'database',
        'page', 'execution_mode', 'approve', 'write', 'retry', 'rollback', 'code_sha')],
])
def test_invalid_request_no_work(client, monkeypatch, payload):
    monkeypatch.setenv(route.FEATURE_FLAG, 'true')
    monkeypatch.setattr(route, 'certify_history', lambda **kw: pytest.fail('invalid request work'))
    response = request(client, body=json.dumps(payload).encode())
    assert response.status_code == 400
    assert 'DO_NOT_ECHO' not in response.text


@pytest.mark.parametrize('body,query', [(b'not json', ''), (b'x' * 257, ''),
    (b'{"date_from":"2026-09-01","date_from":"2026-09-02","date_to":"2026-09-07"}', ''),
    (None, '?tenant=other')])
def test_body_and_query_rejected(client, monkeypatch, body, query):
    monkeypatch.setenv(route.FEATURE_FLAG, 'true')
    assert request(client, body=body, query=query).status_code == 400


@pytest.mark.parametrize('env,value', [('RENDER_GIT_COMMIT', ''), ('RENDER_GIT_COMMIT', 'short'),
    ('POLARIS_TORQUEAI_API_TOKEN', ''), ('POLARIS_TORQUEAI_BASE_URL', 'http://bad.example'),
    ('POLARIS_TORQUEAI_ORGANIZATION_SLUG', 'other')])
def test_config_fail_closed(enabled, database, monkeypatch, env, value):
    client, provider = enabled
    monkeypatch.setenv(env, value)
    before = snapshot(database)
    assert request(client).status_code == 503
    assert provider.calls == []
    assert rows(database, MANIFEST) == []
    assert snapshot(database) == before


def test_inactive_mor_no_provider_or_ledger(enabled, database):
    from app.organizations.models import Organization
    client, provider = enabled
    with database.begin() as conn:
        conn.execute(Organization.__table__.update().where(Organization.id == 'mor').values(status='inactive'))
    assert request(client).status_code == 503
    assert provider.calls == []
    assert rows(database, MANIFEST) == []


def test_one_real_control_preview_no_operational_changes(enabled, database, monkeypatch, caplog):
    client, provider = enabled
    seed(database, [dispatch(1), dispatch(2)])
    provider.records = [dispatch(1), dispatch(2, customerName='SECRET_CUSTOMER_VALUE'), dispatch(3)]
    provider.total = 3
    before = snapshot(database)
    calls = []
    original = BackfillControl.preview
    def tracked(self, *args, **kwargs):
        calls.append(kwargs)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(BackfillControl, 'preview', tracked)
    monkeypatch.setattr(BackfillControl, 'approve', lambda *a, **kw: pytest.fail('approval'))
    monkeypatch.setattr(BackfillControl, 'record_images', lambda *a, **kw: pytest.fail('images'))
    response = request(client)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['status'] == payload['window_status'] == payload['attempt_status'] == 'previewed'
    assert (payload['would_insert'], payload['would_update'], payload['unchanged']) == (1, 1, 1)
    assert payload['safety_verified'] is True
    assert all(payload[k] is False for k in certification.FLAGS)
    assert payload['before']['normal'] == payload['after']['normal']
    assert snapshot(database) == before
    assert payload['control_row_deltas'] == {MANIFEST.name: 1, WINDOW.name: 1, ATTEMPT.name: 1, IDENTITY.name: 3}
    assert len(calls) == len(provider.calls) == 1
    assert len(rows(database, MANIFEST)) == len(rows(database, WINDOW)) == len(rows(database, ATTEMPT)) == 1
    assert rows(database, MANIFEST)[0]['code_sha'] == SHA
    assert rows(database, MANIFEST)[0]['execution_mode'] == 'preview_only'
    assert rows(database, WINDOW)[0]['active_attempt_id'] is None
    assert rows(database, WINDOW)[0]['lease_until'] is None
    assert rows(database, WINDOW)[0]['approved_at'] is None
    assert rows(database, ATTEMPT)[0]['claim_namespace'] == 'torqueai_historical_preview'
    for secret in (SECRET, 'synthetic-provider-token', 'SECRET_CUSTOMER_VALUE', 'provider_load_number', 'provider_order_number'):
        assert secret not in response.text + caplog.text
    assert request(client).status_code == 409  # Signed replay cannot refetch.
    assert len(provider.calls) == 1


def test_seven_inclusive_days_and_overlap(enabled, database):
    client, provider = enabled
    payload = {'date_from': '2026-08-25', 'date_to': '2026-08-31'}
    assert request(client, payload=payload).status_code == 200
    response = request(client, payload={'date_from': '2026-08-31', 'date_to': '2026-09-01'})
    assert response.status_code == 409
    assert len(provider.calls) == 1
    assert len(rows(database, MANIFEST)) == 1


def test_conflicts_quarantined_not_merged(enabled, database):
    client, provider = enabled
    seed(database, [dispatch(4882, 'OLD')])
    provider.records, provider.total = [dispatch(4882, 'NEW')], 1
    response = request(client)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['status'] == payload['attempt_status'] == 'blocked'
    assert payload['identity_conflicts'] == payload['quarantined'] == 1
    assert rows(database, IDENTITY)[0]['quarantined'] == 1
    assert 'OLD' not in response.text and 'NEW' not in response.text
    assert request(client).status_code == 409
    assert len(provider.calls) == 1


def test_failed_preview_retained_no_retry(enabled, database):
    client, provider = enabled
    provider.records, provider.total = [{'loadNumber': 'malformed'}], 1
    response = request(client)
    assert response.status_code == 502, response.text
    assert response.json()['detail']['window_status'] == 'failed'
    assert rows(database, ATTEMPT)[0]['status'] == 'failed'
    assert len(provider.calls) == 1
    assert request(client).status_code == 409


@pytest.mark.parametrize('statement', [
    lambda: insert(TorqueAIDispatch.__table__).values(organization_id='mor'),
    lambda: update(TorqueAIDispatchOperational.__table__).values(source_fingerprint='bad'),
    lambda: update(TorqueAIDispatchStop.__table__).values(source_fingerprint='bad'),
    lambda: update(TorqueAIDispatchSyncState.__table__).values(last_successful_run_id='bad'),
    lambda: update(TorqueAIDispatchSyncRun.__table__).values(status='bad'),
    lambda: select(1).add_cte(update(TorqueAIDispatch.__table__).values(customer_name='bad').cte()),
    lambda: text('DELETE FROM torqueai_backfill_manifests'),
    lambda: text('UPDATE torqueai_dispatch_sync_state SET last_successful_run_id=\'bad\''),
    lambda: text('SELECT 1'),  # Arbitrary text is not a SQLAlchemy Select.
])
def test_engine_boundary_blocks_nonledger_sql(enabled, statement):
    with certification._isolated_engine() as engine, engine.begin() as connection:
        with pytest.raises(ControlError):
            connection.execute(statement())


def test_concurrent_normal_activity_inconclusive_not_attributed(enabled, monkeypatch):
    client, provider = enabled
    original = certification._snapshot
    calls = 0
    def changed(engine, org):
        nonlocal calls
        result = original(engine, org)
        calls += 1
        if calls == 2:
            result['normal']['torqueai_dispatch_sync_runs']['fingerprint'] = 'other-sync'
            result['normal']['torqueai_dispatches']['fingerprint'] = 'other-writer'
        return result
    monkeypatch.setattr(certification, '_snapshot', changed)
    response = request(client)
    assert response.status_code == 409
    payload = response.json()['detail']
    assert payload['status'] == 'inconclusive'
    assert payload['normal_sync_activity_observed'] is True
    assert payload['observed_normal_state_change'] is True
    assert payload['safety_verified'] is False
    assert payload['database_writes'] is False  # Preview boundary, not other writers.
    assert len(provider.calls) == 1


def test_manual_workflow_contract():
    import textwrap
    root = Path(__file__).resolve().parents[3]
    path = root / '.github/workflows/torqueai-historical-preview-certification.yml'
    source = path.read_text()
    assert '\non:\n  workflow_dispatch:\n    inputs:\n' in source
    assert '\n      date_from:\n' in source and '\n      date_to:\n' in source
    assert '\n    timeout-minutes: 10\n' in source
    assert 'POLARIS_PRODUCTION_API_URL' in source
    assert 'POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET' in source
    assert PATH in source
    for forbidden in ('POLARIS_TORQUEAI_API_TOKEN', 'POLARIS_TORQUEAI_BASE_URL',
                      'POLARIS_TORQUEAI_ORGANIZATION_SLUG', 'DATABASE_URL', 'schedule:'):
        assert forbidden not in source
    script = textwrap.dedent(source.split("          python - <<'PY'\n")[1].rsplit('\n          PY', 1)[0])
    compile(script, 'workflow-python', 'exec')
    assert 'NoRedirect' in script and 'timeout=480' in script
    assert 'print(json.dumps' in script
    assert 'payload.get(k) is not False' in script


@pytest.mark.parametrize('violation', [None, *certification.FLAGS, 'status', 'count',
                                     'request', 'safety_verified', 'http_error', 'network_error'])
def test_workflow_executes_once_and_fails_closed(monkeypatch, capsys, violation):
    import io
    import textwrap
    import urllib.error
    import urllib.request
    root = Path(__file__).resolve().parents[3]
    source = (root / '.github/workflows/torqueai-historical-preview-certification.yml').read_text()
    script = textwrap.dedent(source.split("          python - <<'PY'\n")[1].rsplit('\n          PY', 1)[0])
    monkeypatch.setenv('POLARIS_PRODUCTION_API_URL', 'https://synthetic-polaris.example')
    monkeypatch.setenv('POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET', SECRET)
    monkeypatch.setenv('DATE_FROM', '2026-08-25')
    monkeypatch.setenv('DATE_TO', '2026-08-31')
    payload = {'status': 'previewed', 'window_status': 'previewed', 'attempt_status': 'previewed',
               'provider': 'torqueai', 'operation': 'historical_preview_certification',
               'request': {'from': '2026-08-25', 'to': '2026-08-31'},
               'window_semantics': 'dispatch_order_date', 'safety_verified': True,
               'observed_normal_state_change': False, 'provider_records_received': 1,
               'validated_records': 1, 'would_insert': 1, 'would_update': 0, 'unchanged': 0,
               'identity_conflicts': 0, 'quarantined': 0, 'missing_usable_lane_stops': 0,
               'pages_fetched': 1, 'provider_total_count': 1, 'page_size': 100,
               'raw_extra': 'DO_NOT_PRINT', **{k: False for k in certification.FLAGS}}
    if violation in certification.FLAGS:
        payload[violation] = True
    elif violation == 'status':
        payload['status'] = 'DO_NOT_PRINT'
    elif violation == 'count':
        payload['would_insert'] = 'DO_NOT_PRINT'
    elif violation == 'request':
        payload['request'] = {'secret': 'DO_NOT_PRINT'}
    elif violation == 'safety_verified':
        payload['safety_verified'] = False
    requests = []
    class Response(io.BytesIO):
        status = 200
    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            assert timeout == 480
            assert request.full_url == 'https://synthetic-polaris.example' + PATH
            assert request.method == 'POST'
            assert json.loads(request.data) == {'date_from': '2026-08-25', 'date_to': '2026-08-31'}
            signed = request.get_header('X-polaris-job-signature')
            timestamp = request.get_header('X-polaris-job-timestamp')
            assert signed == sign_job_request(method='POST', path=PATH, body=request.data,
                                             timestamp=timestamp, secret=SECRET)
            if violation == 'http_error':
                raise urllib.error.HTTPError(request.full_url, 403, 'DO_NOT_PRINT', {}, None)
            if violation == 'network_error':
                raise urllib.error.URLError('DO_NOT_PRINT')
            return Response(json.dumps(payload).encode())
    monkeypatch.setattr(urllib.request, 'build_opener', lambda handler: Opener())
    if violation is None:
        exec(compile(script, 'workflow', 'exec'), {})
        output = json.loads(capsys.readouterr().out)
        assert output['status'] == 'previewed'
        assert output['would_insert'] == 1
    else:
        with pytest.raises(SystemExit):
            exec(compile(script, 'workflow', 'exec'), {})
    assert len(requests) == 1
    output = capsys.readouterr().out
    assert 'DO_NOT_PRINT' not in output and SECRET not in output
