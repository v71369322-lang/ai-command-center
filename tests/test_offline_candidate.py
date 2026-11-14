"""Restriction-only release preparation. Synthetic private files; no VPS/provider."""
import ast
from copy import deepcopy
import importlib.util
import io
from pathlib import Path
import sys

import pytest

from command_center import offline_candidate as offline, planning_candidate
from command_center.deployment_profile import atomic_json, checksum, render
from command_center.store import Denied
from test_deployment import release as release
from test_planning_admission import profile as profile
from test_planning_candidate import inputs as inputs


@pytest.fixture
def offline_inputs(inputs, tmp_path, monkeypatch):
    options, previous, disabled, active, profile, image, calls, _ = inputs
    old, _, _, live, _, _ = planning_candidate.assemble(previous, disabled, active, profile, image,
        options['output'], options['key_directory'], options['previous_pin'], options['disabled_pin'],
        options['credential_sha256'], now=profile.evidence.observed_at)
    target = deepcopy(disabled)
    target['manifest']['revision'] = 'd' * 40
    target['compose'] = render(disabled['compose'], target['manifest'])
    old_dir, disabled_dir = tmp_path / 'old-planning', tmp_path / 'new-disabled'
    for path, bundle in ((old_dir, old), (disabled_dir, target)):
        path.mkdir(mode=0o700)
        atomic_json(path / 'bundle.json', bundle)
        atomic_json(path / 'compose.json', bundle['compose'])
    atomic_json(old_dir / 'activation.json', {'phase': 'VERIFIED', 'target': checksum(old)})
    root = Path(old['manifest']['data_root'])
    atomic_json(root / 'deployment.json', {'phase': 'VERIFIED', 'bundle': checksum(old),
        'revision': old['manifest']['revision'], 'directory': str(old_dir)})
    atomic_json(root / 'telegram/connection.json', live.model_dump())
    monkeypatch.setattr(offline, 'source_check', lambda m: calls.append(('offline-source', m['revision'])))
    monkeypatch.setattr(offline, 'Engine', planning_candidate.Engine)
    monkeypatch.setattr(offline, 'image_check', lambda engine, images, revision:
                        calls.append(('offline-images', images, revision)))
    return {'previous_directory': old_dir, 'disabled_directory': disabled_dir, 'output': tmp_path / 'offline',
            'previous_pin': checksum(old), 'disabled_pin': checksum(target)}, old, target, live, calls


def test_prepare_and_inspect_remove_only_optional_access_without_key_profile_or_live_writes(offline_inputs, monkeypatch):
    args, old, _, _, calls = offline_inputs
    root = Path(old['manifest']['data_root'])
    before = [(p, p.read_bytes()) for p in (root / 'deployment.json', root / 'telegram/connection.json',
                                          args['previous_directory'] / 'activation.json')]
    real_open = io.open

    def guarded(path, *a, **k):
        checked = Path('/proc/self/fd/' + str(path)).resolve() if isinstance(path, int) else Path(path)
        assert checked.name not in {'openai.key', 'profile.json', 'host.json'}
        return real_open(path, *a, **k)

    monkeypatch.setattr(io, 'open', guarded)
    monkeypatch.setattr('httpx.Client', lambda *a, **k: pytest.fail('no provider client'))
    value = offline.prepare(**args)
    offline.inspect(args['output'], value['candidate_bundle'], value['preparation_digest'])
    bundle = offline.load_bundle(args['output'])
    assert 'planning' not in bundle['manifest'] and 'first_experiment' not in bundle['manifest']
    broker = bundle['compose']['services']['runtime-broker']
    assert not any(str(v).find('planning') >= 0 for v in broker.get('volumes', []))
    assert not any(k.startswith(('F1_PLANNING_', 'F2_INTEGRATION_')) for k in broker['environment'])
    assert 'activation.json' not in [p.name for p in args['output'].iterdir()]
    assert all(p.read_bytes() == data for p, data in before)
    assert len([c for c in calls if c[0] == 'offline-images']) == 2


