"""F2.3 release-policy/failure tests. Fake daemons are NOT rootless host evidence."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from command_center.deployment import Deployment, Engine, initialize_state, load_bundle
from command_center.deployment_profile import atomic_json, checksum, render, validate_manifest, validate_profile
from command_center.recovery import seal


@pytest.fixture
def release(tmp_path):
    root = tmp_path / 'state'
    initialize_state(root)
    source = Path(__file__).resolve().parents[1]
    env = dict(os.environ, F1_SOURCE_REVISION='a' * 40, F1_DOCKER_GID='0')
    result = subprocess.run(['docker', 'compose', '--profile', 'worker', '-f', str(source / 'compose.yaml'), 'config', '--format', 'json'],
                            capture_output=True, env=env, check=True)
    base = json.loads(result.stdout)
    m = dict(schema=1, revision='a' * 40, control_uid=1000, execution_uid=1001, data_root=str(root),
             source_root=str(source), images={k: 'sha256:' + str(i) * 64 for i, k in enumerate(
                 ('api', 'worker', 'broker', 'executor', 'coding'), 1)},
             database_image=base['services']['db']['image'], redis_image=base['services']['redis']['image'],
             migration_hash='b' * 64)
    directory = tmp_path / 'release'
    directory.mkdir(mode=0o700)
    bundle = {'manifest': m, 'compose': render(base, m)}
    atomic_json(directory / 'bundle.json', bundle)
    atomic_json(directory / 'compose.json', bundle['compose'])
    return bundle, directory


class FakeEngine:
    def __init__(self):
        self.calls = []
        self.fail = False

    def run(self, *args, **kwargs):
        self.calls.append(args)
        if self.fail:
            raise RuntimeError('daemon_unavailable')
        return b''


@pytest.fixture
def operator(release, monkeypatch):
    bundle, directory = release
    engine = FakeEngine()
    deployment = Deployment(bundle, directory, engine, FakeEngine())
    monkeypatch.setattr(deployment, 'preflight', lambda **kwargs: None)
    monkeypatch.setattr(deployment, 'postcheck', lambda: {'go_live': False})
    monkeypatch.setattr(deployment, 'tool', lambda code: engine.run('maintenance', code))
    monkeypatch.setattr(deployment, 'quiesce', lambda: engine.run('quiesce'))
    monkeypatch.setattr(deployment, 'backup', lambda: engine.run('encrypted_backup'))
    return deployment


def mark_current(deployment, *, phase='VERIFIED', previous='old'):
    value = {'phase': phase, 'bundle': 'current', 'migration_hash': deployment.m['migration_hash'],
             'database_image': deployment.m['database_image'], 'previous_bundle': previous}
    atomic_json(deployment.root / 'deployment.json', value)
    return value


def test_profile_closed_and_normalizes_with_real_compose(release):
    bundle, directory = release
    result = subprocess.run(['docker', 'compose', '-f', str(directory / 'compose.json'), 'config', '--format', 'json'],
                            capture_output=True, check=True)
    p = json.loads(result.stdout)
    assert set(p['services']) == {'db', 'redis', 'api', 'worker', 'runtime-broker', 'watchdog'}
    assert p['services']['api']['environment']['F1_AUTH_MODE'] == 'oidc'
    assert p['services']['api']['environment']['F1_OIDC_OWNER'] == ''
    assert 'build' not in p['services']['api']
    assert p['volumes']['pgdata']['name'] == 'acc-f23-pgdata'
    assert load_bundle(directory) == bundle


@pytest.mark.parametrize('attack', ['public', 'privileged', 'socket', 'host_mount', 'host_network',
                                   'synthetic_auth', 'rootful', 'integration', 'wrong_image', 'secret_scope', 'egress'])
def test_profile_rejects_boundary_changes(release, attack):
    bundle, _ = release
    p = copy.deepcopy(bundle['compose'])
    api = p['services']['api']
    if attack == 'public':
        api['ports'][0]['host_ip'] = '0.0.0.0'
    elif attack == 'privileged':
        api['privileged'] = True
    elif attack == 'socket':
        api['volumes'].append({'source': '/var/run/docker.sock', 'target': '/var/run/docker.sock'})
    elif attack == 'host_mount':
        api['volumes'].append({'source': '/etc', 'target': '/host', 'read_only': True})
    elif attack == 'host_network':
        api['network_mode'] = 'host'
    elif attack == 'synthetic_auth':
        api['environment']['F1_AUTH_MODE'] = 'synthetic'
    elif attack == 'rootful':
        p['services']['watchdog']['environment']['F1_RUNTIME_MODE'] = 'cloud-rootful-test'
    elif attack == 'integration':
        api['environment']['F2_INTEGRATION_CONFIG_FILE'] = '/host/live.json'
    elif attack == 'wrong_image':
        api['image'] = 'alpine:latest'
    elif attack == 'secret_scope':
        api['secrets'].append({'source': 'db_admin_password'})
    else:
        api['networks'] = {'access': None}
    with pytest.raises(ValueError):
        validate_profile(p, bundle['manifest'])


@pytest.mark.parametrize('field,value', [('control_uid', 0), ('execution_uid', 1000), ('revision', 'main'),
                                       ('database_image', 'postgres:latest'), ('data_root', '../state')])
def test_manifest_rejects_unpinned_or_privileged(release, field, value):
    m = copy.deepcopy(release[0]['manifest'])
    m[field] = value
    with pytest.raises(ValueError):
        validate_manifest(m)


def test_secret_initialization_never_overwrites_or_prints(tmp_path, capsys):
    root = tmp_path / 'state'
    initialize_state(root)
    contents = (root / 'secrets/db_password').read_bytes()
    assert (root.stat().st_mode & 0o777) == 0o700
    assert all((p.stat().st_mode & 0o777) == 0o600 for p in (root / 'secrets').iterdir())
    with pytest.raises(FileExistsError):
        initialize_state(root)
    assert contents == (root / 'secrets/db_password').read_bytes()
    assert not capsys.readouterr().out


def test_bundle_tamper_and_symlink_rejected(release, tmp_path):
    _, directory = release
    atomic_json(directory / 'compose.json', {})
    with pytest.raises(ValueError, match='profile_changed'):
        load_bundle(directory)
    link = tmp_path / 'alias'
    link.symlink_to(directory)
    with pytest.raises(ValueError, match='custody'):
        load_bundle(link)


def test_install_is_bounded_and_halted(operator):
    result = operator.apply('install', checksum(operator.bundle))
    assert result == {'go_live': False}
    commands = str(operator.engine.calls)
    assert 'halt' in commands and 'command_center.admin' in commands
    assert 'pull' in commands and 'never' in commands
    assert 'down' not in commands and 'volume rm' not in commands
    assert json.loads((operator.root / 'deployment.json').read_text())['phase'] == 'VERIFIED'


def test_wrong_consent_cannot_start_any_command(operator):
    with pytest.raises(ValueError, match='authorization'):
        operator.apply('install', 'old-digest')
    assert not operator.engine.calls


def test_update_quiesce_backup_before_any_stop(operator):
    mark_current(operator)
    operator.apply('update', checksum(operator.bundle))
    commands = operator.engine.calls
    assert commands[0] == ('quiesce',) and commands[1] == ('encrypted_backup',)
    assert 'stop' in commands[2]
    assert not any('command_center.admin' in str(c) for c in commands)


@pytest.mark.parametrize('fault', ['cancel_uncertain', 'backup_failure'])
def test_update_cannot_stop_services_if_safe_checkpoint_fails(operator, monkeypatch, fault):
    mark_current(operator)
    def fail():
        raise ValueError(fault)
    monkeypatch.setattr(operator, 'quiesce' if fault == 'cancel_uncertain' else 'backup', fail)
    with pytest.raises(ValueError, match=fault):
        operator.apply('update', checksum(operator.bundle))
    assert not any('stop' in c for c in operator.engine.calls)
    assert json.loads((operator.root / 'deployment.json').read_text())['phase'] == 'VERIFIED'


@pytest.mark.parametrize('change', ['schema', 'major'])
def test_database_changes_are_not_automatic(operator, change):
    old = mark_current(operator)
    old['migration_hash' if change == 'schema' else 'database_image'] = 'different'
    atomic_json(operator.root / 'deployment.json', old)
    with pytest.raises(ValueError, match='migration_plan'):
        operator.apply('update', checksum(operator.bundle))
    assert not operator.engine.calls


def test_failed_rollout_is_durable_and_not_blindly_retried(operator, monkeypatch):
    def fail(*args):
        raise RuntimeError('lost_daemon_response')
    monkeypatch.setattr(operator, 'compose', fail)
    with pytest.raises(RuntimeError):
        operator.apply('install', checksum(operator.bundle))
    assert json.loads((operator.root / 'deployment.json').read_text())['phase'] == 'INTENT'
    with pytest.raises(ValueError, match='investigation'):
        operator.apply('update', checksum(operator.bundle))


@pytest.mark.parametrize('phase', ['VERIFIED', 'INTENT'])
def test_rollback_only_exact_predecessor_without_database_restore(operator, phase):
    mark_current(operator, phase=phase, previous=checksum(operator.bundle))
    operator.apply('rollback', checksum(operator.bundle))
    assert 'pg_restore' not in str(operator.engine.calls)
    assert 'command_center.admin' not in str(operator.engine.calls)


def test_rollback_other_release_denied(operator):
    mark_current(operator, previous='different')
    with pytest.raises(ValueError, match='predecessor'):
        operator.apply('rollback', checksum(operator.bundle))
    assert not operator.engine.calls


@pytest.mark.parametrize('corruption', ['ciphertext', 'wrong_key', 'checksum'])
def test_corrupt_backup_never_reaches_restore_runtime(release, corruption):
    bundle, directory = release
    engine = FakeEngine()
    deployment = Deployment(bundle, directory, engine)
    key = bytes.fromhex((deployment.root / 'secrets/backup_key').read_text())
    payload = json.dumps({'schema': 1, 'dump_sha256': 'incorrect'}).encode() + b'\n' + b'dump'
    archive = bytearray(seal(payload, key))
    if corruption == 'ciphertext':
        archive[-1] ^= 1
    if corruption == 'wrong_key':
        (deployment.root / 'secrets/backup_key').write_text('00' * 32)
    path = deployment.root / 'backups/test.enc'
    path.write_bytes(archive)
    with pytest.raises(Exception):
        deployment.restore_check(path)
    assert not engine.calls


@pytest.mark.parametrize('rootless,cgroup,memory', [(False, '2', True), (True, '1', True), (True, '2', False)])
def test_runtime_preflight_fails_closed(monkeypatch, rootless, cgroup, memory):
    engine = Engine(1000)
    monkeypatch.setattr(Path, 'stat', lambda self: SimpleNamespace(st_mode=0o140600, st_uid=1000))
    monkeypatch.setattr(engine, 'json', lambda *args: {'SecurityOptions': ['name=rootless'] if rootless else [],
        'CgroupVersion': cgroup, 'MemoryLimit': memory, 'PidsLimit': True, 'CpuCfsQuota': True})
    with pytest.raises(ValueError, match='cgroup'):
        engine.preflight()


def test_bootstrap_plan_defaults_no_mutation_and_capacity_floor():
    path = Path(__file__).resolve().parents[1] / 'infra/vps/bootstrap_f23.py'
    spec = importlib.util.spec_from_file_location('f23bootstrap', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    p = module.plan('1:1.2.3-1~ubuntu.24.04~noble', '1.2', '1.2', '1.2')
    assert p['network_changes'] is False and p['rootless_users'] == 2
    with pytest.raises(ValueError, match='versions'):
        module.plan('', '', '', '')
    with pytest.raises(ValueError, match='capacity'):
        module.capacity_gate(2, 8192, 20000)
    module.capacity_gate(4, 7600, 20000)
    with pytest.raises(ValueError, match='authorization'):
        module.apply(p, 'no-permission')
