import importlib.util
import json
from pathlib import Path
import sys

import pytest

from command_center.deployment_profile import atomic_json
from command_center.store import digest
from command_center.telegram_transport import TelegramConnection, connection


ROOT = Path(__file__).resolve().parents[3]
RECONCILE_SPEC = importlib.util.spec_from_file_location(
    'reconcile_deployment_intent', ROOT / 'infra/vps/reconcile_deployment_intent.py')
RECONCILE = importlib.util.module_from_spec(RECONCILE_SPEC)
sys.modules['reconcile_deployment_intent'] = RECONCILE
RECONCILE_SPEC.loader.exec_module(RECONCILE)
SPEC = importlib.util.spec_from_file_location(
    'apply_reconciled_telegram_candidate',
    ROOT / 'infra/vps/apply_reconciled_telegram_candidate.py')
operator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operator)


def manifests():
    fixed = {'migration_hash': 'a' * 64, 'database_image': 'postgres', 'redis_image': 'redis',
             'data_root': '/state', 'control_uid': 1000, 'execution_uid': 1001,
             'owner_login': {'origin': 'x'}}
    telegram = {'mode': 'live', 'owner_id': 1, 'bot_id': 2, 'connection_digest': 'b' * 64}
    old = {'manifest': {**fixed, 'revision': '1' * 40, 'telegram': telegram}, 'compose': {}}
    new = {'manifest': {**fixed, 'revision': '2' * 40,
                        'telegram': {**telegram, 'connection_digest': 'c' * 64}},
           'compose': {'services': {
               'telegram': {'mem_limit': '256m'},
               'watchdog': {'mem_limit': '268435456'},
           }}}
    return old, new


def test_transition_accepts_only_memory_candidate(monkeypatch):
    old, new = manifests()
    monkeypatch.setattr(operator, 'checksum', lambda value: 'old' if value is old else 'new')
    assert operator.validate_transition(old, new, 'old', 'new') == (old['manifest'], new['manifest'])


@pytest.mark.parametrize('change', ['migration_hash', 'owner_id', 'memory',
                                    'watchdog_memory', 'integration'])
def test_transition_rejects_scope_expansion(monkeypatch, change):
    old, new = manifests()
    if change == 'owner_id':
        new['manifest']['telegram']['owner_id'] = 9
    elif change == 'memory':
        new['compose']['services']['telegram']['mem_limit'] = '128m'
    elif change == 'watchdog_memory':
        new['compose']['services']['watchdog']['mem_limit'] = '134217728'
    elif change == 'integration':
        new['manifest']['first_experiment'] = {}
    else:
        new['manifest'][change] = 'changed'
    monkeypatch.setattr(operator, 'checksum', lambda value: 'old' if value is old else 'new')
    with pytest.raises(ValueError):
        operator.validate_transition(old, new, 'old', 'new')


@pytest.mark.parametrize('now,until', [(1000, 1000), (1000, 4601), (1000, None), (1000, True)])
def test_deadline_is_fresh_and_bounded(monkeypatch, now, until):
    monkeypatch.setattr(operator.time, 'time', lambda: now)
    with pytest.raises(ValueError, match='bounded'):
        operator.deadline(until)


