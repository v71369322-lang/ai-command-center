from copy import deepcopy
from pathlib import Path

import pytest

from command_center import assistant_candidate as candidate
from command_center.deployment_profile import atomic_json, checksum, render
from command_center.store import Denied, digest
from command_center.voice_profile import VoiceProfile
from test_deployment import release as release
from test_voice_release import voice_release as voice_release
from test_voice_release import runtime_metadata
from command_center.speech_models import GIGAAM_MANIFEST, model_target


@pytest.fixture
def assistant_release(voice_release, monkeypatch):
    args, old, plain, active, calls = voice_release
    # Preserve an already-installed voice capability, including its admission cutoff.
    current_profile = VoiceProfile.model_validate(candidate.read_json(Path(args['voice']['profile_directory']) / 'profile.json'))
    old_profile = current_profile.model_copy(update={'source_revision': old['manifest']['revision'],
                                                   'connection_digest': digest(active.model_dump())})
    old_directory = Path(old['manifest']['data_root']) / 'voice/old-profile'
    old_directory.mkdir(mode=0o700)
    atomic_json(old_directory / 'profile.json', old_profile.model_dump())
    old['manifest']['voice'] = {**args['voice'], 'profile_directory': str(old_directory),
                               'profile_digest': digest(old_profile.model_dump())}
    base = deepcopy(plain['compose'])
    old['compose'] = render(base, old['manifest'])
    plain['manifest']['assistant_only'] = True
    plain['manifest']['images'] = {'api': plain['manifest']['images']['api']}
    plain['compose'] = render(base, plain['manifest'])
    args['previous_pin'], args['plain_pin'] = checksum(old), checksum(plain)
    for key, bundle in [('previous_directory', old), ('plain_directory', plain)]:
        atomic_json(args[key] / 'bundle.json', bundle)
        atomic_json(args[key] / 'compose.json', bundle['compose'])
    root = Path(old['manifest']['data_root'])
    atomic_json(root / 'deployment.json', {'phase': 'VERIFIED', 'bundle': checksum(old),
        'revision': old['manifest']['revision'], 'directory': str(args['previous_directory'])})
    atomic_json(args['previous_directory'] / 'activation.json', {'phase': 'VERIFIED', 'target': checksum(old)})
    class Engine:
        def __init__(self, uid):
            self.uid = uid
        def preflight(self):
            calls.append(('assistant_engine', self.uid))
    monkeypatch.setattr(candidate, 'Engine', Engine)
    monkeypatch.setattr(candidate, 'source_check', lambda m: calls.append(('source', m['revision'])))
    monkeypatch.setattr(candidate, 'image_check', lambda e, images, revision: calls.append(('assistant_images', images)))
    return args, old, plain, active, calls


def test_preserves_voice_and_owner_without_execution_daemon(assistant_release):
    args, old, _, _, calls = assistant_release
    root = Path(old['manifest']['data_root'])
    before = {p: p.read_bytes() for p in (root / 'deployment.json', root / 'telegram/connection.json')}
    result = candidate.prepare(**args)
    candidate.inspect(args['output'], result['candidate_bundle'], result['preparation_digest'])
    target = candidate.load_bundle(args['output'])
    assert set(target['compose']['services']) == {'api', 'db', 'redis', 'telegram', 'voice'}
    assert all(target['compose']['services'][s]['environment']['F1_ASSISTANT_ONLY'] == '1'
               for s in ('api', 'telegram', 'voice'))
    assert all(p.read_bytes() == content for p, content in before.items())
    assert not (args['output'] / 'activation.json').exists()
    assert all(c[1] == old['manifest']['control_uid'] for c in calls if c[0] == 'assistant_engine')
    assert all(set(c[1]) == {'api', 'voice'} for c in calls if c[0] == 'assistant_images')


