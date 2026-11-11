"""Exact operator adapter with fake deployment; health gates use real PG/SQLite."""
import importlib.util
from pathlib import Path
import sys
import time
from uuid import uuid4

import pytest

from command_center.deployment_profile import atomic_json, checksum
from command_center.store import Denied, digest
from test_planning_candidate import inputs as inputs, invoke
from test_deployment import release as release
from test_planning_admission import profile as profile


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'infra/vps' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


load('reconcile_deployment_intent')
legacy = load('apply_reconciled_telegram_candidate')
operator = load('activate_planning_candidate')


@pytest.fixture
def staged(inputs, monkeypatch):
    from command_center import planning_candidate as candidate
    options = inputs[0]
    prepared = invoke(inputs)
    target = candidate.load_bundle(options['output'])
    events, failures = [], []
    class Previous:
        def __init__(self, bundle, directory):
            self.engine = self
        def preflight(self, **kwargs):
            assert kwargs == {'planning_check': False}
            events.append('previous-preflight')
        def quiesce(self):
            events.append('normal-stop')
        def compose(self, *args):
            events.append(args)
        def run(self, *args):
            assert args[0] == 'ps'
            return b''
    class Engine:
        def __init__(self, uid):
            pass
        def preflight(self):
            events.append('rootless-preflight')
    class Update:
        def __init__(self, bundle, directory):
            self.bundle, self.directory = bundle, Path(directory)
        def apply(self, action, approval, *, expected_previous):
            assert action == 'update' and approval == prepared['candidate_bundle'] and expected_previous == options['previous_pin']
            assert candidate.connection(Path(target['manifest']['data_root']) / 'telegram/connection.json').source_revision == target['manifest']['revision']
            events.append('existing-deployment-apply')
            self.state('INTENT' if failures else 'VERIFIED')
            if failures:
                raise RuntimeError('synthetic unknown apply outcome')
            return self.postcheck()
        def state(self, phase):
            atomic_json(Path(target['manifest']['data_root']) / 'deployment.json', {
                'phase': phase, 'bundle': checksum(target), 'revision': target['manifest']['revision'],
                'directory': str(self.directory), 'migration_hash': target['manifest']['migration_hash'],
                'database_image': target['manifest']['database_image']})
        def reconcile_intent(self, approval):
            assert approval == checksum(self.bundle)
            events.append('existing-deployment-reconcile-intent')
            self.state('VERIFIED')  # Explicit fake of the independently tested core method.
            return self.postcheck()
        def preflight(self):
            events.append('target-preflight')
        def postcheck(self):
            events.append('target-postcheck')
            return {'planning_runtime_ready': True, 'admission_halted': True, 'go_live': False}
    monkeypatch.setattr(legacy, 'Deployment', Previous)
    monkeypatch.setattr(legacy, 'Engine', Engine)
    monkeypatch.setattr(legacy, 'source_check', lambda m: events.append('target-source'))
    monkeypatch.setattr(legacy, 'image_check', lambda *a: events.append('target-images'))
    monkeypatch.setattr(operator.PlanningScope, 'controller', staticmethod(Update))
    args = dict(previous_directory=options['previous_directory'], candidate_directory=options['output'],
        approved_previous=options['previous_pin'], approved_candidate=prepared['candidate_bundle'],
        approved_until=int(time.time()) + 120, approved_preparation=prepared['preparation_digest'],
        approved_capability=digest(operator.capability(target)))
    return args, events, failures, inputs


def test_planning_requires_separate_capability_before_live_mutation(staged):
    args, events, _, inputs = staged
    args['approved_capability'] = 'f' * 64
    with pytest.raises(ValueError, match='exact_access'):
        operator.apply(**args)
    assert not events and not (inputs[0]['output'] / 'activation.json').exists()


def test_planning_activation_reuses_apply_and_leaves_admission_halted(staged):
    args, events, _, inputs = staged
    result = operator.apply(**args)
    assert result['status'] == 'PLANNING_CANDIDATE_APPLIED'
    assert result['task_admission_resumed'] is False and result['paid_calls'] == 0
    assert events.index('normal-stop') < events.index(('stop', 'telegram')) < events.index('existing-deployment-apply')
    journal = operator.read_json(inputs[0]['output'] / 'activation.json')
    assert journal['phase'] == 'VERIFIED' and journal['control_capability'] == args['approved_capability']
    assert journal['preparation_digest'] == args['approved_preparation']


