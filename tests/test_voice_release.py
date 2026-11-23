from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from command_center import voice_candidate as candidate
from command_center.deployment_profile import atomic_json, checksum, render, validate_profile
from command_center.deployment_voice import check_binding, check_runtime, heartbeat_check_code
from command_center.offline_speech import MODEL_FILES
from command_center.store import Denied, digest
from command_center.telegram_transport import TelegramConnection
from command_center.voice_profile import VoiceProfile
from test_deployment import release as release


@pytest.fixture
def voice_release(release, tmp_path, monkeypatch):
    base, _ = release
    old = deepcopy(base)
    active = TelegramConnection(mode='live', owner_id=1234567, bot_id=123456789,
        source_revision=old['manifest']['revision'], token_file='/run/telegram/token')
    old['manifest']['telegram'] = {'mode': 'live', 'owner_id': active.owner_id,
        'bot_id': active.bot_id, 'connection_digest': digest(active.model_dump())}
    old['compose'] = render(base['compose'], old['manifest'])
    plain = deepcopy(base)
    plain['manifest']['revision'] = 'c' * 40
    plain['compose'] = render(base['compose'], plain['manifest'])
    root = Path(old['manifest']['data_root'])
    directory = root / 'voice'
    directory.mkdir(mode=0o700)
    model = directory / 'model'
    model.mkdir(mode=0o700)
    manifest = {}
    for name in MODEL_FILES:
        (model / name).write_bytes(name.encode())
        manifest[name] = sha256(name.encode()).hexdigest()
    private = directory / 'profile'
    private.mkdir(mode=0o700)
    staged = active.model_copy(update={'source_revision': plain['manifest']['revision']})
    profile = VoiceProfile(enabled=True, connection_file='/run/telegram/connection.json',
        connection_digest=digest(staged.model_dump()), source_revision=plain['manifest']['revision'],
        model_directory='/models/whisper-base', model_manifest=manifest,
        since=datetime.now(timezone.utc).isoformat())
    atomic_json(private / 'profile.json', profile.model_dump())
    voice = {'image': 'sha256:' + '9' * 64, 'profile_directory': str(private),
        'profile_digest': digest(profile.model_dump()), 'model_directory': str(model), 'model_manifest': manifest}
    calls = []

    class Engine:
        def __init__(self, uid):
            self.uid = uid

        def preflight(self):
            calls.append(('engine', self.uid))

    monkeypatch.setattr(candidate, 'Engine', Engine)
    monkeypatch.setattr(candidate, 'source_check', lambda m: calls.append(('source', m['revision'])))
    monkeypatch.setattr(candidate, 'image_check', lambda e, images, revision: calls.append(('images', images)))
    directories = []
    for name, bundle in (('previous', old), ('plain', plain)):
        path = tmp_path / name
        path.mkdir(mode=0o700)
        atomic_json(path / 'bundle.json', bundle)
        atomic_json(path / 'compose.json', bundle['compose'])
        directories.append(path)
    (root / 'telegram').mkdir(mode=0o700)
    atomic_json(root / 'telegram/connection.json', active.model_dump())
    atomic_json(root / 'deployment.json', {'phase': 'VERIFIED', 'bundle': checksum(old),
        'revision': old['manifest']['revision'], 'directory': str(directories[0])})
    atomic_json(directories[0] / 'activation.json', {'phase': 'VERIFIED', 'target': checksum(old)})
    args = {'previous_directory': directories[0], 'plain_directory': directories[1],
        'output': tmp_path / 'candidate', 'voice': voice, 'previous_pin': checksum(old), 'plain_pin': checksum(plain)}
    return args, old, plain, active, calls