def test_exact_gigaam_model_change_keeps_every_other_profile_permission(assistant_release):
    args, old, plain, active, _ = assistant_release
    before = VoiceProfile.model_validate(candidate.read_json(Path(old['manifest']['voice']['profile_directory'])
                                                            / 'profile.json'))
    after = before.model_copy(update={'source_revision': plain['manifest']['revision'],
        'connection_digest': digest(active.model_copy(update={'source_revision': plain['manifest']['revision']}).model_dump()),
        'model_manifest': GIGAAM_MANIFEST, 'model_directory': model_target(GIGAAM_MANIFEST)})
    candidate.check_voice_transition(before, after, after.source_revision, after.connection_digest)
    with pytest.raises(ValueError, match='permissions_changed'):
        candidate.check_voice_transition(before, after.model_copy(update={'since': '2030-01-01T00:00:00+00:00'}),
                                         after.source_revision, after.connection_digest)


def test_gigaam_prepare_inspect_pins_new_files_and_preserves_resource_limits(assistant_release, monkeypatch):
    from hashlib import sha256
    from command_center import speech_models
    args, old, _, _, _ = assistant_release
    root = Path(old['manifest']['data_root'])
    model = root / 'voice/gigaam-synthetic-snapshot'
    model.mkdir(mode=0o700)
    manifest = {}
    for name in GIGAAM_MANIFEST:
        data = name.encode()
        (model / name).write_bytes(data)
        manifest[name] = sha256(data).hexdigest()
    # Synthetic file integrity/interlock test, not real model inference.
    monkeypatch.setattr(candidate, 'GIGAAM_MANIFEST', manifest)
    monkeypatch.setattr(speech_models, 'GIGAAM_MANIFEST', manifest)
    result = candidate.prepare_profile(args['previous_directory'], args['plain_directory'],
        root / 'voice/gigaam-profile', args['voice']['image'], model_directory=model, model_manifest=manifest)
    result = candidate.prepare(**{**args, 'voice': result['voice']})
    candidate.inspect(args['output'], result['candidate_bundle'], result['preparation_digest'])
    target = candidate.load_bundle(args['output'])
    service = target['compose']['services']['voice']
    assert service['mem_limit'] == '1g' and service['cpus'] == 1
    assert service['volumes'][-1]['target'] == '/models/gigaam-v3'
    assert service['volumes'][-1]['read_only'] is True
    (model / 'v3_e2e_ctc.int8.onnx').write_bytes(b'tampered')
    with pytest.raises(Denied, match='binding_changed'):
        candidate.inspect(args['output'], result['candidate_bundle'], result['preparation_digest'])


@pytest.mark.parametrize('attack', [None, 'image', 'socket', 'provider', 'writable', 'flag', 'host_pid'])
def test_actual_assistant_runtime_rejects_added_authority(assistant_release, attack):
    from command_center.assistant_runtime import check_runtime
    args, old, plain, active, _ = assistant_release
    target, _ = candidate.assemble(old, plain, active, args['voice'], args['previous_pin'], args['plain_pin'])
    metadata = runtime_metadata(target['manifest'])
    if attack == 'image':
        metadata['Image'] = 'sha256:' + '0' * 64
    elif attack == 'socket':
        metadata['Mounts'].append({'Source': '/run/docker.sock', 'Destination': '/socket', 'RW': False})
    elif attack == 'provider':
        metadata['Config']['Env'].append('OPENAI_API_KEY=PUBLIC_FIXTURE_ONLY')
    elif attack == 'writable':
        metadata['Mounts'][0]['RW'] = True
    elif attack == 'flag':
        metadata['Config']['Env'] = [e for e in metadata['Config']['Env'] if not e.startswith('F1_ASSISTANT_ONLY=')]
    elif attack == 'host_pid':
        metadata['HostConfig']['PidMode'] = 'host'
    service = target['compose']['services']['voice']
    if attack:
        with pytest.raises(ValueError):
            check_runtime(target['manifest'], 'voice', metadata, service)
    else:
        check_runtime(target['manifest'], 'voice', metadata, service)