def test_unknown_apply_is_not_retried_and_exact_reconciliation_reuses_core(staged):
    args, events, failures, inputs = staged
    failures.append(True)
    with pytest.raises(RuntimeError, match='unknown apply'):
        operator.apply(**args)
    journal = inputs[0]['output'] / 'activation.json'
    assert operator.read_json(journal)['phase'] == 'DEPLOYMENT_ATTEMPTED'
    before = events.copy()
    with pytest.raises(ValueError, match='existing_activation'):
        operator.apply(**args)
    assert events == before
    result = operator.reconcile(**args)
    assert not result['runtime_changed'] and not result['binding_changed'] and result['paid_calls'] == 0
    assert events.count('existing-deployment-apply') == 1
    assert events.count('existing-deployment-reconcile-intent') == 1
    assert operator.read_json(journal)['phase'] == 'VERIFIED'


def test_legacy_memory_adapter_cannot_bypass_planning_approval(staged):
    args, events, _, _ = staged
    with pytest.raises(ValueError, match='separate_planning_access'):
        legacy.apply(args['previous_directory'], args['candidate_directory'], args['approved_previous'],
                     args['approved_candidate'], args['approved_until'])
    assert not events


@pytest.mark.parametrize('change', ['deadline', 'preparation', 'previous'])
def test_invalid_exact_activation_scope_does_not_touch_live_binding(staged, change):
    args, events, _, inputs = staged
    if change == 'deadline':
        args['approved_until'] = int(time.time())
    else:
        args['approved_' + change] = 'f' * 64
    with pytest.raises(ValueError):
        operator.apply(**args)
    assert not events and not (inputs[0]['output'] / 'activation.json').exists()


@pytest.mark.parametrize('state', ['healthy', 'historical_complete', 'resumed', 'recovery', 'worker', 'runtime',
                                 'financial', 'complete_reserved', 'ledger_tamper'])
def test_activation_health_gates_with_real_pg_and_sqlite(store, settings, tmp_path, monkeypatch, state):
    from command_center.coding.contract import CodingRequest, payload
    from command_center.coding.gateway import Gateway
    from command_center.models import Control, ExternalAction
    from command_center.runtime_ledger import RuntimeLedger
    task = store.create('owner', str(uuid4()), payload(CodingRequest(provider='openai')))
    if state in {'financial', 'ledger_tamper', 'complete_reserved', 'historical_complete'}:
        with store.transaction() as tx:
            row = ExternalAction(id=str(uuid4()), task_id=task['id'], key=str(uuid4()), kind='openai',
                request_hash='a' * 64, state='COMPLETE' if state in {'historical_complete', 'complete_reserved'} else 'INTENT',
                reserved=0 if state == 'historical_complete' else 1, actual=1 if state == 'historical_complete' else 0,
                created_at=store.now(tx), evidence={})
            tx.add(row)
            tx.flush()
            if state != 'ledger_tamper':
                store.audit(tx, 'synthetic_ledger_fixture', 'owner', task['id'],
                            action_id=row.id, ledger_digest=Gateway.action_digest(row))
    store.halt('owner')
    if state in {'resumed', 'recovery'}:
        with store.transaction() as tx:
            control = tx.get(Control, 1)
            control.halted = state != 'resumed'
            control.recovery = state == 'recovery'
    ledger = RuntimeLedger(tmp_path / 'ledger.sqlite')
    ledger.worker_beat(settings.source_revision if state != 'worker' else 'f' * 40)
    if state == 'runtime':
        ledger.register({'id': str(uuid4()), 'fence': 1, 'revision': settings.source_revision}, 'synthetic-runtime', 30)
    monkeypatch.setenv('F1_RUNTIME_LEDGER', str(ledger.path))
    monkeypatch.setattr(legacy.ReconciledUpdate, 'postcheck', lambda self: {'go_live': False})
    monkeypatch.setattr('httpx.Client', lambda *a, **k: pytest.fail('HTTP during health checks'))
    class Engine:
        def run(self, *args):
            assert args[:4] == ('exec', 'acc-f23-runtime-broker-1', 'python', '-c')
            exec(compile(args[-1], 'synthetic_broker_health.py', 'exec'), {})
    controller = operator.PlanningUpdate({'manifest': {'data_root': str(tmp_path)}, 'compose': {}},
                                         tmp_path, Engine(), object())
    monkeypatch.setattr(controller, 'tool', lambda code: exec(compile(code, 'synthetic_db_health.py', 'exec'), {}))
    if state in {'healthy', 'historical_complete'}:
        result = controller.postcheck()
        assert result['planning_runtime_ready'] and result['admission_halted'] and not result['paid_calls_authorized']
    else:
        with pytest.raises((AssertionError, Denied)):
            controller.postcheck()
