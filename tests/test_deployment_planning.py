"""Private deployment bindings and installed scope, using only synthetic files/images."""
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import time

import pytest

from command_center import deployment_planning as binding
from command_center.deployment import Deployment
from command_center.deployment_profile import render, validate_manifest, validate_profile
from command_center.planning_admission import PlanningProfile
from command_center.planning_host import HostDeclaration
from command_center.store import Denied, digest
from test_deployment import release as release
from test_planning_admission import profile as profile


@pytest.fixture
def planning_release(release, profile, tmp_path):
    original, _ = release
    m = deepcopy(original['manifest'])
    m['telegram'] = {'mode': 'live', 'owner_id': 1234567, 'bot_id': 123456789,
                     'connection_digest': 'c' * 64}
    host = HostDeclaration(source_revision=m['revision'], container_name='acc-f23-runtime-broker-1',
        image_id=m['images']['broker'], endpoint='unix:///var/run/docker.sock',
        attestation_endpoint=f'unix:///run/user/{m["control_uid"]}/docker.sock',
        ledger_path='/var/lib/f1-runtime/ledger.sqlite', metadata_digest='d' * 64)
    public_key = b'PUBLIC_SYNTHETIC_PLANNING_KEY_ONLY_12345'
    data = profile.model_dump()
    data['runtime'] = {'source_revision': m['revision'], 'binding_digest': digest(host.model_dump()),
                       'credential_sha256': hashlib.sha256(public_key).hexdigest()}
    data['evidence'].update(observed_at=int(time.time()) - 10, expires_at=int(time.time()) + 900)
    profile = PlanningProfile.model_validate(data)
    directory, keys = tmp_path / 'planning-private', tmp_path / 'planning-key-private'
    directory.mkdir(mode=0o700)
    keys.mkdir(mode=0o700)
    for path, raw in ((directory / 'profile.json', profile.model_dump_json().encode()),
                      (directory / 'host.json', host.model_dump_json().encode()),
                      (keys / 'openai.key', public_key)):
        path.write_bytes(raw)
        path.chmod(0o600)
    m['planning'] = binding.prepare_binding(m, directory, keys)
    return m, render(original['compose'], m), profile, host


def test_bound_profile_key_and_control_socket_are_broker_scoped(planning_release):
    m, compose, profile, host = planning_release
    assert binding.check_binding(m) == (profile, host)
    validate_manifest(m)
    validate_profile(compose, m)
    for name, service in compose['services'].items():
        targets = {v['target'] for v in service.get('volumes', [])}
        assert ('/run/planning' in targets) == (name in {'telegram', 'runtime-broker'})
        assert ('/run/planning-key' in targets) == (name == 'runtime-broker')
        assert (f'/run/user/{m["control_uid"]}/docker.sock' in targets) == (name == 'runtime-broker')
        assert ('planning-access' in service['networks']) == (name == 'runtime-broker')
        actual = {k: v for k, v in service.get('environment', {}).items() if k.startswith('F1_PLANNING_')}
        assert actual == binding.environment(m, name)


def test_preflight_does_not_read_key_or_open_a_provider_client(planning_release, monkeypatch):
    m, _, _, _ = planning_release
    key = Path(m['planning']['key_directory']) / 'openai.key'
    real_open, real_fdopen = io.open, os.fdopen

    def open_file(path, *args, **kwargs):
        assert (Path(f'/proc/self/fd/{path}').resolve() if isinstance(path, int) else Path(path)) != key
        return real_open(path, *args, **kwargs)

    def fdopen(fd, *args, **kwargs):
        assert Path(f'/proc/self/fd/{fd}').resolve() != key
        return real_fdopen(fd, *args, **kwargs)

    monkeypatch.setattr(io, 'open', open_file)
    monkeypatch.setattr(os, 'fdopen', fdopen)
    monkeypatch.setattr('httpx.Client', lambda *a, **k: pytest.fail('provider client during preflight'))
    binding.check_binding(m)


@pytest.mark.parametrize('attack', ['profile', 'host', 'profile_pin', 'host_pin', 'source', 'image',
    'extra_profile_file', 'extra_key_file', 'profile_mode', 'key_mode', 'directory_mode',
    'key_symlink', 'key_hardlink', 'expired', 'future', 'first_experiment', 'no_telegram', 'nested', 'state_mount'])
