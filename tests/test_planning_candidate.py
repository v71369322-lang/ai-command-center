"""Candidate preparation is non-activating; only synthetic files/daemons are used."""
from copy import deepcopy
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from command_center import planning_candidate as candidate
from command_center.deployment_profile import atomic_json, checksum, render
from command_center.planning_admission import PlanningProfile
from command_center.planning_host import BROKER_COMMAND
from command_center.store import Denied, digest
from command_center.telegram_transport import TelegramConnection
from test_deployment import release as release
from test_planning_admission import profile as profile


@pytest.fixture
def inputs(release, profile, tmp_path, monkeypatch):
    original, _ = release
    base = deepcopy(original)
    base['manifest'].update(control_uid=os.getuid(), execution_uid=os.getuid() + 1)
    base['compose'] = render(original['compose'], base['manifest'])
    active = TelegramConnection(mode='live', owner_id=1234567, bot_id=123456789,
        source_revision=base['manifest']['revision'], token_file='/run/telegram/token')
    previous = deepcopy(base)
    previous['manifest']['telegram'] = {'mode': active.mode, 'owner_id': active.owner_id,
        'bot_id': active.bot_id, 'connection_digest': digest(active.model_dump())}
    previous['compose'] = render(base['compose'], previous['manifest'])
    disabled = deepcopy(base)
    disabled['manifest']['revision'] = 'c' * 40
    disabled['compose'] = render(base['compose'], disabled['manifest'])
    directories = []
    for name, bundle in (('previous', previous), ('disabled', disabled)):
        directory = tmp_path / name
        directory.mkdir(mode=0o700)
        atomic_json(directory / 'bundle.json', bundle)
        atomic_json(directory / 'compose.json', bundle['compose'])
        directories.append(directory)
    root = Path(base['manifest']['data_root'])
    (root / 'telegram').mkdir(mode=0o700)
    atomic_json(root / 'telegram/connection.json', active.model_dump())
    atomic_json(root / 'deployment.json', {'phase': 'VERIFIED', 'bundle': checksum(previous),
        'revision': previous['manifest']['revision'], 'directory': str(directories[0])})
    atomic_json(directories[0] / 'activation.json', {'phase': 'VERIFIED', 'target': checksum(previous)})
    directory = tmp_path / 'operator'
    directory.mkdir(mode=0o700)
    operator = PlanningProfile.model_validate({**profile.model_dump(), 'evidence': {
        **profile.evidence.model_dump(), 'observed_at': int(time.time()) - 10, 'expires_at': int(time.time()) + 900}})
    atomic_json(directory / 'operator.json', operator.model_dump())
    keys = tmp_path / 'private-key'
    keys.mkdir(mode=0o700)
    key = keys / 'openai.key'
    key.write_bytes(b'PUBLIC_CANDIDATE_FIXTURE_CREDENTIAL_12345')
    key.chmod(0o600)
    image = {'Id': disabled['manifest']['images']['broker'], 'Config': {
        'Labels': {'org.opencontainers.image.revision': disabled['manifest']['revision']},
        'WorkingDir': '/app', 'Cmd': BROKER_COMMAND, 'Entrypoint': None,
        'Env': ['PATH=/usr/local/bin:/usr/bin:/bin', 'PYTHONPATH=/app/src']}}
    calls, changed = [], []
    class Engine:
        def __init__(self, uid):
            self.uid = uid
        def preflight(self):
            calls.append(('preflight', self.uid))
        def json(self, *args):
            calls.append(args)
            assert args[:2] == ('image', 'inspect')
            if changed:
                changed[0]()
            return [{**image, 'Id': args[2]}]
    monkeypatch.setattr(candidate, 'Engine', Engine)
    monkeypatch.setattr(candidate, 'source_check', lambda m: calls.append(('source_check', m['revision'])))
    options = dict(previous_directory=directories[0], disabled_directory=directories[1], output=tmp_path / 'candidate',
        operator_file=directory / 'operator.json', operator_pin=candidate.raw_pin(operator.model_dump()),
        key_directory=keys, credential_sha256=hashlib.sha256(key.read_bytes()).hexdigest(),
        previous_pin=checksum(previous), disabled_pin=checksum(disabled))
    return options, previous, disabled, active, operator, image, calls, changed


def invoke(inputs):
    return candidate.prepare(**inputs[0])


