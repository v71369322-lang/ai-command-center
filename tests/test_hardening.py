from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
import jwt
import pytest
from sqlalchemy import text

from command_center.api import create_app
from command_center.backup_jobs import BackupJobs, LocalRepository
from command_center.broker_client import BrokerClient
from command_center.runtime_broker import RuntimeBroker, create_broker_app
from command_center.runtime_ledger import RuntimeLedger
from command_center.runtime_policy import RuntimeBackend, RuntimeLimits
from command_center.store import Denied, Store
from command_center.watchdog import Watchdog
from command_center.worker import Runner
from command_center.worker import docker
from test_control_plane import create
from conftest import wait_ready


@pytest.fixture
def oidc(settings, tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public['kid'] = 'synthetic-idp'
    path = tmp_path / 'public-jwks.json'
    path.write_text(json.dumps({'keys': [public]}))
    configured = replace(settings, auth_mode='oidc', oidc_issuer='https://idp.invalid',
                         oidc_audience='f1-owner', oidc_owner='synthetic-owner',
                         oidc_jwks_file=str(path), web_origin='https://testserver')
    def assertion(**changes):
        now = int(time.time())
        claims = {'iss': configured.oidc_issuer, 'aud': configured.oidc_audience,
                  'sub': configured.oidc_owner, 'jti': str(uuid4()), 'iat': now, 'nbf': now,
                  'exp': now + 600, 'auth_time': now, 'amr': ['pwd', 'mfa'], **changes}
        return jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'synthetic-idp'})
    return configured, assertion


def test_owner_session_csrf_revocation_and_no_bearer_bypass(store, oidc, headers):
    configured, assertion = oidc
    with TestClient(create_app(configured), base_url='https://testserver') as client:
        assert client.post('/api/control/stop', headers=headers['owner']).status_code == 401
        credential = assertion()
        response = client.post('/api/auth/exchange', json={'assertion': credential})
        assert response.status_code == 200
        cookie = response.headers['set-cookie'].lower()
        assert 'secure' in cookie and 'httponly' in cookie and 'samesite=strict' in cookie
        csrf = response.json()['csrf_token']
        assert client.post('/api/auth/exchange', json={'assertion': credential}).status_code == 401
        assert client.get('/api/state').status_code == 200
        csrf = client.get('/api/auth/csrf').json()['csrf_token']
        assert client.post('/api/control/stop').status_code == 403
        assert client.post('/api/control/stop', headers={'X-CSRF-Token': csrf, 'Origin': 'https://attacker.invalid'}).status_code == 403
        assert client.post('/api/control/stop', headers={'X-CSRF-Token': csrf}).status_code == 200
        assert client.post('/api/auth/revoke-all', headers={'X-CSRF-Token': csrf}).status_code == 200
        assert client.get('/api/state').status_code == 401


@pytest.mark.parametrize('changes', [{'amr': ['pwd']}, {'sub': 'intruder'}, {'aud': 'other'},
                                    {'auth_time': 1}, {'exp': 1}, {'nbf': 9999999999}])
def test_owner_idp_negative_assertions(store, oidc, changes):
    configured, assertion = oidc
    with TestClient(create_app(configured), base_url='https://testserver') as client:
        response = client.post('/api/auth/exchange', json={'assertion': assertion(**changes)})
        assert response.status_code == 401
        assert client.get('/api/state').status_code == 401


def test_owner_idp_missing_is_fail_closed(store, settings):
    with TestClient(create_app(replace(settings, auth_mode='oidc')), base_url='https://testserver') as client:
        assert client.post('/api/auth/exchange', json={'assertion': 'x' * 64}).status_code == 503
        assert client.get('/api/state').status_code == 401