def test_binding_changes_fail_closed(planning_release, attack, monkeypatch):
    m, _, _, _ = planning_release
    b = m['planning']
    directory, keys = Path(b['profile_directory']), Path(b['key_directory'])
    if attack in {'profile', 'host'}:
        path = directory / (attack + '.json')
        path.write_bytes(path.read_bytes() + b' ')
    elif attack.endswith('_pin'):
        b[attack.removesuffix('_pin') + '_sha256'] = 'f' * 64
    elif attack == 'source':
        m['revision'] = 'f' * 40
    elif attack == 'image':
        m['images']['broker'] = 'sha256:' + 'f' * 64
    elif attack.startswith('extra_'):
        ((directory if attack == 'extra_profile_file' else keys) / 'unexpected').touch()
    elif attack in {'profile_mode', 'key_mode', 'directory_mode'}:
        {'profile_mode': directory / 'profile.json', 'key_mode': keys / 'openai.key',
         'directory_mode': directory}[attack].chmod(0o755)
    elif attack == 'key_symlink':
        key = keys / 'openai.key'
        key.unlink()
        key.symlink_to(directory / 'profile.json')
    elif attack == 'key_hardlink':
        (keys.parent / 'linked').hardlink_to(keys / 'openai.key')
    elif attack in {'expired', 'future'}:
        monkeypatch.setattr(binding.time, 'time', lambda: 0 if attack == 'future' else 2**40)
    elif attack == 'first_experiment':
        m['first_experiment'] = {}
    elif attack == 'no_telegram':
        del m['telegram']
    elif attack == 'state_mount':
        b['key_directory'] = str(Path(m['data_root']) / 'runtime-ledger' / 'keys')
    else:
        b['key_directory'] = str(directory / 'nested')
    with pytest.raises((ValueError, Denied, OSError)):
        binding.check_binding(m)


@pytest.mark.parametrize('attack', ['telegram_key', 'api_profile', 'worker_control_socket', 'writable',
                                   'host_path', 'host_pin', 'unknown_flag', 'network', 'no_binding'])
def test_compose_scope_cannot_expand(planning_release, attack):
    m, compose, _, _ = planning_release
    broker = compose['services']['runtime-broker']
    if attack in {'telegram_key', 'api_profile', 'worker_control_socket'}:
        service, index = {'telegram_key': ('telegram', 1), 'api_profile': ('api', 0),
                          'worker_control_socket': ('worker', 2)}[attack]
        compose['services'][service]['volumes'].append(binding.mounts(m, 'runtime-broker')[index])
    elif attack == 'writable':
        broker['volumes'][-2]['read_only'] = False
    elif attack in {'host_path', 'host_pin', 'unknown_flag'}:
        k = {'host_path': 'F1_PLANNING_HOST_FILE', 'host_pin': 'F1_PLANNING_HOST_SHA256',
             'unknown_flag': 'F1_PLANNING_ENABLED'}[attack]
        broker['environment'][k] = 'unreviewed'
    elif attack == 'network':
        broker['networks']['access'] = None
    else:
        del m['planning']
    with pytest.raises(ValueError):
        validate_profile(compose, m)


def runtime_metadata(m, compose, service):
    return {'Mounts': [{'Source': v['source'], 'Destination': v['target'], 'RW': not v['read_only']}
                       for v in binding.mounts(m, service)],
            'Config': {'Env': [k + '=' + v for k, v in binding.environment(m, service).items()]},
            'NetworkSettings': {'Networks': {'acc-f23_' + k: {} for k in compose['services'][service]['networks']}}}


@pytest.mark.parametrize('service', ['api', 'worker', 'telegram', 'runtime-broker', 'watchdog'])
@pytest.mark.parametrize('attack', [None, 'key_alias', 'parent_alias', 'env', 'network'])
def test_postcheck_measures_actual_scope(planning_release, service, attack):
    m, compose, _, _ = planning_release
    metadata = runtime_metadata(m, compose, service)
    if attack in {'key_alias', 'parent_alias'}:
        path = Path(m['planning']['key_directory'])
        metadata['Mounts'].append({'Source': str(path if attack == 'key_alias' else path.parent),
                                   'Destination': '/leaked', 'RW': False})
    elif attack == 'env':
        metadata['Config']['Env'].append('F1_PLANNING_EXTRA=1')
    elif attack == 'network':
        metadata['NetworkSettings']['Networks']['unreviewed'] = {}
    if attack:
        with pytest.raises(ValueError):
            binding.check_runtime(m, service, metadata, compose['services'][service])
    else:
        binding.check_runtime(m, service, metadata, compose['services'][service])


def test_deployment_preflight_checks_binding_before_any_compose(planning_release, monkeypatch, tmp_path):
    m, compose, _, _ = planning_release
    class Engine:
        def preflight(self):
            pass
    operator = Deployment({'manifest': m, 'compose': compose}, tmp_path, Engine(), Engine())
    monkeypatch.setattr('command_center.deployment.source_check', lambda m: None)
    monkeypatch.setattr(operator, 'compose', lambda *a: pytest.fail('compose before binding rejection'))
    Path(m['planning']['profile_directory'], 'profile.json').chmod(0o644)
    with pytest.raises((ValueError, Denied)):
        operator.preflight()


def test_deployment_postcheck_checks_binding_before_any_container_access(planning_release, tmp_path):
    m, compose, _, _ = planning_release
    Path(m['planning']['key_directory'], 'unexpected').touch()
    operator = Deployment({'manifest': m, 'compose': compose}, tmp_path, object(), object())
    with pytest.raises(ValueError):
        operator.postcheck()


@pytest.mark.parametrize('field,value', [('attestation_endpoint', 'unix:///run/user/1001/docker.sock'),
    ('endpoint', 'unix:///run/user/1000/docker.sock'), ('ledger_path', '/other/ledger.sqlite'),
    ('container_name', 'acc-f1-runtime-broker-1'), ('source_revision', 'f' * 40),
    ('image_id', 'sha256:' + 'f' * 64)])
