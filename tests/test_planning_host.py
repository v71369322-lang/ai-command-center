"""Linux/PG lifecycle tests with synthetic rootless metadata and mock HTTP, never host acceptance."""
from copy import deepcopy
import hashlib
import json
import os
import socket
import sqlite3
from dataclasses import replace
from threading import Event
from types import SimpleNamespace

import pytest

from command_center.models import Approval, ExternalAction, Task
from command_center.planning_admission import PlanningProfile
from command_center.planning_host import HostDeclaration, PlanningHost, metadata_document
from command_center.runtime_broker import RuntimeBroker
from command_center.runtime_ledger import RuntimeLedger
from command_center.runtime_policy import RuntimeLimits
from command_center.store import Denied, digest
from command_center.watchdog import Watchdog
from test_live_planning_gateway import prepared as prepared
from test_telegram_planning_authorize import profile as profile, issue, click, rows
from test_telegram_readiness import bridge as bridge
from test_telegram_service import configured as configured


@pytest.fixture
def host_setup(prepared, store, bridge, tmp_path):
    ledger = RuntimeLedger(tmp_path / 'runtime' / 'ledger.sqlite')
    limits = RuntimeLimits(wall_seconds=30, heartbeat_seconds=30, watchdog_seconds=30)
    image_id, container_id = 'sha256:' + 'a' * 64, 'b' * 64
    container_name = 'acc-f23-runtime-broker-1'
    info = {'Id': container_id, 'Name': '/' + container_name, 'Image': image_id,
        'State': {'Running': True, 'OOMKilled': False},
        'Config': {'Hostname': socket.gethostname(), 'User': str(os.geteuid()) + ':0', 'WorkingDir': '/app',
                   'Env': ['PATH=/usr/local/bin:/usr/bin:/bin', 'PYTHONPATH=/app/src',
                           'F1_SOURCE_REVISION=' + store.settings.source_revision],
                   'Cmd': ['uvicorn', 'command_center.runtime_broker:create_broker_app', '--factory',
                           '--uds', '/run/f1-broker/runtime.sock', '--no-access-log'],
                   'Entrypoint': None},
        'HostConfig': {'ReadonlyRootfs': True, 'Privileged': False, 'CapDrop': ['ALL'], 'CapAdd': [],
            'SecurityOpt': ['no-new-privileges:true'], 'Memory': 256 * 1024 * 1024,
            'NanoCpus': 500000000, 'PidsLimit': 64, 'NetworkMode': 'synthetic-control'}, 'Mounts': []}

    class Backend:
        mode, endpoint = 'rootless-required', 'unix:///run/user/1000/docker.sock'
        def __init__(self):
            self.info, self.calls = info, []
            self.image_source = store.settings.source_revision
            self.verified = True
        def preflight(self):
            self.calls.append(('preflight',))
            return {'mode': self.mode, 'rootless_verified': self.verified}
        def call(self, *args, **kwargs):
            self.calls.append(args)
            if args == ('inspect', container_name):
                value = self.info
            elif args == ('image', 'inspect', image_id):
                value = {'Id': image_id, 'Config': {'Labels': {'org.opencontainers.image.revision': self.image_source},
                                                   'Env': ['PATH=/usr/local/bin:/usr/bin:/bin', 'PYTHONPATH=/app/src']}}
            else:
                pytest.fail('planning lifecycle must not start/stop an executor container')
            return SimpleNamespace(returncode=0, stdout=json.dumps([value]).encode())

    backend = Backend()
    declaration = HostDeclaration(source_revision=store.settings.source_revision, container_name=container_name,
        image_id=image_id, endpoint=backend.endpoint, ledger_path=str(ledger.path.resolve()),
        metadata_digest=digest(metadata_document(info)))
    path = prepared.key.parent / 'host.json'
    raw = declaration.model_dump_json().encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    host = PlanningHost(str(path), hashlib.sha256(raw).hexdigest())
    data = prepared.config.model_dump()
    data['runtime']['binding_digest'] = digest(declaration.model_dump())
    prepared.config = PlanningProfile.model_validate(data)
    prepared.save(prepared.config)
    ledger.watchdog()
    ledger.worker_beat(store.settings.source_revision)
    issue(bridge)
    bridge[0].receive(click(bridge))
    task = rows(store, Task)[0]
    service = RuntimeBroker(store, ledger, backend, limits, planning_host=host)
    yield SimpleNamespace(prepared=prepared, store=store, ledger=ledger, backend=backend, host=host,
                          path=path, declaration=declaration, service=service, task_id=task.id, limits=limits)
    service.pool.shutdown(wait=True)


