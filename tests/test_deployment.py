"""F2.3 release-policy/failure tests. Fake daemons are NOT rootless host evidence."""
import copy
import fcntl
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


def test_password_profile_is_explicit_and_api_only(release):
    original, _ = release
    m = copy.deepcopy(original['manifest'])
    m['owner_login'] = {'origin': 'http://127.0.0.1:18000', 'loopback_http': True}
    # Use the same normalized source compose used by the existing fixture.
    source = Path(__file__).resolve().parents[1]
    env = dict(os.environ, F1_SOURCE_REVISION='a' * 40, F1_DOCKER_GID='0')
    base = json.loads(subprocess.check_output(['docker', 'compose', '--profile', 'worker', '-f',
        str(source / 'compose.yaml'), 'config', '--format', 'json'], env=env))
    p = render(base, m)
    assert p['services']['api']['environment']['F1_AUTH_MODE'] == 'password'
    assert p['services']['api']['ports'][0]['host_ip'] == '127.0.0.1'
    for name, service in p['services'].items():
        mounted = any(v['target'] == '/run/owner/password.json' for v in service.get('volumes', []))
        assert mounted == (name == 'api')
    bad = copy.deepcopy(p)
    bad['services']['api']['environment']['F1_WEB_ORIGIN'] = 'http://evil.invalid'
    with pytest.raises(ValueError, match='password_login_binding_changed'):
        validate_profile(bad, m)
    m['owner_login']['origin'] = 'http://public.example'
    with pytest.raises(ValueError, match='password_origin_invalid'):
        validate_manifest(m)


def telegram_release(release):
    bundle, _ = release
    m = copy.deepcopy(bundle['manifest'])
    m['telegram'] = {'mode': 'live', 'owner_id': 1234567, 'bot_id': 123456789,
                     'connection_digest': 'c' * 64}
    env = dict(os.environ, F1_SOURCE_REVISION='a' * 40, F1_DOCKER_GID='0')
    base = json.loads(subprocess.check_output(['docker', 'compose', '--profile', 'worker', '-f',
        str(Path(m['source_root']) / 'compose.yaml'), 'config', '--format', 'json'], env=env))
    return m, render(base, m)


def test_telegram_profile_is_explicit_db_only_and_default_stays_closed(release):
    m, profile = telegram_release(release)
    service = profile['services']['telegram']
    assert service['secrets'] == ['db_password'] and service['restart'] == 'no'
    assert not service.get('ports') and not service.get('privileged')
    assert all('docker.sock' not in v['source'] for v in service['volumes'])
    assert set(service['environment']) == {'F1_SOURCE_REVISION', 'F1_DB_USER', 'F1_DB_HOST', 'F1_DB_PASSWORD_FILE'}
    assert json.loads(profile['services']['api']['environment']['F1_TELEGRAM_SCOPE']) == m['telegram']
    assert 'telegram' not in release[0]['compose']['services']


@pytest.mark.parametrize('attack', ['socket', 'ports', 'network', 'secrets', 'cpu', 'memory', 'pids', 'restart', 'command', 'scope'])
def test_telegram_profile_rejects_extra_authority_and_unbounded_resources(release, attack):
    m, p = telegram_release(release)
    t = p['services']['telegram']
    if attack == 'socket':
        t['volumes'].append({'source': '/var/run/docker.sock', 'target': '/var/run/docker.sock'})
    elif attack == 'ports':
        t['ports'] = ['8001:8001']
    elif attack == 'network':
        t['networks']['access'] = None
    elif attack == 'secrets':
        t['secrets'].append('db_admin_password')
    elif attack == 'cpu':
        t['cpus'] = 4
    elif attack == 'memory':
        t['mem_limit'] = '8g'
    elif attack == 'pids':
        t['pids_limit'] = 99999
    elif attack == 'restart':
        t['restart'] = 'always'
    elif attack == 'command':
        t['command'] = ['sh']
    else:
        p['services']['api']['environment']['F1_TELEGRAM_SCOPE'] = '{}'
    with pytest.raises(ValueError):
        validate_profile(p, m)


def test_telegram_release_rejects_mock_or_extra_manifest_scope(release):
    m, _ = telegram_release(release)
    for value in ({**m['telegram'], 'mode': 'http_mock'}, {**m['telegram'], 'endpoint': 'https://other.invalid'}):
        with pytest.raises(ValueError, match='telegram_release_binding_invalid'):
            validate_manifest({**m, 'telegram': value})


def test_disabling_telegram_stops_previous_poller_and_blocks_unconfirmed_stop(release, tmp_path):
    m, old_profile = telegram_release(release)
    directory = tmp_path / 'telegram-old'
    directory.mkdir(mode=0o700)
    old = {'manifest': m, 'compose': old_profile}
    atomic_json(directory / 'bundle.json', old)
    atomic_json(directory / 'compose.json', old_profile)
    atomic_json(Path(m['data_root']) / 'deployment.json', {
        'phase': 'VERIFIED', 'bundle': checksum(old), 'directory': str(directory)})

    class StubbornEngine(FakeEngine):
        def run(self, *args, **kwargs):
            super().run(*args, **kwargs)
            return b'container-still-running' if args[0] == 'ps' else b''

    engine = StubbornEngine()
    target, target_dir = release
    controller = Deployment(target, target_dir, engine, engine)
    with pytest.raises(ValueError, match='stop_unconfirmed'):
        controller.pause_telegram()
    assert str(directory / 'compose.json') in engine.calls[0] and engine.calls[0][-2:] == ('stop', 'telegram')
    assert not any('up' in c for c in engine.calls)


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