def test_prepare_inspect_does_not_modify_live_binding_or_start_anything(voice_release, monkeypatch):
    args, old, _, _, calls = voice_release
    root = Path(old['manifest']['data_root'])
    before = {p: p.read_bytes() for p in (root / 'deployment.json', root / 'telegram/connection.json')}
    monkeypatch.setattr('httpx.Client', lambda *a, **k: pytest.fail('no network in preparation'))
    value = candidate.prepare(**args)
    candidate.inspect(args['output'], value['candidate_bundle'], value['preparation_digest'])
    target = candidate.load_bundle(args['output'])
    assert check_binding(target['manifest']).enabled is True
    assert set(target['compose']['services']) - set(old['compose']['services']) == {'voice'}
    assert all(p.read_bytes() == content for p, content in before.items())
    assert any('voice' in c[1] for c in calls if c[0] == 'images')
    assert not (args['output'] / 'activation.json').exists()
    compile(heartbeat_check_code(target['manifest']), '<voice-heartbeat-postcheck>', 'exec')


@pytest.mark.parametrize('attack', ['socket', 'memory', 'restart', 'network', 'credential', 'mutable'])
def test_voice_service_cannot_gain_authority_or_escape_resource_limits(voice_release, attack):
    args, old, plain, active, _ = voice_release
    target, _ = candidate.assemble(old, plain, active, args['voice'], args['previous_pin'], args['plain_pin'])
    profile = deepcopy(target['compose'])
    service = profile['services']['voice']
    if attack == 'socket':
        service['volumes'].append({'type': 'bind', 'source': '/run/docker.sock', 'target': '/var/run/docker.sock'})
    elif attack == 'memory':
        service['mem_limit'] = '8g'
    elif attack == 'restart':
        service['restart'] = 'always'
    elif attack == 'network':
        service['network_mode'] = 'host'
    elif attack == 'credential':
        service['secrets'].append('broker_token')
    else:
        service['volumes'][-1]['read_only'] = False
    with pytest.raises(ValueError):
        validate_profile(profile, target['manifest'])


@pytest.mark.parametrize('attack', ['profile', 'model', 'inventory', 'mode', 'activation', 'previous'])
def test_mutated_preparation_is_not_activatable(voice_release, attack):
    args, _, _, _, _ = voice_release
    value = candidate.prepare(**args)
    output = args['output']
    if attack == 'profile':
        path = Path(args['voice']['profile_directory']) / 'profile.json'
        doc = candidate.read_json(path)
        doc['enabled'] = False
        atomic_json(path, doc)
    elif attack == 'model':
        (Path(args['voice']['model_directory']) / 'model.bin').write_bytes(b'changed')
    elif attack == 'inventory':
        atomic_json(output / 'unexpected.json', {})
    elif attack == 'mode':
        (output / 'bundle.json').chmod(0o644)
    elif attack == 'activation':
        atomic_json(output / 'activation.json', {'purpose': 'not-voice', 'phase': 'VERIFIED'})
    else:
        atomic_json(output / 'connection.previous.json', {})
    with pytest.raises((ValueError, Denied)):
        candidate.inspect(output, value['candidate_bundle'], value['preparation_digest'])


def runtime_metadata(m):
    from command_center.deployment_voice import service
    expected = service(m)
    return {'Image': m['voice']['image'], 'State': {'Running': True},
        'Config': {'User': '0:0', 'Entrypoint': expected['entrypoint'], 'Cmd': expected['command'],
                   'Env': [k + '=' + str(v) for k, v in expected['environment'].items()]},
        'HostConfig': {'ReadonlyRootfs': True, 'CapDrop': ['ALL'], 'Memory': 1024**3,
                       'NanoCpus': 10**9, 'PidsLimit': 64, 'SecurityOpt': ['no-new-privileges'], 'IpcMode': 'private',
                       'RestartPolicy': {'Name': 'no'}},
        'NetworkSettings': {'Networks': {'acc-f23_control': {}, 'acc-f23_telegram-access': {}}},
        'Mounts': [{'Source': v['source'], 'Destination': v['target'], 'RW': False} for v in expected['volumes']]
            + [{'Source': str(Path(m['data_root']) / 'secrets/db_password'),
                'Destination': '/run/secrets/db_password', 'RW': False}]}