def test_prepare_and_inspect_preserve_live_state_and_do_not_read_credentials(inputs, monkeypatch):
    options, previous, disabled, active, operator, image, calls, _ = inputs
    key = options['key_directory'] / 'openai.key'
    root = Path(previous['manifest']['data_root'])
    watched = [root / 'deployment.json', root / 'telegram/connection.json',
               options['previous_directory'] / 'activation.json', key]
    before = {p: (p.stat().st_ino, p.stat().st_size, p.stat().st_mtime_ns) for p in watched}
    real_open, real_fdopen = io.open, os.fdopen
    def open_file(path, *a, **k):
        assert (Path(f'/proc/self/fd/{path}').resolve() if isinstance(path, int) else Path(path)) != key
        return real_open(path, *a, **k)
    def fdopen(fd, *a, **k):
        assert Path(f'/proc/self/fd/{fd}').resolve() != key
        return real_fdopen(fd, *a, **k)
    monkeypatch.setattr(io, 'open', open_file)
    monkeypatch.setattr(os, 'fdopen', fdopen)
    monkeypatch.setattr('httpx.Client', lambda *a, **k: pytest.fail('HTTP in candidate preparation'))
    monkeypatch.setattr('command_center.store.Store.__init__', lambda *a, **k: pytest.fail('DB in candidate preparation'))
    result = invoke(inputs)
    inspected = candidate.inspect(options['output'], result['candidate_bundle'], result['preparation_digest'])
    assert inspected['status'] == 'PLANNING_CANDIDATE_INTEGRITY_VERIFIED_NOT_ACTIVATED'
    assert not inspected['deployment_authorized'] and inspected['paid_calls'] == 0
    assert before == {p: (p.stat().st_ino, p.stat().st_size, p.stat().st_mtime_ns) for p in watched}
    assert all(c[0] in {'preflight', 'source_check', 'image'} for c in calls)
    bundle = candidate.load_bundle(options['output'])
    profile, host = candidate.check_binding(bundle['manifest'])
    assert profile.runtime.binding_digest == digest(host.model_dump())
    assert profile.runtime.credential_sha256 == options['credential_sha256']
    metadata = candidate.read_json(options['output'] / 'broker.expected.json')
    assert host.metadata_digest == digest(metadata)
    assert profile.evidence == operator.evidence and profile.tariff == operator.tariff
    assert candidate.connection(options['output'] / 'connection.candidate.json').source_revision == disabled['manifest']['revision']
    assert candidate.connection(root / 'telegram/connection.json') == active
    assert all(p.stat().st_mode & 0o077 == 0 for p in options['output'].rglob('*'))
    with pytest.raises(ValueError, match='planning_new_private_candidate_directory_required'):
        invoke(inputs)


@pytest.mark.parametrize('attack', ['previous_pin', 'disabled_pin', 'operator_pin', 'credential_pin',
    'operator_expired', 'already_bound', 'deployment_intent', 'activation_attempted', 'changed_predecessor',
    'key_symlink', 'extra_key_file', 'output_state', 'image_source', 'image_command', 'image_python', 'changed_input'])
def test_preparation_fails_without_live_mutation(inputs, attack):
    options, previous, _, _, _, image, _, changed = inputs
    if attack in {'previous_pin', 'disabled_pin', 'operator_pin'}:
        options[attack] = 'f' * 64
    elif attack == 'credential_pin':
        options['credential_sha256'] = 'not-a-fingerprint'
    elif attack in {'operator_expired', 'already_bound'}:
        data = candidate.read_json(options['operator_file'])
        if attack == 'operator_expired':
            data['evidence'].update(observed_at=100, expires_at=200)
        else:
            data['runtime'] = {'source_revision': 'c' * 40, 'binding_digest': 'd' * 64, 'credential_sha256': 'e' * 64}
        atomic_json(options['operator_file'], data)
        options['operator_pin'] = candidate.raw_pin(data)
    elif attack == 'deployment_intent':
        atomic_json(Path(previous['manifest']['data_root']) / 'deployment.json', {'phase': 'INTENT'})
    elif attack == 'activation_attempted':
        atomic_json(options['previous_directory'] / 'activation.json', {'phase': 'DEPLOYMENT_ATTEMPTED'})
    elif attack == 'changed_predecessor':
        changed.append(lambda: atomic_json(Path(previous['manifest']['data_root']) / 'deployment.json', {'phase': 'INTENT'}))
    elif attack == 'key_symlink':
        key = options['key_directory'] / 'openai.key'
        key.unlink()
        key.symlink_to(options['operator_file'])
    elif attack == 'extra_key_file':
        (options['key_directory'] / 'unexpected').touch()
    elif attack == 'output_state':
        options['output'] = Path(previous['manifest']['data_root']) / 'candidate'
    elif attack == 'image_source':
        image['Config']['Labels']['org.opencontainers.image.revision'] = 'f' * 40
    elif attack == 'image_command':
        image['Config']['Cmd'] = ['sh']
    elif attack == 'image_python':
        image['Config']['Env'].append('LD_PRELOAD=/untrusted')
    else:
        changed.append(lambda: atomic_json(options['operator_file'], {'changed': True}))
    with pytest.raises((ValueError, Denied, OSError)):
        invoke(inputs)
    assert not options['output'].exists()