def submit(value):
    result = value.service.submit(value.task_id, value.store.settings.source_revision)
    value.service.last_future.result(timeout=20)
    return result


def test_broker_rootless_attestation_claim_and_returned_operation(host_setup):
    value = host_setup
    result = submit(value)
    row = value.ledger.get(value.task_id, result['fence'])
    assert row['kind'] == 'planning_http' and row['returned'] == 1 and row['phase'] == 'DONE'
    assert value.store.get(value.task_id)['state'] == 'SUCCEEDED'
    assert len(value.prepared.calls) == 1 and rows(value.store, ExternalAction)[0].actual == 700
    value.ledger.verify()
    assert value.service.submit(value.task_id, value.store.settings.source_revision)['phase'] == 'NOT_ADMITTED'
    assert len(value.prepared.calls) == 1


@pytest.mark.parametrize('change', ['mode', 'rootless', 'source', 'image', 'hostname', 'user', 'rw',
    'privileged', 'memory', 'caps', 'mount', 'command', 'declaration', 'watchdog', 'worker', 'profile',
    'pythonpath', 'path', 'preload', 'system_mount'])
def test_preclaim_attestation_failures_do_not_consume_approval(host_setup, change):
    value = host_setup
    info = value.backend.info
    if change == 'mode':
        value.backend.mode = 'cloud-rootful-test'
    elif change == 'rootless':
        value.backend.verified = False
    elif change == 'source':
        value.backend.image_source = 'e' * 40
    elif change == 'image':
        info['Image'] = 'sha256:' + 'e' * 64
    elif change in {'hostname', 'user'}:
        info['Config']['Hostname' if change == 'hostname' else 'User'] = 'foreign'
    elif change == 'rw':
        info['HostConfig']['ReadonlyRootfs'] = False
    elif change == 'privileged':
        info['HostConfig']['Privileged'] = True
    elif change == 'memory':
        info['HostConfig']['Memory'] = 0
    elif change == 'caps':
        info['HostConfig']['CapAdd'] = ['SYS_ADMIN']
    elif change == 'mount':
        info['Mounts'] = [{'Source': '/public', 'Destination': '/app/src', 'RW': True}]
    elif change == 'command':
        info['Config']['Cmd'] = ['sh', '-c', 'not-the-broker']
    elif change == 'pythonpath':
        info['Config']['Env'].append('PYTHONPATH=/tmp/untrusted')
    elif change == 'path':
        info['Config']['Env'].append('PATH=/tmp/untrusted')
    elif change == 'preload':
        info['Config']['Env'].append('LD_PRELOAD=/tmp/untrusted')
    elif change == 'system_mount':
        info['Mounts'] = [{'Source': '/public', 'Destination': '/usr/local/lib', 'RW': True}]
    elif change == 'declaration':
        value.path.write_text('{}')
    elif change == 'watchdog':
        value.ledger.watchdog(False)
    elif change == 'worker':
        value.ledger.worker_beat('e' * 40)
    else:
        data = value.prepared.config.model_dump()
        data['runtime']['binding_digest'] = 'e' * 64
        value.prepared.save(PlanningProfile.model_validate(data))
    with pytest.raises((Denied, RuntimeError, ValueError)):
        value.service.submit(value.task_id, value.store.settings.source_revision)
    assert value.store.get(value.task_id)['state'] == 'READY'
    assert not rows(value.store, Approval)[0].used
    assert not value.ledger.runs() and not value.prepared.calls


def test_absent_host_keeps_existing_production_default_closed(host_setup):
    value = host_setup
    value.service.planning_host = None
    with pytest.raises(Denied, match='planning_runtime_not_connected'):
        value.service.submit(value.task_id, value.store.settings.source_revision)
    assert not value.backend.calls and not rows(value.store, Approval)[0].used


