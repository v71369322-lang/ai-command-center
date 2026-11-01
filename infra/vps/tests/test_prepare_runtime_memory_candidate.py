import importlib.util
from pathlib import Path
import sys

import pytest

from command_center.deployment_profile import atomic_json, checksum
from command_center.store import digest
from command_center.telegram_transport import TelegramConnection


ROOT = Path(__file__).resolve().parents[3]
RECONCILE_SPEC = importlib.util.spec_from_file_location(
    'reconcile_deployment_intent', ROOT / 'infra/vps/reconcile_deployment_intent.py')
RECONCILE = importlib.util.module_from_spec(RECONCILE_SPEC)
sys.modules['reconcile_deployment_intent'] = RECONCILE
RECONCILE_SPEC.loader.exec_module(RECONCILE)
SPEC = importlib.util.spec_from_file_location(
    'prepare_runtime_memory_candidate', ROOT / 'infra/vps/prepare_runtime_memory_candidate.py')
operator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operator)


def bundles():
    active = TelegramConnection(mode='live', owner_id=10, bot_id=20,
        source_revision='1' * 40, token_file='/run/telegram/token')
    fixed = {'migration_hash': 'a' * 64, 'database_image': 'postgres',
             'redis_image': 'redis', 'data_root': '/state', 'control_uid': 1000,
             'execution_uid': 1001, 'owner_login': {'origin': 'x'}}
    old = {'manifest': {**fixed, 'revision': '1' * 40,
        'telegram': {'mode': 'live', 'owner_id': 10, 'bot_id': 20,
                     'connection_digest': digest(active.model_dump())}}, 'compose': {}}
    disabled = {'manifest': {**fixed, 'revision': '2' * 40},
                'compose': {'services': {'watchdog': {'mem_limit': '268435456'}}}}
    rendered = {'services': {'telegram': {'mem_limit': '256m'},
                             'watchdog': {'mem_limit': '268435456'}}}
    return active, old, disabled, rendered


def test_candidate_requires_both_memory_fixes(monkeypatch):
    active, old, disabled, rendered = bundles()
    approved = checksum(old)
    monkeypatch.setattr(operator, 'render', lambda compose, manifest: rendered)
    bundle, staged = operator.candidate(old, disabled, active, approved, '1' * 40, '2' * 40)
    assert bundle['compose'] == rendered
    assert staged.source_revision == '2' * 40
    assert bundle['manifest']['telegram']['connection_digest'] == digest(staged.model_dump())


@pytest.mark.parametrize('change', ['telegram_memory', 'watchdog_memory', 'integration',
                                    'owner', 'migration', 'revision'])
def test_candidate_rejects_scope_expansion(monkeypatch, change):
    active, old, disabled, rendered = bundles()
    if change == 'telegram_memory':
        rendered['services']['telegram']['mem_limit'] = '128m'
    elif change == 'watchdog_memory':
        rendered['services']['watchdog']['mem_limit'] = '134217728'
    elif change == 'integration':
        disabled['manifest']['first_experiment'] = {}
    elif change == 'owner':
        active = active.model_copy(update={'owner_id': 11})
    elif change == 'migration':
        disabled['manifest']['migration_hash'] = 'b' * 64
    else:
        disabled['manifest']['revision'] = '3' * 40
    monkeypatch.setattr(operator, 'render', lambda compose, manifest: rendered)
    with pytest.raises(ValueError):
        operator.candidate(old, disabled, active, checksum(old), '1' * 40, '2' * 40)


@pytest.fixture
def prepared_host(tmp_path, monkeypatch):
    uid = operator.os.getuid()
    root = tmp_path / 'state'
    telegram = root / 'telegram'
    previous_directory = tmp_path / 'previous'
    disabled_directory = tmp_path / 'disabled'
    parent = tmp_path / 'candidates'
    for path in (root, telegram, previous_directory, disabled_directory, parent):
        path.mkdir(mode=0o700)
    active = TelegramConnection(mode='live', owner_id=10, bot_id=20,
        source_revision='1' * 40, token_file='/run/telegram/token')
    atomic_json(telegram / 'connection.json', active.model_dump())
    images = {key: 'sha256:' + str(index) * 64 for index, key in enumerate(
        ('api', 'worker', 'broker', 'executor', 'coding'), 1)}
    old = {'manifest': {'revision': '1' * 40, 'control_uid': uid,
        'execution_uid': uid + 1, 'data_root': str(root), 'images': images}, 'compose': {}}
    disabled = {'manifest': {**old['manifest'], 'revision': '2' * 40}, 'compose': {}}
    target = {'manifest': disabled['manifest'], 'compose': {'services': {}}}
    approved = 'a' * 64
    atomic_json(root / 'deployment.json', {'phase': 'VERIFIED', 'bundle': approved,
        'revision': '1' * 40, 'directory': str(previous_directory)})
    staged = active.model_copy(update={'source_revision': '2' * 40})

    class FakeEngine:
        def __init__(self, value):
            self.uid = value

        def preflight(self):
            pass

    monkeypatch.setattr(operator, 'exact_bundle', lambda *args: old)
    monkeypatch.setattr(operator, 'load_bundle', lambda *args: disabled)
    monkeypatch.setattr(operator, 'candidate', lambda *args: (target, staged))
    monkeypatch.setattr(operator, 'source_check', lambda *args: None)
    monkeypatch.setattr(operator, 'Engine', FakeEngine)
    monkeypatch.setattr(operator, 'image_check', lambda *args: None)
    monkeypatch.setattr(operator.time, 'time', lambda: 1234)
    return root, previous_directory, disabled_directory, parent, approved, target


def test_prepare_writes_disabled_candidate_only_after_all_checks(prepared_host):
    root, previous, disabled, parent, approved, target = prepared_host
    output = parent / 'candidate'
    result = operator.prepare(previous, disabled, output, approved, '1' * 40, '2' * 40)
    assert result['candidate_bundle'] == checksum(target)
    assert result['telegram_memory_bytes'] == result['watchdog_memory_bytes'] == 268435456
    assert result['deployment_authorized'] is False
    assert result['task_admission_resumed'] is False and result['paid_calls'] == 0
    assert sorted(path.name for path in output.iterdir()) == [
        'bundle.json', 'compose.json', 'connection.candidate.json', 'preparation.json']
    assert not (root / 'activation.json').exists()


def test_prepare_intent_state_has_no_candidate_side_effect(prepared_host):
    root, previous, disabled, parent, approved, _ = prepared_host
    atomic_json(root / 'deployment.json', {'phase': 'INTENT', 'bundle': approved,
        'revision': '1' * 40, 'directory': str(previous)})
    output = parent / 'candidate'
    with pytest.raises(ValueError, match='verified_predecessor'):
        operator.prepare(previous, disabled, output, approved, '1' * 40, '2' * 40)
    assert not output.exists()