def test_broker_rejects_auth_arbitrary_docker_and_forged_fence(store, tmp_path):
    service = RuntimeBroker(store, RuntimeLedger(tmp_path / 'runtime.sqlite'), RuntimeBackend(mode='cloud-rootful-test'))
    with TestClient(create_broker_app(service, 'public-test-only-token')) as client:
        message = {'action': 'submit', 'task_id': str(uuid4()), 'revision': store.settings.source_revision}
        assert client.post('/rpc', json=message).status_code == 401
        header = {'Authorization': 'Bearer public-test-only-token'}
        assert client.post('/rpc', json={**message, 'privileged': True}, headers=header).status_code == 422
        assert client.post('/rpc', json={**message, 'fence': True}, headers=header).status_code == 422
        assert client.post('/rpc', json={**message, 'action': 'docker'}, headers=header).status_code == 422
        assert client.post('/rpc', json=message, headers=header).status_code == 409
        assert client.post('/rpc', content=b'x' * 2049, headers=header).status_code == 413
    service.pool.shutdown()


def test_broker_unavailable_has_no_direct_runtime_fallback(tmp_path):
    with pytest.raises(Exception):
        BrokerClient(str(tmp_path / 'missing.sock'), 'synthetic-token').request({'action': 'submit'})


def test_runtime_ledger_simultaneous_process_startup(tmp_path):
    path = tmp_path / 'shared' / 'runtime.sqlite'
    with ThreadPoolExecutor(max_workers=8) as pool:
        ledgers = list(pool.map(lambda _: RuntimeLedger(path), range(8)))
    assert all(ledger.verify() == '0' * 64 for ledger in ledgers)


@pytest.mark.parametrize('field,value', [('cpu', 8), ('memory_mib', 4096), ('pids', 4096),
                                        ('wall_seconds', 999), ('disk_mib', 1024), ('output_kib', 999)])
def test_runtime_limits_reject_expansion(field, value):
    with pytest.raises(ValueError):
        RuntimeLimits(**{field: value})


def test_runtime_endpoint_and_rootless_required():
    with pytest.raises(ValueError):
        RuntimeBackend('tcp://forbidden.invalid:2375')
    with pytest.raises(RuntimeError, match='rootless_not_verified'):
        RuntimeBackend(mode='rootless-required').preflight()


def test_broker_actual_executor_watchdog_admission_and_replay(store, tmp_path):
    ledger = RuntimeLedger(tmp_path / 'runtime.sqlite')
    backend = RuntimeBackend(mode='cloud-rootful-test')
    service = RuntimeBroker(store, ledger, backend)
    try:
        task = create(store, 'approved_render')
        ledger.watchdog()
        assert service.submit(task['id'], store.settings.source_revision)['phase'] == 'NOT_ADMITTED'
        store.approve('owner', task['id'], 1)
        with pytest.raises(Denied):
            service.submit(task['id'], 'f' * 40)
        run = service.submit(task['id'], store.settings.source_revision)
        service.last_future.result(timeout=30)
        assert ledger.get(task['id'], run['fence'])['phase'] == 'DONE'
        assert store.get(task['id'])['state'] == 'SUCCEEDED'
        assert service.submit(task['id'], store.settings.source_revision)['phase'] == 'NOT_ADMITTED'
    finally:
        service.pool.shutdown(wait=True)


@pytest.fixture
def sleeping_broker(store, tmp_path):
    builder = 'acc-f1-hardening-build-' + uuid4().hex
    image = 'acc-f1-hardening-sleeper:' + uuid4().hex
    assert docker('create', '--name', builder, 'acc-f1-executor:local').returncode == 0
    try:
        code = 'import sys,time;sys.stdin.read();time.sleep(60)'
        change = 'ENTRYPOINT ' + json.dumps(['python', '-I', '-c', code])
        assert docker('commit', '--change', change, builder, image).returncode == 0
        original = store.settings
        store.settings = replace(original, executor_image=image)
        ledger = RuntimeLedger(tmp_path / 'runtime.sqlite')
        backend = RuntimeBackend(mode='cloud-rootful-test')
        service = RuntimeBroker(store, ledger, backend, RuntimeLimits(heartbeat_seconds=1))
        ledger.watchdog()
        task = create(store)
        run = service.submit(task['id'], store.settings.source_revision)
        wait_ready(lambda: ledger.get(task['id'], run['fence'])['phase'] == 'ACTIVE', seconds=10)
        yield service, task, run
    finally:
        if 'service' in locals():
            for row in ledger.runs():
                docker('rm', '--force', row['name'])
            service.pool.shutdown(wait=True)
            store.settings = original
        docker('rm', '--force', builder)
        docker('image', 'rm', image)