def test_http_uncertainty_is_not_reported_as_stopped_container(host_setup):
    value = host_setup
    value.prepared.drop = True
    result = submit(value)
    row = value.ledger.get(value.task_id, result['fence'])
    assert row['returned'] == 1 and row['phase'] == 'UNCERTAIN'
    assert value.store.get(value.task_id)['state'] == 'RECONCILING'
    assert rows(value.store, ExternalAction)[0].reserved > 0
    with pytest.raises(Denied):
        value.service.submit(value.task_id, value.store.settings.source_revision)
    assert len(value.prepared.calls) == 1


def test_watchdog_never_uses_container_absence_to_prove_http_stop(host_setup):
    value = host_setup
    entered, release = Event(), Event()
    value.prepared.after = lambda: (entered.set(), release.wait(10))
    result = value.service.submit(value.task_id, value.store.settings.source_revision)
    assert entered.wait(10)
    watchdog = Watchdog(value.store, value.ledger, value.backend, value.limits)
    try:
        watchdog.emergency(value.ledger.get(value.task_id, result['fence']), 'synthetic_revocation')
        row = value.ledger.get(value.task_id, result['fence'])
        assert row['phase'] == 'UNCERTAIN' and not row['returned']
        with pytest.raises(Denied, match='return_evidence_required'):
            watchdog.reconcile_confirmed(value.task_id, result['fence'])
    finally:
        release.set()
    value.service.last_future.result(timeout=15)
    row = value.ledger.get(value.task_id, result['fence'])
    assert row['returned'] == 1 and row['phase'] == 'UNCERTAIN'
    watchdog.reconcile_confirmed(value.task_id, result['fence'])
    assert value.ledger.get(value.task_id, result['fence'])['phase'] == 'DONE'
    assert value.store.snapshot()['halted']
    assert rows(value.store, ExternalAction)[0].reserved > 0
    assert len(value.prepared.calls) == 1


def test_tampered_operation_kind_and_returned_flag_are_detected(host_setup):
    value = host_setup
    value.prepared.drop = True
    result = submit(value)
    with value.ledger.tx() as db:
        db.execute("UPDATE runs SET kind='container' WHERE id=?", (value.task_id,))
    with pytest.raises(ValueError, match='operation_evidence_corrupt'):
        value.ledger.verify()
    with value.ledger.tx() as db:
        db.execute("UPDATE runs SET kind='planning_http',returned=0 WHERE id=?", (value.task_id,))
    with pytest.raises(ValueError, match='operation_evidence_corrupt'):
        value.ledger.verify()
    assert result['fence'] == 1


def test_old_container_ledger_migrates_without_inventing_http_evidence(tmp_path):
    path = tmp_path / 'old.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE runs(id TEXT PRIMARY KEY,fence INTEGER,name TEXT,phase TEXT,deadline REAL,'
                   'heartbeat REAL,revision TEXT,stops INTEGER DEFAULT 0,observed INTEGER NOT NULL DEFAULT 0)')
    ledger = RuntimeLedger(path)
    task = {'id': 'public-task', 'fence': 1, 'revision': 'a' * 40}
    ledger.register(task, 'public-container', 30)
    row = ledger.get(task['id'], 1)
    assert row['kind'] == 'container' and row['returned'] == 0
    with pytest.raises(ValueError, match='planning_runtime_required'):
        ledger.planning_returned(task['id'], 1)
    ledger.verify()


def test_host_metadata_excludes_environment_values(host_setup):
    info = deepcopy(host_setup.backend.info)
    info['Config']['Env'] = ['SYNTHETIC_SECRET=not-for-metadata']
    assert 'not-for-metadata' not in json.dumps(metadata_document(info))


def test_prepared_declaration_does_not_require_a_future_container_id(host_setup):
    value = host_setup
    before = value.path.read_bytes()
    value.host.preflight(value.store, value.ledger, value.backend)
    assert value.host.container_id == 'b' * 64
    value.backend.info['Id'] = 'c' * 64
    recreated = PlanningHost(str(value.path), hashlib.sha256(before).hexdigest())
    recreated.preflight(value.store, value.ledger, value.backend)
    assert recreated.container_id == 'c' * 64 and value.path.read_bytes() == before
    assert not value.prepared.calls and not rows(value.store, Approval)[0].used