@pytest.mark.parametrize('attack', ['planning', 'integration', 'telegram', 'owner', 'migration', 'pin', 'connection'])
def test_assemble_rejects_changed_scope_or_binding(offline_inputs, attack):
    args, old, disabled, live, _ = offline_inputs
    new = deepcopy(disabled)
    if attack in {'planning', 'integration', 'telegram'}:
        key = {'integration': 'first_experiment'}.get(attack, attack)
        new['manifest'][key] = old['manifest'].get(key, {})
    elif attack == 'owner':
        new['manifest']['owner_login'] = {'origin': 'http://127.0.0.1:19000', 'loopback_http': True}
    elif attack == 'migration':
        new['manifest']['migration_hash'] = 'f' * 64
    elif attack == 'connection':
        live = live.model_copy(update={'owner_id': 7654321})
    with pytest.raises(ValueError):
        offline.assemble(old, new, live, args['previous_pin'], '0' * 64 if attack == 'pin' else checksum(new))


@pytest.mark.parametrize('attack', ['receipt', 'compose', 'connection', 'inventory', 'mode', 'archive', 'activation'])
def test_inspection_rejects_tampered_preparation(offline_inputs, attack):
    args, _, _, _, _ = offline_inputs
    value = offline.prepare(**args)
    root = args['output']
    if attack == 'inventory':
        atomic_json(root / 'unexpected.json', {})
    elif attack == 'mode':
        (root / 'bundle.json').chmod(0o644)
    elif attack in {'archive', 'activation'}:
        atomic_json(root / ('connection.previous.json' if attack == 'archive' else 'activation.json'), {})
    else:
        name = {'receipt': 'preparation.json', 'compose': 'compose.json',
                'connection': 'connection.candidate.json'}[attack]
        data = offline.read_json(root / name, 1024 * 1024)
        data['changed'] = True
        atomic_json(root / name, data)
    with pytest.raises((ValueError, KeyError, Denied)):
        offline.inspect(root, value['candidate_bundle'], value['preparation_digest'])


def test_operator_uses_existing_interlocks_and_disabled_postcheck(monkeypatch, offline_inputs):
    # Import the actual operator composition, with only deployment I/O substituted.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'infra/vps'))
    try:
        spec = importlib.util.spec_from_file_location('offline_operator',
            Path(__file__).resolve().parents[1] / 'infra/vps/activate_offline_candidate.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    args, _, _, _, _ = offline_inputs
    value = offline.prepare(**args)
    bundle = offline.load_bundle(args['output'])
    previous = offline.load_bundle(args['previous_directory'])
    scope = module.OfflineScope(args['previous_pin'], value['candidate_bundle'], value['preparation_digest'])
    receipt = offline.read_json(args['output'] / 'preparation.json')
    assert scope.validate(previous, bundle, args['output'], receipt)['provider_bindings_removed'] is True
    calls = []
    monkeypatch.setattr(module, 'apply_transition', lambda *a, **k: calls.append((a, k)) or {'paid_calls': 0})
    module.activate(args['previous_directory'], args['output'], args['previous_pin'], value['candidate_bundle'],
                    value['preparation_digest'], 123)
    assert isinstance(calls[0][1]['_planning'], module.OfflineScope)
    monkeypatch.setattr(module.PlanningUpdate, 'postcheck', lambda *a: {'planning_runtime_ready': True})
    controller = object.__new__(module.OfflineUpdate)
    controller.engine = type('Engine', (), {'run': lambda _, *args: calls.append(args)})()
    assert controller.postcheck()['offline_runtime_ready']
    code = calls[-1][-1]
    compile(code, '<offline-postcheck>', 'exec')
    tree = ast.parse(code)
    nested = tree.body[-1].value.args[0]
    compile(ast.literal_eval(nested), '<offline-nested-postcheck>', 'exec')