@pytest.mark.parametrize('attack', ['file', 'plan', 'pin', 'extra', 'hardlink', 'host', 'staged'])
def test_candidate_inspection_rejects_tampering(inputs, attack):
    options = inputs[0]
    result = invoke(inputs)
    directory = options['output']
    if attack in {'file', 'host', 'staged'}:
        path = directory / {'file': 'bundle.json', 'host': 'planning-profile/host.json',
                            'staged': 'connection.candidate.json'}[attack]
        path.write_bytes(path.read_bytes() + b' ')
    elif attack == 'plan':
        receipt = candidate.read_json(directory / 'preparation.json')
        receipt['review']['activation_authorized'] = True
        atomic_json(directory / 'preparation.json', receipt)
        result['preparation_digest'] = checksum(receipt)
    elif attack == 'pin':
        result['candidate_bundle'] = 'f' * 64
    elif attack == 'extra':
        (directory / 'unexpected').touch()
    else:
        (directory.parent / 'linked').hardlink_to(directory / 'bundle.json')
    with pytest.raises((ValueError, Denied, OSError)):
        candidate.inspect(directory, result['candidate_bundle'], result['preparation_digest'])


def test_interruption_never_writes_completion_marker(inputs, monkeypatch):
    real = candidate.atomic_json
    def interrupted(path, value):
        if path.name == 'preparation.json':
            raise OSError('synthetic interruption')
        real(path, value)
    monkeypatch.setattr(candidate, 'atomic_json', interrupted)
    with pytest.raises(OSError):
        invoke(inputs)
    with pytest.raises(OSError):
        candidate.inspect(inputs[0]['output'], 'a' * 64, 'b' * 64)


@pytest.mark.parametrize('mode', ['parse', 'inspect'])
def test_cli_never_echoes_argument_values(mode):
    marker = 'PUBLIC_ARGUMENT_MARKER_MUST_NOT_BE_ECHOED'
    script = Path(__file__).resolve().parents[1] / 'infra/vps/prepare_planning_candidate.py'
    args = ['inspect', '--unknown', marker] if mode == 'parse' else [
        'inspect', '--directory', '/' + marker, '--candidate-pin', 'a' * 64, '--preparation-pin', 'b' * 64]
    result = subprocess.run([sys.executable, str(script), *args], capture_output=True, check=False)
    assert result.returncode == (2 if mode == 'parse' else 1)
    assert marker.encode() not in result.stdout + result.stderr


@pytest.mark.parametrize('attack', ['entrypoint', 'secret_alias', 'interpreter', 'endpoint', 'memory'])
def test_disabled_bundle_cannot_reseal_unsafe_broker_policy(inputs, attack):
    options, _, disabled, *_ = inputs
    service = disabled['compose']['services']['runtime-broker']
    if attack == 'entrypoint':
        service['entrypoint'] = ['sh']
    elif attack == 'secret_alias':
        service['secrets'][0]['target'] = '/unreviewed'
    elif attack == 'interpreter':
        service['environment']['PYTHONPATH'] = '/untrusted'
    elif attack == 'endpoint':
        service['environment']['F1_RUNTIME_SOCKET'] = 'unix:///run/user/1001/docker.sock'
    else:
        service['mem_limit'] = '1g'
    atomic_json(options['disabled_directory'] / 'bundle.json', disabled)
    atomic_json(options['disabled_directory'] / 'compose.json', disabled['compose'])
    options['disabled_pin'] = checksum(disabled)
    with pytest.raises(ValueError):
        invoke(inputs)
    assert not options['output'].exists()