@pytest.mark.parametrize('fault', ['worker_heartbeat', 'deadline', 'lease', 'cancel', 'audit'])
def test_watchdog_stops_real_container_independently(store, sleeping_broker, fault, admin):
    service, task, run = sleeping_broker
    ledger = service.ledger
    if fault == 'worker_heartbeat':
        with ledger.tx() as db:
            db.execute('UPDATE runs SET heartbeat=0')
    elif fault == 'deadline':
        with ledger.tx() as db:
            db.execute('UPDATE runs SET deadline=0')
    elif fault == 'lease':
        with store.transaction() as session:
            current = store.task(session, task['id'])
            current.lease_until = store.now(session) - timedelta(seconds=1)
    elif fault == 'cancel':
        store.cancel('owner', task['id'])
        store.cancel('owner', task['id'])
    else:
        with admin.engine.begin() as connection:
            connection.execute(text("UPDATE audit SET digest='corrupt'"))
    guard = Watchdog(store, ledger, service.backend, service.limits)
    guard.tick()
    service.last_future.result(timeout=20)
    assert docker('inspect', Runner.name({**task, 'fence': run['fence']})).returncode != 0
    assert store.get(task['id'])['state'] != 'SUCCEEDED'
    if fault == 'cancel':
        assert store.get(task['id'])['state'] == 'CANCELLED'
    ledger.verify()


def test_watchdog_loss_blocks_new_admission(store, tmp_path):
    ledger = RuntimeLedger(tmp_path / 'runtime.sqlite')
    service = RuntimeBroker(store, ledger, RuntimeBackend(mode='cloud-rootful-test'))
    try:
        task = create(store)
        with pytest.raises(Denied, match='watchdog_unavailable'):
            service.submit(task['id'], store.settings.source_revision)
        assert store.get(task['id'])['attempts'] == 0
    finally:
        service.pool.shutdown()


def test_owner_session_expiration_and_https_required(store, oidc):
    configured, assertion = oidc
    with TestClient(create_app(configured), base_url='https://testserver') as client:
        assert client.post('/api/auth/exchange', json={'assertion': assertion()}).status_code == 200
        with store.transaction() as session:
            session.execute(text("UPDATE owner_sessions SET expires_at=clock_timestamp()-interval '1 second'"))
        assert client.get('/api/state').status_code == 401
    with TestClient(create_app(configured), base_url='http://testserver') as client:
        assert client.post('/api/auth/exchange', json={'assertion': assertion()}).status_code == 403


def test_watchdog_cancel_stop_failure_never_claims_cancelled(store, tmp_path, monkeypatch):
    ledger = RuntimeLedger(tmp_path / 'runtime.sqlite')
    task = store.claim(create(store)['id'])
    ledger.register({**task, 'revision': store.settings.source_revision}, Runner.name(task), 30)
    ledger.phase(task['id'], task['fence'], 'ACTIVE')
    store.cancel('owner', task['id'])
    store.cancel('owner', task['id'])
    guard = Watchdog(store, ledger, RuntimeBackend(mode='cloud-rootful-test'))
    monkeypatch.setattr(guard.runner, 'stop', lambda _: False)
    guard.tick()
    guard.tick()
    guard.tick()
    assert store.get(task['id'])['state'] == 'CANCEL_REQUESTED'
    assert ledger.get(task['id'], task['fence'])['phase'] == 'UNCERTAIN'
    assert ledger.get(task['id'], task['fence'])['stops'] == 2
    assert not ledger.watchdog_ready()
    monkeypatch.undo()
    guard.reconcile_confirmed(task['id'], task['fence'])
    assert store.get(task['id'])['state'] == 'CANCELLED'
    assert store.snapshot()['halted']
    assert ledger.get(task['id'], task['fence'])['phase'] == 'DONE'