@pytest.mark.parametrize('attack', [None, 'extra_secret', 'env', 'proxy', 'cpu', 'image', 'host_pid'])
def test_runtime_postcheck_checks_actual_container_not_only_compose(voice_release, attack):
    args, old, plain, active, _ = voice_release
    target, _ = candidate.assemble(old, plain, active, args['voice'], args['previous_pin'], args['plain_pin'])
    metadata = runtime_metadata(target['manifest'])
    if attack == 'extra_secret':
        metadata['Mounts'].append({'Source': '/state/key', 'Destination': '/key', 'RW': False})
    elif attack == 'env':
        metadata['Config']['Env'].append('F2_INTEGRATION_CONFIG_FILE=/config')
    elif attack == 'proxy':
        metadata['Config']['Env'].append('HTTPS_PROXY=http://outside.example/')
    elif attack == 'cpu':
        metadata['HostConfig']['NanoCpus'] *= 2
    elif attack == 'image':
        metadata['Image'] = 'sha256:' + '0' * 64
    elif attack == 'host_pid':
        metadata['HostConfig']['PidMode'] = 'host'
    if attack is None:
        check_runtime(target['manifest'], metadata)
    else:
        with pytest.raises(ValueError):
            check_runtime(target['manifest'], metadata)


@pytest.mark.parametrize('attack', ['symlink', 'hardlink'])
def test_model_custody_cannot_escape_the_reviewed_artifact(voice_release, attack):
    args, old, plain, active, _ = voice_release
    target, _ = candidate.assemble(old, plain, active, args['voice'], args['previous_pin'], args['plain_pin'])
    model = Path(args['voice']['model_directory'])
    if attack == 'symlink':
        alias = model.with_name('model-alias')
        alias.symlink_to(model, target_is_directory=True)
        target['manifest']['voice']['model_directory'] = str(alias)
    else:
        model.with_name('outside-model-link').hardlink_to(model / 'model.bin')
    with pytest.raises(ValueError, match='custody'):
        check_binding(target['manifest'])


def test_private_profile_preparation_never_replaces_existing_file(voice_release):
    args, _, _, _, _ = voice_release
    output = str(Path(args['voice']['profile_directory']).with_name('new-profile'))
    options = {'previous_directory': args['previous_directory'], 'plain_directory': args['plain_directory'],
        'profile_directory': output, 'model_directory': args['voice']['model_directory'],
        'image': args['voice']['image'], 'since': datetime.now(timezone.utc).isoformat(),
        'model_manifest': args['voice']['model_manifest']}
    result = candidate.prepare_profile(**options)
    assert result['status'] == 'VOICE_PROFILE_PREPARED_NOT_ACTIVATED'
    content = (Path(output) / 'profile.json').read_bytes()
    with pytest.raises(ValueError):
        candidate.prepare_profile(**options)
    assert (Path(output) / 'profile.json').read_bytes() == content


def test_operator_composes_existing_interlocks_and_checks_fresh_paused_worker(voice_release, monkeypatch):
    import ast
    import importlib.util
    import sys
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'infra/vps'))
    try:
        spec = importlib.util.spec_from_file_location('voice_operator', root / 'infra/vps/activate_voice_candidate.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    args, old, _, _, _ = voice_release
    value = candidate.prepare(**args)
    target = candidate.load_bundle(args['output'])
    scope = module.VoiceScope(args['previous_pin'], value['candidate_bundle'], value['preparation_digest'],
                              value['voice_capability'])
    receipt = candidate.read_json(args['output'] / 'preparation.json')
    assert scope.validate(old, target, args['output'], receipt)['purpose'] == candidate.PURPOSE
    calls = []
    monkeypatch.setattr(module, 'apply_transition', lambda *a, **k: calls.append(k) or {})
    module.activate(args['previous_directory'], args['output'], args['previous_pin'], value['candidate_bundle'],
                    value['preparation_digest'], value['voice_capability'], 123)
    assert isinstance(calls[0]['_planning'], module.VoiceScope)
    monkeypatch.setattr(module.PlanningUpdate, 'postcheck', lambda _: {'planning_runtime_ready': True})
    controller = object.__new__(module.VoiceUpdate)
    controller.m = target['manifest']
    controller.tool = lambda code: calls.append(code)
    assert controller.postcheck()['offline_voice_runtime_ready'] is True
    code = calls[-1]
    compile(code, '<voice-postcheck>', 'exec')
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'exec':
            compile(ast.literal_eval(node.args[0]), '<nested-voice-postcheck>', 'exec')