@pytest.mark.parametrize('attack', ['cutoff', 'model', 'profile', 'owner', 'mode', 'migration', 'paid', 'inventory', 'activation'])
def test_changed_scope_or_preparation_is_rejected(assistant_release, attack):
    args, old, plain, _, _ = assistant_release
    if attack in {'owner', 'mode', 'migration', 'paid'}:
        if attack == 'owner':
            old['manifest']['telegram']['owner_id'] += 1
        elif attack == 'mode':
            plain['manifest'].pop('assistant_only')
        elif attack == 'migration':
            plain['manifest']['migration_hash'] = '0' * 64
        else:
            plain['manifest']['first_experiment'] = {}
        for key, bundle in [('previous_directory', old), ('plain_directory', plain)]:
            atomic_json(args[key] / 'bundle.json', bundle)
            atomic_json(args[key] / 'compose.json', bundle['compose'])
        with pytest.raises(ValueError):
            candidate.prepare(**args)
        return
    if attack == 'cutoff':
        path = Path(args['voice']['profile_directory']) / 'profile.json'
        doc = candidate.read_json(path)
        doc['since'] = '2030-01-01T00:00:00+00:00'
        atomic_json(path, doc)
        args['voice']['profile_digest'] = digest(VoiceProfile.model_validate(doc).model_dump())
        with pytest.raises(ValueError, match='voice_permissions_changed'):
            candidate.prepare(**args)
        return
    result = candidate.prepare(**args)
    if attack == 'model':
        (Path(args['voice']['model_directory']) / 'model.bin').write_bytes(b'changed')
    elif attack == 'profile':
        path = Path(args['voice']['profile_directory']) / 'profile.json'
        doc = candidate.read_json(path)
        doc['enabled'] = False
        atomic_json(path, doc)
    elif attack == 'inventory':
        atomic_json(args['output'] / 'extra.json', {})
    else:
        atomic_json(args['output'] / 'activation.json', {'phase': 'VERIFIED', 'purpose': 'other'})
    with pytest.raises((ValueError, Denied)):
        candidate.inspect(args['output'], result['candidate_bundle'], result['preparation_digest'])


def test_operator_preserves_existing_transaction_without_broker_postcheck(assistant_release, monkeypatch):
    import importlib.util
    import sys
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / 'infra/vps'))
    spec = importlib.util.spec_from_file_location('assistant_operator', root / 'infra/vps/activate_assistant_candidate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    args, old, _, _, _ = assistant_release
    result = candidate.prepare(**args)
    target = candidate.load_bundle(args['output'])
    # Bind the preparation checks to this test's fake engines only.
    monkeypatch.setattr(module, 'inspect', candidate.inspect)
    scope = module.AssistantScope(args['previous_pin'], result['candidate_bundle'], result['preparation_digest'])
    receipt = candidate.read_json(args['output'] / 'preparation.json')
    assert scope.validate(old, target, args['output'], receipt)['purpose'] == candidate.PURPOSE
    calls = []
    monkeypatch.setattr(module, 'apply_transition', lambda *a, **k: calls.append(k) or {})
    module.activate(args['previous_directory'], args['output'], args['previous_pin'], result['candidate_bundle'],
                    result['preparation_digest'], 123)
    assert isinstance(calls[0]['_planning'], module.AssistantScope)
    monkeypatch.setattr(module.ReconciledUpdate, 'postcheck', lambda _: {})
    controller = object.__new__(module.AssistantUpdate)
    controller.m = target['manifest']
    controller.tool = lambda code: calls.append(code)
    assert controller.postcheck()['developer_services_stopped'] is True
    assert all('acc-f23-runtime-broker-1' not in code for code in calls if isinstance(code, str))
    for code in calls:
        if isinstance(code, str):
            compile(code, '<assistant-postcheck>', 'exec')
    # This scope cannot be silently used by the generic Telegram memory updater.
    apply_module = sys.modules['apply_reconciled_telegram_candidate']
    with pytest.raises(ValueError, match='separate_assistant_transition_approval_required'):
        apply_module.validate_transition(old, target, checksum(old), checksum(target))