def test_watchdog_intent_absence_is_not_stop_proof(store, tmp_path):
    ledger = RuntimeLedger(tmp_path / 'runtime.sqlite')
    task = store.claim(create(store)['id'])
    ledger.register({**task, 'revision': store.settings.source_revision}, Runner.name(task), 1)
    with ledger.tx() as db:
        db.execute('UPDATE runs SET deadline=0')
    guard = Watchdog(store, ledger, RuntimeBackend(mode='cloud-rootful-test'))
    guard.tick()
    guard.tick()
    assert store.get(task['id'])['state'] == 'RECONCILING'
    assert ledger.get(task['id'], task['fence'])['phase'] == 'UNCERTAIN'


def test_watchdog_real_pg_loss_stops_and_reconciles_after_return(store, sleeping_broker):
    service, task, run = sleeping_broker
    guard = Watchdog(store, service.ledger, service.backend, service.limits)
    assert docker('stop', 'acc-f1-db-1').returncode == 0
    try:
        guard.tick()
        assert docker('inspect', Runner.name({**task, 'fence': run['fence']})).returncode != 0
    finally:
        assert docker('start', 'acc-f1-db-1').returncode == 0
        wait_ready(lambda: store.get(task['id'])['id'] == task['id'])
    service.last_future.result(timeout=20)
    guard.tick()
    assert store.get(task['id'])['state'] != 'SUCCEEDED'


def test_runtime_database_role_cannot_create_approval_or_read_owner_session(store, settings):
    password = Path('.runtime/secrets/db_runtime_password').read_text().strip()
    restricted = Store(replace(settings, database_url=settings.database_url.set(username='f1_runtime', password=password)))
    try:
        for sql in ('UPDATE approvals SET revoked=false', 'SELECT * FROM owner_sessions', "UPDATE tasks SET payload='{}'::jsonb"):
            with pytest.raises(Exception):
                with restricted.engine.begin() as connection:
                    connection.execute(text(sql))
    finally:
        restricted.engine.dispose()


def test_backup_job_actual_dump_readback_freshness_corruption_restore(store, admin, tmp_path):
    create(store)
    repo = LocalRepository(tmp_path / 'repo')
    jobs = BackupJobs(store, repo, b'K' * 32, tmp_path / 'state')
    receipt = jobs.backup()
    exported = jobs.checkpoint()
    with store.transaction() as session:
        store.check_audit(session, json.loads(repo.get(exported['name'])))
    assert jobs.status()['state'] == 'VERIFIED_LOCAL'
    assert jobs.status(now=datetime.now(timezone.utc) + timedelta(hours=1))['state'] == 'STALE_OR_CLOCK_ERROR'
    target = 'f1_restore_' + uuid4().hex
    try:
        assert jobs.restore(receipt['name'], target, admin.settings)['state'] == 'VERIFIED_QUARANTINED'
    finally:
        with admin.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{target}" WITH (FORCE)'))
    archive = repo.path(receipt['name'])
    data = archive.read_bytes()
    archive.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    assert jobs.status()['state'] == 'CORRUPT_OR_UNAVAILABLE'
    with pytest.raises(Exception):
        jobs.restore(receipt['name'], 'f1_restore_corrupt', admin.settings)


def test_backup_storage_no_overwrite_or_traversal_or_unbounded_spool(tmp_path):
    repo = LocalRepository(tmp_path, quota_mib=16)
    repo.put('fixture.enc', b'synthetic')
    with pytest.raises(FileExistsError):
        repo.put('fixture.enc', b'replace')
    with pytest.raises(ValueError):
        repo.put('../escape', b'x')
    with pytest.raises(ValueError):
        repo.put('huge.enc', b'x' * (17 * 1024 * 1024))
