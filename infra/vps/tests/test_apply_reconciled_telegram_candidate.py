import importlib.util
from pathlib import Path
import sys

import pytest


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
           'compose': {'services': {'telegram': {'mem_limit': '256m'}}}}
    return old, new


def test_transition_accepts_only_memory_candidate(monkeypatch):
    old, new = manifests()
    monkeypatch.setattr(operator, 'checksum', lambda value: 'old' if value is old else 'new')
    assert operator.validate_transition(old, new, 'old', 'new') == (old['manifest'], new['manifest'])


@pytest.mark.parametrize('change', ['migration_hash', 'owner_id', 'memory', 'integration'])
def test_transition_rejects_scope_expansion(monkeypatch, change):
    old, new = manifests()
    if change == 'owner_id':
        new['manifest']['telegram']['owner_id'] = 9
    elif change == 'memory':
        new['compose']['services']['telegram']['mem_limit'] = '128m'
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