@pytest.fixture
def staged_update(tmp_path, monkeypatch):
    root = tmp_path / 'state'
    telegram = root / 'telegram'
    previous_directory = tmp_path / 'previous'
    candidate_directory = tmp_path / 'candidate'
    for path in (root, telegram, previous_directory, candidate_directory):
        path.mkdir(mode=0o700)
    original = TelegramConnection(mode='live', owner_id=10, bot_id=20,
                                  source_revision='1' * 40, token_file='/run/telegram/token')
    staged = TelegramConnection.model_validate({
        **original.model_dump(), 'source_revision': '2' * 40,
    })
    atomic_json(telegram / 'connection.json', original.model_dump())
    atomic_json(candidate_directory / 'connection.candidate.json', staged.model_dump())
    old_digest, new_digest = 'a' * 64, 'b' * 64
    fixed = {'migration_hash': 'c' * 64, 'database_image': 'postgres',
             'redis_image': 'redis', 'data_root': str(root), 'control_uid': 1000,
             'execution_uid': 1001, 'owner_login': {'origin': 'x'},
             'images': {key: 'sha256:' + str(index) * 64 for index, key in enumerate(
                 ('api', 'worker', 'broker', 'executor', 'coding'), 1)}}
    old = {'manifest': {**fixed, 'revision': original.source_revision,
                        'telegram': {'mode': 'live', 'owner_id': 10, 'bot_id': 20,
                                     'connection_digest': digest(original.model_dump())}},
           'compose': {}}
    new = {'manifest': {**fixed, 'revision': staged.source_revision,
                        'telegram': {'mode': 'live', 'owner_id': 10, 'bot_id': 20,
                                     'connection_digest': digest(staged.model_dump())}},
           'compose': {'services': {
               'telegram': {'mem_limit': '256m'},
               'watchdog': {'mem_limit': '268435456'},
           }}}
    atomic_json(root / 'deployment.json', {
        'phase': 'VERIFIED', 'bundle': old_digest, 'directory': str(previous_directory),
    })
    atomic_json(candidate_directory / 'preparation.json', {
        'state': 'STAGED_NOT_ACTIVATED', 'candidate_bundle': new_digest,
        'expected_incomplete_predecessor': old_digest,
        'external_ai_profile_enabled': False,
    })
    events = []

    class Controller:
        def __init__(self, bundle, directory):
            assert bundle is old and Path(directory) == previous_directory
            self.engine = self

        def preflight(self):
            events.append('old-preflight')

        def compose(self, *args):
            events.append(('old-compose', *args))

        def run(self, *args):
            events.append(('old-engine', *args))
            return b''

    class Engine:
        def __init__(self, uid):
            self.uid = uid

        def preflight(self):
            events.append(('engine-preflight', self.uid))

    class Update:
        failure = None

        def __init__(self, bundle, directory):
            assert bundle is new and Path(directory) == candidate_directory

        def apply(self, action, approval, *, expected_previous):
            events.append(('apply', action, approval, expected_previous))
            if self.failure:
                raise RuntimeError(self.failure)
            return {'state': 'CLOSED_SYNTHETIC_SERVICES_RUNNING', 'go_live': False}

    monkeypatch.setattr(operator, 'exact_bundle', lambda path, approved: old)
    monkeypatch.setattr(operator, 'load_bundle', lambda path: new)
    monkeypatch.setattr(operator, 'checksum', lambda value: old_digest if value is old else new_digest)
    monkeypatch.setattr(operator, 'Deployment', Controller)
    monkeypatch.setattr(operator, 'Engine', Engine)
    monkeypatch.setattr(operator, 'ReconciledUpdate', Update)
    monkeypatch.setattr(operator, 'source_check', lambda manifest: events.append('source-check'))
    monkeypatch.setattr(operator, 'image_check', lambda *args: events.append('image-check'))
    monkeypatch.setattr(operator.time, 'time', lambda: 1000)
    return (previous_directory, candidate_directory, old_digest, new_digest,
            original, staged, events, Update)


def invoke(staged_update):
    previous, candidate, old, new, *_ = staged_update
    return operator.apply(previous, candidate, old, new, 1100)


def test_apply_orders_stop_binding_and_existing_deployment_interlocks(staged_update):
    *_, staged, events, _ = staged_update
    result = invoke(staged_update)
    assert result['status'] == 'TELEGRAM_MEMORY_FIX_APPLIED'
    assert events.index(('old-compose', 'stop', 'telegram')) < events.index(
        ('apply', 'update', 'b' * 64, 'a' * 64))
    assert connection(staged_update[1] / 'connection.previous.json') == staged_update[4]
    assert connection(staged_update[1].parent / 'state/telegram/connection.json') == staged
    activation = json.loads((staged_update[1] / 'activation.json').read_text())
    assert activation['phase'] == 'VERIFIED'
    assert activation['task_admission_resumed'] is False and activation['paid_calls'] == 0


def test_unknown_apply_result_preserves_receipt_and_blocks_retry(staged_update):
    staged_update[-1].failure = 'unknown-daemon-result'
    with pytest.raises(RuntimeError, match='unknown-daemon-result'):
        invoke(staged_update)
    activation = json.loads((staged_update[1] / 'activation.json').read_text())
    assert activation['phase'] == 'DEPLOYMENT_ATTEMPTED'
    before = staged_update[6][:]
    with pytest.raises(ValueError, match='existing_activation'):
        invoke(staged_update)
    assert staged_update[6] == before