def test_resealing_cannot_change_fixed_host_scope(planning_release, field, value):
    m, _, profile, host = planning_release
    directory = Path(m['planning']['profile_directory'])
    host = HostDeclaration.model_validate({**host.model_dump(), field: value})
    data = profile.model_dump()
    data['runtime']['binding_digest'] = digest(host.model_dump())
    (directory / 'profile.json').write_text(json.dumps(data))
    (directory / 'host.json').write_text(host.model_dump_json())
    with pytest.raises(ValueError, match='planning_source_image_host_binding_invalid'):
        binding.prepare_binding(m, directory, m['planning']['key_directory'])


@pytest.mark.parametrize('name', ['profile', 'host'])
def test_duplicate_json_fields_rejected_before_binding(planning_release, name):
    m, _, _, _ = planning_release
    directory = Path(m['planning']['profile_directory'])
    path = directory / (name + '.json')
    field = 'source_revision' if name == 'host' else 'schema_version'
    path.write_bytes(path.read_bytes()[:-1] + (',"' + field + '":1}').encode())
    with pytest.raises(ValueError):
        binding.prepare_binding(m, directory, m['planning']['key_directory'])


@pytest.mark.parametrize('options', [{'planning_profile_directory': '/private/profile'},
    {'planning_key_directory': '/private/key'},
    {'planning_profile_directory': '/private/profile', 'planning_key_directory': '/private/key',
     'first_experiment_config': '/private/other'}])
def test_partial_or_mixed_prepare_rejected_before_docker(monkeypatch, options):
    from command_center.deployment import prepare
    monkeypatch.setattr('command_center.deployment.Engine', lambda *a: pytest.fail('Docker before validation'))
    with pytest.raises(ValueError):
        prepare('/unused', '/unused/new', 1000, 1001, '/unused/state', **options)


@pytest.mark.parametrize('attack', [None, 'telegram_key', 'broker_network', 'worker_environment'])
def test_deployment_postcheck_runs_installed_checks(planning_release, tmp_path, monkeypatch, attack):
    m, compose, _, _ = planning_release
    calls = []
    class Engine:
        def json(self, *args):
            service = args[1].removeprefix('acc-f23-').removesuffix('-1')
            metadata = runtime_metadata(m, compose, service)
            metadata['State'] = {'Running': True}
            if attack == 'telegram_key' and service == 'telegram':
                metadata['Mounts'].append({'Source': m['planning']['key_directory'], 'Destination': '/leaked', 'RW': False})
            elif attack == 'broker_network' and service == 'runtime-broker':
                metadata['NetworkSettings']['Networks']['unexpected'] = {}
            elif attack == 'worker_environment' and service == 'worker':
                metadata['Config']['Env'].append('F1_PLANNING_ENABLED=1')
            return [metadata]
        def run(self, *args):
            calls.append(args)
            return b''  # Explicit fake exec; actual factory attestation tested separately.
    engine = Engine()
    operator = Deployment({'manifest': m, 'compose': compose}, tmp_path, engine, engine)
    monkeypatch.setattr(operator, 'tool', lambda code: b'')  # No DB/Redis in this offline policy test.
    if attack:
        with pytest.raises(ValueError):
            operator.postcheck()
    else:
        assert not operator.postcheck()['go_live']
        assert any(c[1] == 'acc-f23-telegram-1' and 'profile' in c[-1] for c in calls)
        assert any(c[1] == 'acc-f23-runtime-broker-1' and 'h.preflight' in c[-1] for c in calls)


def test_backup_preflight_remains_independent_of_planning_expiry(planning_release, tmp_path, monkeypatch):
    m, compose, _, _ = planning_release
    class Engine:
        def preflight(self):
            pass
    operator = Deployment({'manifest': m, 'compose': compose}, tmp_path, Engine(), Engine())
    monkeypatch.setattr('command_center.deployment.source_check', lambda m: None)
    monkeypatch.setattr('command_center.deployment.image_check', lambda *a: None)
    monkeypatch.setattr('command_center.telegram_release.preflight', lambda m: None)
    monkeypatch.setattr(operator, 'compose', lambda *a: b'')
    monkeypatch.setattr(binding.time, 'time', lambda: 2**40)
    with pytest.raises(ValueError, match='planning_operator_evidence_expired'):
        operator.preflight()
    operator.preflight(planning_check=False)


@pytest.mark.parametrize('name', ['profile', 'host'])
def test_invalid_operator_documents_do_not_echo_input(planning_release, name):
    m, _, _, _ = planning_release
    directory = Path(m['planning']['profile_directory'])
    path = directory / (name + '.json')
    data = json.loads(path.read_bytes())
    marker = 'PUBLIC_MARKER_MUST_NOT_APPEAR_IN_ERROR'
    data['credential'] = marker
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='planning_private_documents_invalid') as error:
        binding.prepare_binding(m, directory, m['planning']['key_directory'])
    assert marker not in str(error.value)
