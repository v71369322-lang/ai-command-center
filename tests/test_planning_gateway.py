"""Real F1/PG approval and money ledger, strict HTTP-mock planning only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import replace
import json
from threading import Event
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select

from command_center.coding.gateway import Gateway, Uncertain
from command_center.coding.integration_config import FileCredentials, Tariff
from command_center.models import Approval, Audit, Control, ExternalAction, ExternalGrant, Outbox, Task
from command_center.planning_gateway import CONFIRMATION, KEY, SCOPE, PlanningConfig, PlanningGateway
from command_center.planning_task import create_task, payload
from command_center.project_inbox import classify
from command_center.request_plan_store import read, EVENT
from command_center.request_planning import context, request_document
from command_center.runtime_broker import RuntimeBroker
from command_center.store import Denied, digest
from command_center.worker import Runner
from command_center.watchdog import Watchdog
from test_request_planning import snapshot as snapshot, response, change_plan, MODEL, LIMITS
from test_telegram_readiness import ledger
from test_telegram_task_status import authority
from test_readiness import setup as coding_setup, send as coding_send
from test_project_inbox import capture


def config():
    return PlanningConfig(mode='http_mock', enabled=True, budget_evidence='PUBLIC_MOCK_ONLY_NOT_FUNDING',
        daily_nano_rub=1_000_000, monthly_nano_rub=1_000_000,
        tariff=Tariff(model=MODEL, input_nano_rub=2, output_nano_rub=4,
                      context_tokens=8192, max_output_tokens=2048, confirmed=True, evidence='PUBLIC_MOCK_ONLY'))


class Backend:
    def __init__(self, snapshot):
        self.snapshot, self.calls, self.after = snapshot, [], None
        self.data, self.status, self.drop = response(snapshot), 200, False

    def handle(self, request):
        assert str(request.url) == 'https://api.openai.com/v1/responses'
        assert request.headers['Authorization'] == 'Bearer PUBLIC_PLANNING_HTTP_MOCK_ONLY'
        self.calls.append(json.loads(request.content))
        if self.after:
            self.after()
        if self.drop:
            raise httpx.ReadTimeout('public mock response loss')
        return httpx.Response(self.status, json=self.data, headers={'x-request-id': 'public-planning-response'})


@pytest.fixture
def planning(store, snapshot):
    backend = Backend(snapshot)
    gateway = PlanningGateway(store, config(), transport=httpx.MockTransport(backend.handle))
    task = create_task(store, 'owner', snapshot)
    yield gateway, task, backend
    gateway.close()


def approve(gateway, task, **changes):
    args = {'budget_nano_rub': gateway.config.tariff.maximum(), 'confirmation': CONFIRMATION,
            'expected_config_hash': digest(gateway.config.model_dump())}
    args.update(changes)
    return gateway.authorize('owner', task['id'], task['version'], **args)


def claim(store, planning):
    gateway, task, _ = planning
    approve(gateway, task)
    return store.claim(task['id'])


def actions(store):
    with store.transaction() as session:
        return list(session.scalars(select(ExternalAction).order_by(ExternalAction.id)))


def drafts(store):
    with store.transaction() as session:
        return list(session.scalars(select(Audit).where(Audit.event['kind'].as_string() == EVENT)))


def test_waiting_task_to_f1_grant_one_mock_request_atomic_draft_and_success(planning, snapshot, store, monkeypatch):
    gateway, waiting, backend = planning
    assert waiting['state'] == 'WAITING_APPROVAL' and drafts(store) == [] and actions(store) == []
    with store.transaction() as session:
        assert session.get(Approval, waiting['id']) is None
        assert session.get(ExternalGrant, waiting['id']) is None
        assert session.scalar(select(Outbox)) is None
    monkeypatch.setattr(FileCredentials, 'get', lambda *a: pytest.fail('no real credential read'))
    task = claim(store, planning)
    assert task['fence'] == 1 and task['attempts'] == 1
    result = gateway.perform(task['id'], task['fence'])
    assert result['stored'] and result['provider_evidence_verified'] is result['execution_authorized'] is False
    assert backend.calls == [request_document(snapshot, MODEL, **LIMITS)]
    final = store.get(task['id'])
    assert final['state'] == 'SUCCEEDED' and '"business_execution":false' in final['artifact']
    assert read(store, 'owner', snapshot.request_id)['state'] == 'CURRENT'
    assert len(drafts(store)) == 1 and len(actions(store)) == 1
    assert actions(store)[0].actual == 1400 and actions(store)[0].reserved == 0
    assert gateway.status(task['id'])['financial_values_are_mock'] is True
    with store.transaction() as session:
        assert session.get(Control, 1).actual == 1 and session.get(Control, 1).reserved == 0
        assert session.get(ExternalGrant, task['id']).document['scope'] == SCOPE


def test_no_default_or_live_transport_can_be_constructed(store, monkeypatch):
    monkeypatch.setattr(httpx, 'Client', lambda *a, **k: pytest.fail('disabled must fail before client construction'))
    with pytest.raises(Denied, match='http_mock_only'):
        PlanningGateway(store)
    with pytest.raises(Denied, match='http_mock_only'):
        PlanningGateway(store, config())
    with pytest.raises(ValidationError):
        PlanningConfig(mode='live', enabled=True)
    with pytest.raises(ValidationError):
        PlanningConfig(mode='http_mock', enabled=True, credential_files={'openai': '/private/key'})


def test_create_task_is_fixed_idempotent_and_never_reopens_a_terminal_attempt(planning, snapshot, store):
    _, task, _ = planning
    assert create_task(store, 'owner', snapshot)['id'] == task['id']
    store.cancel('owner', task['id'])
    assert create_task(store, 'owner', snapshot)['state'] == 'CANCELLED'
    with store.transaction() as session:
        assert len(list(session.scalars(select(Task)))) == 1


@pytest.mark.parametrize('role', ['operator', 'agent', None])
def test_planning_requires_owner_for_create_and_scoped_approval(planning, snapshot, store, role):
    gateway, task, _ = planning
    with pytest.raises(Denied):
        create_task(store, role, snapshot)
    with pytest.raises(Denied):
        gateway.authorize(role, task['id'], task['version'], budget_nano_rub=1_000_000,
                          confirmation=CONFIRMATION, expected_config_hash=digest(gateway.config.model_dump()))
    if role == 'operator':
        with pytest.raises(Denied, match='owner_required_for_planning'):
            store.create(role, 'public-operator-plan', payload(snapshot))


@pytest.mark.parametrize('change', [{'confirmation': 'AUTHORIZE_FIRST_PAID_EXPERIMENT'},
    {'expected_config_hash': '0' * 64}, {'budget_nano_rub': True}, {'budget_nano_rub': 1}, {'seconds': 121}, {'seconds': True}])
def test_approval_cannot_reuse_coding_consent_or_weaken_budget_bounds(planning, store, change):
    gateway, task, _ = planning
    with pytest.raises(Denied):
        approve(gateway, task, **change)
    assert store.get(task['id'])['state'] == 'WAITING_APPROVAL'
    with store.transaction() as session:
        assert session.get(ExternalGrant, task['id']) is None and session.get(Approval, task['id']) is None


def test_generic_f1_approval_alone_cannot_invoke_provider(planning, store):
    gateway, task, backend = planning
    store.approve('owner', task['id'], task['version'])
    task = store.claim(task['id'])
    with pytest.raises(Denied):
        gateway.perform(task['id'], task['fence'])
    assert backend.calls == [] and actions(store) == []


@pytest.mark.parametrize('change', ['project', 'source', 'stop', 'revoke', 'fence', 'profile', 'lease'])
def test_authority_is_rechecked_before_any_io(planning, snapshot, store, monkeypatch, change):
    gateway, _, backend = planning
    task = claim(store, planning)
    if change == 'project':
        classify(store, 'owner', snapshot.request_id, 'capital-lab', 1, str(uuid4()))
    elif change == 'source':
        monkeypatch.setattr(store, 'settings', replace(store.settings, source_revision='a' * 40))
    elif change == 'stop':
        store.halt('owner')
    elif change == 'revoke':
        store.cancel('owner', task['id'], revoke=True)
    elif change == 'fence':
        task['fence'] += 1
    elif change == 'profile':
        gateway.config.tariff.input_nano_rub += 1
    else:
        now = store.now
        monkeypatch.setattr(store, 'now', lambda s: now(s).replace(year=now(s).year + 1))
    with pytest.raises(Denied):
        gateway.perform(task['id'], task['fence'])
    assert backend.calls == [] and actions(store) == []


def test_changed_profile_between_owner_review_and_approval_rolls_back(planning, store, monkeypatch):
    gateway, task, _ = planning
    original = store.approve
    def change(*a, **kw):
        gateway.config.tariff.input_nano_rub += 1
        return original(*a, **kw)
    monkeypatch.setattr(store, 'approve', change)
    with pytest.raises(Denied, match='approval_profile_changed'):
        approve(gateway, task)
    assert store.get(task['id'])['state'] == 'WAITING_APPROVAL'


@pytest.mark.parametrize('change', ['model', 'tools', 'tier', 'context'])
def test_only_exact_planning_document_is_allowed(planning, snapshot, store, change):
    gateway, _, backend = planning
    task = claim(store, planning)
    body = request_document(snapshot, MODEL, **LIMITS)
    if change == 'model':
        body['model'] = 'other-model'
    elif change == 'tools':
        body['tools'] = [{'type': 'web_search'}]
    elif change == 'tier':
        body['service_tier'] = 'priority'
    else:
        body['input'][1]['content'] += ' changed'
    with pytest.raises(Denied, match='provider_request_contract'):
        gateway.request(task['id'], task['fence'], KEY, 'openai', 'POST', '/v1/responses', body)
    assert backend.calls == [] and actions(store) == []


def test_planning_and_coding_grants_cannot_be_cross_used(planning, store):
    planner, _, backend = planning
    coding, task, fake = coding_setup(store)
    try:
        with pytest.raises(Denied):
            planner.perform(task['id'], task['fence'])
        assert fake.ai_calls == 0 and backend.calls == []
    finally:
        coding.close()


def test_coding_gateway_rejects_planning_task_even_with_its_own_grant(planning, store):
    planner, _, _ = planning
    task = claim(store, planning)
    with store.transaction() as session, pytest.raises(Denied, match='external_task_scope'):
        Gateway.authority(planner, session, task['id'], task['fence'])
    with pytest.raises(Denied, match='external_task_scope'):
        Gateway.status(planner, task['id'])


@pytest.mark.parametrize('method,path,kind', [('GET', '/v1/responses', 'openai'),
    ('POST', '/v1/chat/completions', 'openai'), ('POST', '/repos/example/repo/pulls', 'github')])
def test_no_other_provider_or_publisher_endpoint_exists(planning, method, path, kind):
    with pytest.raises(Denied, match='endpoint_forbidden'):
        planning[0].endpoint(kind, path, method)


def test_cached_response_never_creates_a_second_http_request(planning, snapshot, store):
    gateway, _, backend = planning
    task = claim(store, planning)
    body = request_document(snapshot, MODEL, **LIMITS)
    first = gateway.request(task['id'], task['fence'], KEY, 'openai', 'POST', '/v1/responses', body)
    assert gateway.request(task['id'], task['fence'], KEY, 'openai', 'POST', '/v1/responses', body) == first
    gateway.perform(task['id'], task['fence'])
    with pytest.raises(Denied):
        gateway.perform(task['id'], task['fence'])
    assert len(backend.calls) == len(actions(store)) == len(drafts(store)) == 1


@pytest.mark.parametrize('case', ['timeout', 'http_error', 'missing_usage'])
def test_ambiguous_outcome_retains_reservation_and_blocks_repeat(planning, store, case):
    gateway, _, backend = planning
    task = claim(store, planning)
    if case == 'timeout':
        backend.drop = True
    elif case == 'http_error':
        backend.status = 500
    else:
        backend.data.pop('usage')
    with pytest.raises(Uncertain):
        gateway.perform(task['id'], task['fence'])
    assert actions(store)[0].reserved == gateway.config.tariff.maximum()
    assert actions(store)[0].state == 'UNCERTAIN' and drafts(store) == []
    with pytest.raises(Uncertain):
        gateway.perform(task['id'], task['fence'])
    assert len(backend.calls) == 1


def test_cancellation_during_http_preserves_confirmed_mock_cost_but_no_plan(planning, store):
    gateway, _, backend = planning
    task = claim(store, planning)
    backend.after = lambda: store.cancel('owner', task['id'])
    with pytest.raises(Denied):
        gateway.perform(task['id'], task['fence'])
    assert actions(store)[0].actual == 1400 and actions(store)[0].state == 'COMPLETE'
    assert drafts(store) == [] and store.get(task['id'])['state'] == 'CANCEL_REQUESTED'


def test_tariff_mutation_during_io_cannot_reprice_the_admitted_request(planning, store):
    gateway, _, backend = planning
    task = claim(store, planning)
    backend.after = lambda: setattr(gateway.config.tariff, 'input_nano_rub', 3)
    with pytest.raises(Denied, match='scope_changed'):
        gateway.perform(task['id'], task['fence'])
    assert actions(store)[0].actual == 1400 and drafts(store) == []


def test_failure_during_atomic_plan_finalization_uses_cached_response_on_recovery(planning, store, monkeypatch):
    gateway, _, backend = planning
    task = claim(store, planning)
    audit = store.audit
    def fail(session, kind, *a, **kw):
        if kind == 'planning_proposal_bound':
            raise RuntimeError('public local composition failure')
        return audit(session, kind, *a, **kw)
    with monkeypatch.context() as patch:
        patch.setattr(store, 'audit', fail)
        with pytest.raises(RuntimeError):
            gateway.perform(task['id'], task['fence'])
    assert store.get(task['id'])['state'] == 'RUNNING' and drafts(store) == []
    assert actions(store)[0].state == 'COMPLETE'
    gateway.perform(task['id'], task['fence'])
    assert store.get(task['id'])['state'] == 'SUCCEEDED'
    assert len(backend.calls) == len(drafts(store)) == 1


def test_invalid_plan_is_not_published_even_with_structurally_settled_usage(planning, store):
    gateway, _, backend = planning
    task = claim(store, planning)
    change_plan(backend.data, lambda p: p.update(execution_authorized=True))
    with pytest.raises(Denied, match='planning_response_invalid'):
        gateway.perform(task['id'], task['fence'])
    assert actions(store)[0].state == 'COMPLETE' and drafts(store) == []
    assert store.get(task['id'])['state'] == 'RUNNING'


def test_production_broker_and_generic_runner_reject_planning_before_effects(planning, store):
    _, waiting, _ = planning
    approve(planning[0], waiting)
    class Ledger:
        def verify(self):
            pass
        def watchdog_ready(self, *a):
            pytest.fail('unsupported planning must stop before runtime admission')
    class Backend:
        def preflight(self):
            pytest.fail('no engine access for unsupported planning dispatch')
    broker = RuntimeBroker(store, Ledger(), Backend())
    try:
        with pytest.raises(Denied, match='planning_runtime_not_connected'):
            broker.submit(waiting['id'], store.settings.source_revision)
    finally:
        broker.pool.shutdown(wait=True)
    assert store.get(waiting['id'])['state'] == 'READY'
    for method in (Runner(store).execute, Runner(store).reconcile):
        with pytest.raises(Denied, match='task_scope'):
            method(waiting)
    assert actions(store) == []


@pytest.mark.parametrize('change', ['cost', 'float_cost', 'extra', 'text', 'epoch'])
def test_forged_planning_payload_cannot_create_a_task(snapshot, store, change):
    data = deepcopy(payload(snapshot))
    if change == 'cost':
        data['cost'] = 2
    elif change == 'float_cost':
        data['cost'] = 1.0
    elif change == 'extra':
        data['execute'] = True
    elif change == 'text':
        data['planning']['text'] += ' changed'
    else:
        data['planning']['control_epoch'] += 1
    before = authority(store), ledger(store)
    with pytest.raises(Denied):
        store.create('owner', 'public-forged-plan', data)
    assert (authority(store), ledger(store)) == before


def test_concurrent_calls_cannot_double_spend_or_duplicate_the_plan(planning, store):
    gateway, _, backend = planning
    task = claim(store, planning)
    entered, release = Event(), Event()
    def block():
        entered.set()
        assert release.wait(5)
    backend.after = block
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(gateway.perform, task['id'], task['fence'])
        try:
            assert entered.wait(3)
            second = pool.submit(gateway.perform, task['id'], task['fence'])
            with pytest.raises(Uncertain):
                second.result(timeout=4)
        finally:
            release.set()
        assert first.result(timeout=5)['stored']
    assert len(backend.calls) == len(actions(store)) == len(drafts(store)) == 1


@pytest.mark.parametrize('settle', [False, True])
def test_context_change_or_billing_settlement_is_not_a_retry_of_an_unknown_result(planning, snapshot, store, settle):
    gateway, _, backend = planning
    task = claim(store, planning)
    backend.drop = True
    with pytest.raises(Uncertain):
        gateway.perform(task['id'], task['fence'])
    if settle:
        gateway.reconcile_usage('owner', actions(store)[0].id, 500, 100, 'PUBLIC_MOCK_BILLING_NOT_LIVE_EVIDENCE')
    store.cancel('owner', task['id'])
    store.abort(task['id'], task['fence'], 'public_mock_test_stop', True, usage_unknown=True)
    classify(store, 'owner', snapshot.request_id, 'lnauto', 1, str(uuid4()))
    current = context(store, 'owner', snapshot.request_id)
    new = create_task(store, 'owner', current)
    with pytest.raises(Denied, match='request_outcome_unresolved'):
        approve(gateway, new)
    assert store.get(new['id'])['state'] == 'WAITING_APPROVAL' and len(backend.calls) == 1


def test_existing_global_ledger_costs_reduce_room_for_another_planning_task(planning, store):
    gateway, _, backend = planning
    gateway.config.daily_nano_rub = 25000
    task = claim(store, planning)
    gateway.perform(task['id'], task['fence'])
    rid = capture(store, 2, 'Second public planning request')
    classify(store, 'owner', rid, 'lnauto', 0, str(uuid4()))
    current = context(store, 'owner', rid)
    next_task = create_task(store, 'owner', current)
    approve(gateway, next_task)
    next_task = store.claim(next_task['id'])
    with pytest.raises(Denied, match='external_budget_limit'):
        gateway.perform(next_task['id'], next_task['fence'])
    assert len(backend.calls) == 1 and len(actions(store)) == 1


def test_coding_settlement_uses_the_original_admitted_tariff(store):
    gateway, task, backend = coding_setup(store)
    old = gateway.client
    def change(request):
        result = backend.handle(request)
        gateway.config.tariff.input_nano_rub += 1
        return result
    gateway.client = httpx.Client(transport=httpx.MockTransport(change), trust_env=False)
    old.close()
    try:
        with pytest.raises(Denied, match='scope_changed'):
            coding_send(gateway, task)
        assert actions(store)[0].actual == 1640
    finally:
        gateway.close()


def test_different_creation_key_cannot_bypass_single_grant_for_exact_context(planning, snapshot, store):
    gateway, _, _ = planning
    task = claim(store, planning)
    gateway.perform(task['id'], task['fence'])
    duplicate = store.create('owner', 'public-manual-duplicate-key', payload(snapshot))
    with pytest.raises(Denied, match='context_already_bound'):
        approve(gateway, duplicate)
    assert store.get(duplicate['id'])['state'] == 'WAITING_APPROVAL'


def test_public_api_cannot_smuggle_creation_or_generic_approval(planning, snapshot, store, client, headers):
    gateway, task, _ = planning
    result = client.post('/api/simulator/commands', headers={**headers['owner'], 'Idempotency-Key': 'public-plan'},
                         json=payload(snapshot))
    assert result.status_code == 422 and result.json() == {'detail': 'invalid_request'}
    result = client.post('/api/tasks/' + task['id'] + '/approve', headers=headers['owner'], json={'version': 1})
    assert result.status_code == 409 and result.json() == {'detail': 'external_scope_approval_required'}
    assert store.get(task['id'])['state'] == 'WAITING_APPROVAL'
    assert gateway.config.mode == 'http_mock'


def test_watchdog_container_absence_does_not_refund_unknown_planning_result(planning, store, monkeypatch):
    gateway, _, backend = planning
    task = claim(store, planning)
    backend.drop = True
    with pytest.raises(Uncertain):
        gateway.perform(task['id'], task['fence'])
    row = {'id': task['id'], 'fence': task['fence'], 'name': 'public-mock-name', 'phase': 'ACTIVE', 'observed': 1}
    class Ledger:
        def record(self, *a, **kw):
            pass
        def stop_attempt(self, *a):
            pass
        def get(self, *a):
            return dict(row)
        def phase(self, tid, fence, phase):
            row['phase'] = phase
        def launch_lock(self, **kw):
            return nullcontext()
        def watchdog(self, *a):
            pass
    class Backend:
        def preflight(self):
            pass
    watchdog = Watchdog(store, Ledger(), Backend())
    monkeypatch.setattr(watchdog.runner, 'stop', lambda *a: True)
    watchdog.emergency(dict(row), 'public_mock_stop')
    with store.transaction() as session:
        assert session.get(Control, 1).reserved == 1 and session.get(Control, 1).halted
    assert actions(store)[0].reserved == gateway.config.tariff.maximum()
    assert gateway.status(task['id'])['result_uncertain']