def test_pulse_keeps_f1_lease_during_slow_http(host_setup, monkeypatch):
    value = host_setup
    monkeypatch.setattr(value.store, 'settings', replace(value.store.settings, lease_seconds=4))
    value.prepared.after = lambda: Event().wait(5)
    result = submit(value)
    assert value.store.get(value.task_id)['state'] == 'SUCCEEDED'
    assert value.ledger.get(value.task_id, result['fence'])['returned'] == 1
    assert len(value.prepared.calls) == 1


def test_wall_deadline_revokes_stream_and_retains_uncertain_money(host_setup):
    value = host_setup
    value.service.limits = RuntimeLimits(wall_seconds=1, heartbeat_seconds=30, watchdog_seconds=30)
    value.prepared.after = lambda: Event().wait(2)
    result = submit(value)
    assert value.ledger.get(value.task_id, result['fence'])['phase'] == 'UNCERTAIN'
    assert rows(value.store, ExternalAction)[0].reserved > 0 and len(value.prepared.calls) == 1


def test_restart_has_no_automatic_return_or_retry_evidence(host_setup):
    value = host_setup
    task = value.store.claim(value.task_id)
    task['revision'] = value.store.settings.source_revision
    value.ledger.register(task, 'public-http-name', 30, kind='planning_http')
    value.ledger.phase(task['id'], task['fence'], 'ACTIVE')
    restarted = RuntimeLedger(value.ledger.path)
    watchdog = Watchdog(value.store, restarted, value.backend, value.limits)
    watchdog.emergency(restarted.get(task['id'], task['fence']), 'broker_restart')
    with pytest.raises(Denied, match='return_evidence_required'):
        watchdog.reconcile_confirmed(task['id'], task['fence'])
    assert not restarted.get(task['id'], task['fence'])['returned'] and not value.prepared.calls


@pytest.mark.parametrize('unsafe', ['privileged', 'code_mount', 'preload', 'unbounded', 'host_network',
                                  'unconfined', 'public_rpc', 'python_userbase'])
def test_even_matching_operator_pin_cannot_allow_unsafe_host(host_setup, unsafe):
    value = host_setup
    if unsafe == 'privileged':
        value.backend.info['HostConfig']['Privileged'] = True
    elif unsafe == 'code_mount':
        value.backend.info['Mounts'] = [{'Source': '/public', 'Destination': '/app/src', 'RW': False}]
    elif unsafe == 'preload':
        value.backend.info['Config']['Env'].append('LD_PRELOAD=/tmp/untrusted')
    elif unsafe == 'host_network':
        value.backend.info['HostConfig']['NetworkMode'] = 'host'
    elif unsafe == 'unconfined':
        value.backend.info['HostConfig']['SecurityOpt'].append('apparmor=unconfined')
    elif unsafe == 'public_rpc':
        value.backend.info['Config']['Cmd'] = ['uvicorn', 'command_center.runtime_broker:create_broker_app',
                                             '--host', '0.0.0.0', '--port', '8000']
    elif unsafe == 'python_userbase':
        value.backend.info['Config']['Env'].append('PYTHONUSERBASE=/tmp/untrusted')
    else:
        value.backend.info['HostConfig']['Memory'] = 0
    declaration = value.declaration.model_copy(update={'metadata_digest': digest(metadata_document(value.backend.info))})
    raw = declaration.model_dump_json().encode()
    value.path.write_bytes(raw)
    value.service.planning_host = PlanningHost(str(value.path), hashlib.sha256(raw).hexdigest())
    data = value.prepared.config.model_dump()
    data['runtime']['binding_digest'] = digest(declaration.model_dump())
    value.prepared.save(PlanningProfile.model_validate(data))
    with pytest.raises(Denied):
        value.service.submit(value.task_id, value.store.settings.source_revision)
    assert not rows(value.store, Approval)[0].used and not value.prepared.calls