@pytest.mark.parametrize('change', ['bundle', 'pending', 'missing', 'malformed'])
def test_remote_update_predecessor_is_checked_before_any_effect(operator, change):
    previous = mark_current(operator)
    previous['bundle'] = 'c' * 64
    expected = 'c' * 64
    if change == 'bundle':
        previous['bundle'] = 'd' * 64
    elif change == 'pending':
        previous['phase'] = 'INTENT'
    elif change == 'malformed':
        expected = 'main'
    atomic_json(operator.root / 'deployment.json', previous)
    if change == 'missing':
        (operator.root / 'deployment.json').unlink()
    with pytest.raises(ValueError, match='expected_previous_release_changed'):
        operator.apply('update', checksum(operator.bundle), expected_previous=expected)
    assert operator.engine.calls == []


def test_remote_update_exact_predecessor_uses_existing_backup_and_interlock(operator):
    previous = mark_current(operator)
    previous['bundle'] = 'c' * 64
    atomic_json(operator.root / 'deployment.json', previous)
    operator.apply('update', checksum(operator.bundle), expected_previous='c' * 64)
    calls = operator.engine.calls
    assert calls[0] == ('quiesce',) and calls[1] == ('encrypted_backup',)
    receipt = json.loads((operator.root / 'deployment.json').read_text())
    assert receipt['phase'] == 'VERIFIED' and receipt['previous_bundle'] == 'c' * 64


@pytest.mark.parametrize('change', ['none', 'predecessor', 'pending', 'owner_login', 'migration',
                                   'data_root', 'control_uid', 'catalog_revision', 'telegram_owner'])
def test_host_channel_enforces_owner_scope_and_ready_prepared_release(release, monkeypatch, change):
    import command_center.deployment as deployment_module
    import command_center.operations_channel as operations
    before = copy.deepcopy(release[0])
    target = copy.deepcopy(before)
    for value in (before, target):
        value['manifest']['data_root'] = '/home/acc-control/f30/state'
    target['manifest']['revision'] = 'd' * 40
    if change == 'owner_login':
        target['manifest']['owner_login'] = {'origin': 'http://127.0.0.1:18000', 'loopback_http': True}
    elif change == 'migration':
        target['manifest']['migration_hash'] = 'f' * 64
    elif change == 'data_root':
        target['manifest']['data_root'] = '/home/acc-control/other-state'
    elif change == 'control_uid':
        target['manifest']['control_uid'] = 0
    elif change == 'telegram_owner':
        before['manifest']['telegram'] = {'mode': 'live', 'owner_id': 12, 'bot_id': 34}
        target['manifest']['telegram'] = {'mode': 'live', 'owner_id': 56, 'bot_id': 34}
    active = dict(phase='INTENT' if change == 'pending' else 'VERIFIED',
                  bundle=checksum(before), directory='/home/acc-control/old/bundle')
    request = dict(action='update', target_bundle=checksum(target), expected_bundle=active['bundle'])
    if change == 'predecessor':
        request['expected_bundle'] = 'e' * 64
    policy = {'releases': {request['target_bundle']: dict(directory='/home/acc-control/new/bundle',
                         revision='f' * 40 if change == 'catalog_revision' else target['manifest']['revision'])}}
    monkeypatch.setattr(operations, 'protected_read', lambda *args, **kwargs: operations.canonical(active))
    monkeypatch.setattr(deployment_module, 'load_bundle', lambda p:
                        before if p == active['directory'] else target)
    monkeypatch.setattr(Deployment, 'preflight', lambda self: None)
    backend = operations.HostBackend(policy)
    if change == 'none':
        prepared = backend.prepare(request)
        assert prepared.bundle == target
        invoked = []
        monkeypatch.setattr(prepared, 'apply', lambda *args, **kwargs: invoked.append((args, kwargs)))
        backend.execute(request, prepared)
        assert invoked == [(('update', request['target_bundle']), {'expected_previous': request['expected_bundle']})]
    else:
        with pytest.raises(operations.Blocked):
            backend.prepare(request)


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
        api['networks'] = {'unapproved': None}
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


def test_boot_cannot_race_update_lock(operator):
    state = mark_current(operator)
    state['bundle'] = checksum(operator.bundle)
    atomic_json(operator.root / 'deployment.json', state)
    with (operator.root / 'deployment.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            operator.boot()
    assert not operator.engine.calls


def test_restart_policy_cannot_bypass_boot_interlock(release):
    p = release[0]['compose']
    for name in ('api', 'worker', 'runtime-broker', 'watchdog'):
        assert p['services'][name]['restart'] == 'no'


def test_update_preflight_rejects_modified_bind_source(release, monkeypatch):
    import command_center.deployment as module
    bundle, directory = release
    engine = FakeEngine()
    engine.preflight = lambda: None
    deployment = Deployment(bundle, directory, engine, engine)
    monkeypatch.setattr(os, 'getuid', lambda: 1000)
    monkeypatch.setattr(module, 'image_check', lambda *args: None)
    def changed(_):
        raise ValueError('source_checkout_changed')
    monkeypatch.setattr(module, 'source_check', changed)
    with pytest.raises(ValueError, match='source_checkout_changed'):
        deployment.preflight(fresh=False)


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
