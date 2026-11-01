import importlib.util
import json
from pathlib import Path

import pytest

from command_center.deployment_profile import atomic_json
from command_center.store import digest
from command_center.telegram_transport import TelegramConnection


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    'reconcile_runtime_memory_activation',
    ROOT / 'infra/vps/reconcile_runtime_memory_activation.py')
operator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operator)


@pytest.fixture
def attempted(tmp_path, monkeypatch):
    uid = operator.os.getuid()
    root = tmp_path / 'state'
    telegram = root / 'telegram'
    candidate = tmp_path / 'candidate'
    for path in (root, telegram, candidate):
        path.mkdir(mode=0o700)
    previous, target = 'a' * 64, 'b' * 64
    revision = 'c' * 40
    live = TelegramConnection(mode='live', owner_id=10, bot_id=20,
        source_revision=revision, token_file='/run/telegram/token')
    atomic_json(telegram / 'connection.json', live.model_dump())
    bundle = {'manifest': {'control_uid': uid, 'data_root': str(root),
        'revision': revision, 'telegram': {'connection_digest': digest(live.model_dump())}},
        'compose': {}}
    atomic_json(candidate / 'preparation.json', {'state': 'STAGED_NOT_ACTIVATED',
        'candidate_bundle': target, 'expected_incomplete_predecessor': previous,
        'external_ai_profile_enabled': False, 'task_admission_resumed': False,
        'paid_calls': 0})
    atomic_json(candidate / 'activation.json', {'phase': 'DEPLOYMENT_ATTEMPTED',
        'previous': previous, 'target': target, 'task_admission_resumed': False,
        'paid_calls': 0})
    atomic_json(root / 'deployment.json', {'phase': 'VERIFIED', 'bundle': target,
        'revision': revision, 'directory': str(candidate)})
    events = []

    class Deployment:
        def __init__(self, value, directory):
            assert value is bundle and Path(directory) == candidate

        def preflight(self):
            events.append('preflight')

        def postcheck(self):
            events.append('postcheck')
            return {'state': 'CLOSED_SYNTHETIC_SERVICES_RUNNING', 'go_live': False}

    monkeypatch.setattr(operator, 'load_bundle', lambda path: bundle)
    monkeypatch.setattr(operator, 'checksum', lambda value: target)
    monkeypatch.setattr(operator, 'Deployment', Deployment)
    monkeypatch.setattr(operator.time, 'time', lambda: 1000)
    return candidate, previous, target, events


def test_reconcile_closes_exact_attempt_after_postcheck(attempted):
    candidate, previous, target, events = attempted
    result = operator.reconcile(candidate, previous, target, 1100)
    assert events == ['preflight', 'postcheck']
    assert result['status'] == 'RUNTIME_MEMORY_ACTIVATION_RECONCILED'
    assert result['runtime_changed'] is False and result['paid_calls'] == 0
    receipt = json.loads((candidate / 'activation.json').read_text())
    assert receipt['phase'] == 'VERIFIED'
    assert receipt['checks']['go_live'] is False


@pytest.mark.parametrize('change', ['activation', 'deployment', 'binding', 'deadline'])
def test_reconcile_rejects_changed_evidence_without_receipt_write(attempted, monkeypatch, change):
    candidate, previous, target, events = attempted
    path = candidate / 'activation.json'
    before = path.read_bytes()
    until = 1100
    if change == 'activation':
        value = json.loads(path.read_text())
        value['phase'] = 'VERIFIED'
        atomic_json(path, value)
        before = path.read_bytes()
    elif change == 'deployment':
        state = candidate.parent / 'state/deployment.json'
        value = json.loads(state.read_text())
        value['phase'] = 'INTENT'
        atomic_json(state, value)
    elif change == 'binding':
        monkeypatch.setattr(operator, 'digest', lambda value: 'f' * 64)
    else:
        until = 1000
    with pytest.raises(ValueError):
        operator.reconcile(candidate, previous, target, until)
    assert path.read_bytes() == before
    assert events == []
