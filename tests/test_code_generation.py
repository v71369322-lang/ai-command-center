"""Real PG/F1 and observed mock Telegram to AI proposal to independently checked code.

Provider and Bot API are MockTransport. Local check processes are not rootless acceptance.
"""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from command_center import code_generation as cg, code_workspace as cw
from command_center.code_factory import CodeFactory
from command_center.coding.gateway import Uncertain
from command_center.coding.isolated_entry import execute
from command_center.models import Approval, ExternalAction, ExternalGrant, Task, TelegramDelivery
from command_center.runtime_broker import RuntimeBroker
from command_center.runtime_ledger import RuntimeLedger
from command_center.runtime_policy import RuntimeLimits
from command_center.store import Denied, canonical, digest
from command_center.telegram_code_generation import allowed_markup, ISSUED, CONSUMED
from test_isolated_coding import binding, FIX, SOURCE
import test_plan_acceptance
from test_planning_gateway import config
from test_telegram_readiness import bridge as bridge
from test_telegram_service import configured as configured, update
from test_telegram_plan_acceptance import callback, records
from test_telegram_coding_approval import click as execution_click


@pytest.fixture
def workspace(store, bridge, monkeypatch):
    monkeypatch.setattr(test_plan_acceptance, 'capture', lambda _, value:
                        bridge[0].receive(update(10, value))['inbox_id'])
    body = binding(store, monkeypatch)
    body.pop('replacements')
    value = cw.preview(store, 'owner', body)
    return cw.prepare(store, 'owner', {**body, 'expected_workspace_digest': value['workspace_digest']})


def profile(store):
    with store.transaction() as s:
        now = int(store.now(s).timestamp())
    return cg.CodeProfile(mode='http_mock', enabled=True, tariff=config().tariff,
        available_nano_rub=1_000_000, daily_nano_rub=1_000_000, monthly_nano_rub=1_000_000,
        evidence={'account': 'PUBLIC_MOCK', 'model': 'PUBLIC_MOCK', 'funding': 'PUBLIC_MOCK',
                  'data_sharing': 'PUBLIC_MOCK', 'observed_at': now - 10, 'expires_at': now + 1000})


def install(store):
    p = profile(store)
    cg.configure(store, 'owner', {'profile': p.model_dump(), 'expected_profile_digest': digest(p.model_dump()),
                                'confirmation': 'CONFIGURE_CODE_HTTP_MOCK'})
    return p


def develop(store, bridge, workspace):
    bridge[0].receive(update(20, '/develop 10'))
    with store.transaction() as s:
        return store.view(s.scalar(select(Task).where(Task.payload['kind'].as_string() == cw.KIND)))


def card(bridge, task):
    bridge[0].receive(update(21, '/code_authorize ' + task['id']))
    while bridge[0].deliver_one():
        pass
    i, body = next((i, b) for i, b in reversed(list(enumerate(bridge[1].sent, 1)))
                   if allowed_markup(b.get('reply_markup')))
    return callback(body, i, 22)


def response(seed):
    replacements = {p: value for p, value in cw.validate(seed).items()
                    if p in seed['specification']['scope']['allowed_files'] and not p.startswith('tests/')}
    replacements[SOURCE] = FIX
    return {'id': 'resp_public_code', 'object': 'response', 'status': 'completed',
        'model': config().tariff.model, 'service_tier': 'default',
        'usage': {'input_tokens': 100, 'output_tokens': 50, 'total_tokens': 150},
        'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
            'content': [{'type': 'output_text', 'annotations': [], 'text': canonical(
                {'workspace_digest': digest(seed), 'replacements': replacements})}]}]}


def test_end_to_end_observed_consent_proposal_separate_execution_and_verified_notification(
        store, bridge, workspace, tmp_path):
    p = install(store)
    waiting = develop(store, bridge, workspace)
    assert waiting['state'] == 'WAITING_APPROVAL' and store.claim(waiting['id']) is None
    button = card(bridge, waiting)
    assert 'HTTP mock' in bridge[1].sent[-1]['text']
    bridge[0].receive(button)
    assert len(records(store, CONSUMED)) == 1
    running = store.claim(waiting['id'])
    calls = []

    def handle(req):
        calls.append(json.loads(req.content))
        assert req.headers['Authorization'] == 'Bearer PUBLIC_CODE_HTTP_MOCK_ONLY'
        assert str(req.url) == 'https://api.openai.com/v1/responses'
        return httpx.Response(200, json=response(workspace['workspace']))

    g = cg.CodeGateway(store, p, transport=httpx.MockTransport(handle))
    try:
        result = g.perform(running['id'], running['fence'])
    finally:
        g.close()
    assert len(calls) == 1
    child = store.get(result['execution_task_id'])
    assert child['state'] == 'WAITING_APPROVAL' and store.claim(child['id']) is None
    with store.transaction() as s:
        assert s.get(ExternalGrant, child['id']) is None and s.get(Approval, child['id']) is None
        action = s.scalar(select(ExternalAction))
        assert action.state == 'COMPLETE' and action.actual > 0 and action.reserved == 0
    bridge[0].collect_results()
    bridge[0].receive(update(23, '/develop 10'))
    bridge[0].receive(update(24, '/coding_authorize ' + child['id']))
    bridge[0].receive(execution_click(bridge, 25))
    execution = store.claim(child['id'])
    # Two fresh directories and real Ruff/pytest subprocesses. Production isolation is tested separately.
    a, b = execute(child['payload'], tmp_path / 'first'), execute(child['payload'], tmp_path / 'second')
    assert a == b and a['passed']
    verified = {**b, 'independent_verification': True}
    store.finish(child['id'], execution['fence'], canonical(verified), digest(verified), actual_cost=0)
    bridge[0].collect_results()
    while bridge[0].deliver_one():
        pass
    assert 'Результат независимо проверен' in bridge[1].sent[-1]['text']
    assert store.get(waiting['id'])['state'] == 'SUCCEEDED'


def test_default_disabled_profile_cannot_construct_client_or_grant(store, bridge, workspace, monkeypatch):
    task = develop(store, bridge, workspace)
    bridge[0].receive(update(21, '/code_authorize ' + task['id']))
    assert records(store, ISSUED) == []
    monkeypatch.setattr(httpx, 'Client', lambda *a, **k: pytest.fail('disabled must not create HTTP client'))
    with pytest.raises(Denied, match='disabled_or_expired'):
        cg.CodeGateway(store, cg.CodeProfile())


@pytest.mark.parametrize('attack', ['pending', 'card_body', 'wrong_message', 'replay'])
def test_observed_card_and_replay_guards(store, bridge, workspace, admin, attack):
    install(store)
    task = develop(store, bridge, workspace)
    button = card(bridge, task)
    e = records(store, ISSUED)[0].event
    if attack == 'wrong_message':
        button['callback_query']['message']['message_id'] += 100
    elif attack in {'pending', 'card_body'}:
        with admin.transaction() as s:
            delivery = s.get(TelegramDelivery, e['delivery_id'])
            if attack == 'pending':
                delivery.state = 'NEW'
            else:
                delivery.body = {**delivery.body, 'text': 'changed'}
    else:
        bridge[0].receive(button)
        button['update_id'] += 100
        bridge[0].receive(button)
        assert len(records(store, CONSUMED)) == 1
        return
    with pytest.raises(Denied):
        bridge[0].receive(button)
    assert store.get(task['id'])['state'] == 'WAITING_APPROVAL'


@pytest.mark.parametrize('attack', ['tests', 'pin', 'model', 'tools', 'usage', 'noop'])
def test_provider_response_cannot_expand_scope(workspace, attack):
    data = response(workspace['workspace'])
    content = data['output'][0]['content'][0]
    proposal = json.loads(content['text'])
    if attack == 'tests':
        proposal['replacements']['tests/test_example.py'] = 'pass\n'
    elif attack == 'pin':
        proposal['workspace_digest'] = '0' * 64
    elif attack == 'model':
        data['model'] = 'wrong-model'
    elif attack == 'tools':
        data['output'].append({'type': 'function_call'})
    elif attack == 'usage':
        data['usage']['total_tokens'] = 999
    else:
        proposal['replacements'][SOURCE] = cw.validate(workspace['workspace'])[SOURCE]
    content['text'] = canonical(proposal)
    with pytest.raises(Denied):
        cg.decode(data, workspace['workspace'], config().tariff)


def test_modified_workspace_and_non_owner_cannot_register(store, workspace):
    bad = deepcopy(workspace['workspace'])
    bad['context']['text'] = 'changed'
    with pytest.raises(Denied):
        cw.validate(bad)
    with pytest.raises(Denied, match='owner'):
        cw.preview(store, 'operator', {})


def approved(store, bridge, workspace):
    p = install(store)
    task = develop(store, bridge, workspace)
    bridge[0].receive(card(bridge, task))
    return p, task


@pytest.mark.parametrize('attack', ['expired', 'cancel', 'profile', 'consent', 'payload', 'body'])
def test_revocation_before_key_read_has_no_http_or_money(store, bridge, workspace, admin, monkeypatch, attack):
    p, task = approved(store, bridge, workspace)
    running = store.claim(task['id'])
    g = cg.CodeGateway(store, p, transport=httpx.MockTransport(lambda req: pytest.fail('no provider I/O')))
    monkeypatch.setattr(g.credentials, 'get', lambda *a: pytest.fail('no key read'))
    body = cg.request_document(workspace['workspace'], p.tariff)
    if attack == 'cancel':
        store.cancel('owner', task['id'])
    elif attack == 'expired':
        with admin.transaction() as s:
            s.get(Approval, task['id']).expires_at = store.now(s) - timedelta(seconds=1)
    elif attack == 'profile':
        cg.configure(store, 'owner', {'profile': cg.CodeProfile().model_dump(),
            'expected_previous_digest': digest(p.model_dump()),
            'expected_profile_digest': digest(cg.CodeProfile().model_dump()), 'confirmation': 'KEEP_CODE_AI_DISABLED'})
    elif attack == 'consent':
        event = records(store, CONSUMED)[0].event
        from command_center.models import TelegramInbox
        with admin.transaction() as s:
            s.get(TelegramInbox, event['inbox_id']).state = 'RECEIVED'
    elif attack == 'payload':
        with admin.transaction() as s:
            row = s.get(Task, task['id'])
            row.payload = {**row.payload, 'kind': 'render'}
            row.payload_hash = digest(row.payload)
    else:
        body['store'] = True
    try:
        with pytest.raises(Denied):
            g.request(task['id'], running['fence'], cg.KEY, 'openai', 'POST', '/v1/responses', body)
        with store.transaction() as s:
            assert s.scalar(select(ExternalAction)) is None
    finally:
        g.close()


@pytest.mark.parametrize('attack', ['lost', 'invalid_response', 'cancel_during_response'])
def test_uncertain_call_never_retries_or_creates_execution(store, bridge, workspace, attack):
    p, task = approved(store, bridge, workspace)
    running = store.claim(task['id'])
    calls = []

    def handle(req):
        calls.append(req)
        if attack == 'lost':
            raise httpx.ReadTimeout('PUBLIC_MOCK_LOSS')
        data = response(workspace['workspace'])
        if attack == 'invalid_response':
            data['output'][0]['content'][0]['text'] = 'invalid JSON'
        else:
            store.cancel('owner', task['id'])
        return httpx.Response(200, json=data)

    g = cg.CodeGateway(store, p, transport=httpx.MockTransport(handle))
    try:
        for _ in range(2):
            with pytest.raises((Denied, Uncertain)):
                g.perform(task['id'], running['fence'])
        assert len(calls) == 1
        with store.transaction() as s:
            assert s.scalar(select(Task).where(Task.payload['kind'].as_string() == 'isolated_coding')) is None
            action = s.scalar(select(ExternalAction))
            if attack == 'cancel_during_response':
                assert action.state == 'COMPLETE' and action.actual > 0 and action.reserved == 0
            else:
                assert action.reserved > 0
    finally:
        g.close()


def test_concurrent_click_consumes_card_once(store, bridge, workspace):
    install(store)
    task = develop(store, bridge, workspace)
    button = card(bridge, task)
    other = deepcopy(button)
    other['update_id'] += 1
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(bridge[0].receive, [button, other]))
    assert len(records(store, CONSUMED)) == 1


def test_profile_configuration_is_not_api_or_execution_approval(store, client, headers, bridge, workspace):
    p = install(store)
    task = develop(store, bridge, workspace)
    r = client.post('/api/tasks/' + task['id'] + '/approve', json={'version': 1, 'seconds': 120},
                    headers=headers['owner'])
    assert r.status_code == 409 and r.json()['detail'] == 'external_scope_approval_required'
    assert store.claim(task['id']) is None
    with store.transaction() as s:
        assert s.get(Approval, task['id']) is None and s.get(ExternalGrant, task['id']) is None
    # Production factory never routes a mock profile to real transport.
    with pytest.raises(Denied, match='live_profile_not_connected'):
        CodeFactory(store).preflight()
    assert p.mode == 'http_mock'


@pytest.mark.parametrize('failure', [None, 'watchdog', 'host', 'factory'])
def test_broker_composes_same_http_lifecycle_without_executor_or_key_handoff(
        store, bridge, workspace, tmp_path, failure):
    p, task = approved(store, bridge, workspace)
    ledger = RuntimeLedger(tmp_path / 'runtime.sqlite')
    ledger.watchdog()
    ledger.worker_beat(store.settings.source_revision)
    calls = []

    def preflight(*args):
        if failure == 'host':
            raise Denied('PUBLIC_HOST_REJECTED')

    class Factory:
        def preflight(self):
            if failure == 'factory':
                raise Denied('PUBLIC_FACTORY_REJECTED')

        def __call__(self, guard):
            def handle(req):
                calls.append(req)
                return httpx.Response(200, json=response(workspace['workspace']))
            return cg.CodeGateway(store, p, transport=httpx.MockTransport(handle))

    backend = SimpleNamespace(mode='rootless-required', preflight=lambda: None)
    host = SimpleNamespace(preflight=preflight, guard=lambda *a: True)
    service = RuntimeBroker(store, ledger, backend, RuntimeLimits(), planning_host=host, code_factory=Factory())
    if failure == 'watchdog':
        ledger.watchdog_ready = lambda *a: False
    try:
        if failure:
            with pytest.raises(Denied):
                service.submit(task['id'], store.settings.source_revision)
            assert store.get(task['id'])['state'] == 'READY'
            with store.transaction() as s:
                assert s.get(Approval, task['id']).used is False
            assert not calls
        else:
            service.submit(task['id'], store.settings.source_revision)
            service.last_future.result(timeout=20)
            row = ledger.get(task['id'], 1)
            assert row['kind'] == 'planning_http' and row['returned'] and row['phase'] == 'DONE'
            assert len(calls) == 1 and store.get(task['id'])['state'] == 'SUCCEEDED'
    finally:
        service.pool.shutdown(wait=True)


def test_production_factory_uses_installed_credential_reference_and_exact_host_binding(store, monkeypatch):
    from command_center import code_factory, planning_profile
    from command_center.planning_admission import PlanningProfile
    p = profile(store)
    runtime = {'source_revision': store.settings.source_revision, 'binding_digest': 'a' * 64,
               'credential_sha256': 'b' * 64, 'credential_ref': 'planning-openai'}
    installed = PlanningProfile(tariff=p.tariff, evidence=p.evidence, available_nano_rub=p.available_nano_rub,
        daily_nano_rub=p.daily_nano_rub, monthly_nano_rub=p.monthly_nano_rub, runtime=runtime)
    monkeypatch.setattr(planning_profile, 'load', lambda: installed)
    monkeypatch.setattr(code_factory, 'load', lambda: installed)
    live = cg.CodeProfile.model_validate({**p.model_dump(), 'mode': 'live', 'live_authorized': True,
        'runtime': runtime, 'installation_profile_digest': digest(installed.model_dump())})
    cg.configure(store, 'owner', {'profile': live.model_dump(), 'expected_profile_digest': digest(live.model_dump()),
                                'confirmation': 'ENABLE_PAID_CODE_GENERATION'})
    guards = []

    def constructor(store_arg, profile_arg, *, credentials, runtime_guard):
        assert store_arg is store and profile_arg == live
        assert credentials.profile == installed
        assert runtime_guard() is True
        return 'PUBLIC_FACTORY_CONSTRUCTOR_ONLY_NO_IO'

    monkeypatch.setattr(code_factory, 'CodeGateway', constructor)
    assert CodeFactory(store)(lambda binding: guards.append(binding) or True) == 'PUBLIC_FACTORY_CONSTRUCTOR_ONLY_NO_IO'
    assert guards == [runtime]


def test_reply_failure_rolls_back_financial_and_f1_approval(store, bridge, workspace, monkeypatch):
    install(store)
    task = develop(store, bridge, workspace)
    button = card(bridge, task)
    monkeypatch.setattr(bridge[0], 'finish', lambda *a, **k: (_ for _ in ()).throw(Denied('reply_failed')))
    with pytest.raises(Denied, match='reply_failed'):
        bridge[0].receive(button)
    assert records(store, CONSUMED) == [] and store.get(task['id'])['state'] == 'WAITING_APPROVAL'
    with store.transaction() as s:
        assert s.get(Approval, task['id']) is None and s.get(ExternalGrant, task['id']) is None


def test_finish_failure_keeps_complete_response_without_partial_child(store, bridge, workspace, monkeypatch):
    p, task = approved(store, bridge, workspace)
    running = store.claim(task['id'])
    original = store.audit

    def fail(session, kind, actor, *args, **kwargs):
        if kind == cg.BOUND:
            raise Denied('compose_failed')
        return original(session, kind, actor, *args, **kwargs)

    monkeypatch.setattr(store, 'audit', fail)
    g = cg.CodeGateway(store, p, transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json=response(workspace['workspace']))))
    try:
        with pytest.raises(Denied, match='compose_failed'):
            g.perform(task['id'], running['fence'])
        with store.transaction() as s:
            assert s.scalar(select(Task).where(Task.payload['kind'].as_string() == 'isolated_coding')) is None
            assert s.scalar(select(ExternalAction)).state == 'COMPLETE'
        assert store.get(task['id'])['state'] == 'RUNNING'
    finally:
        g.close()


def test_decoded_credential_echo_stays_uncertain(store, bridge, workspace):
    p, task = approved(store, bridge, workspace)
    running = store.claim(task['id'])
    data = response(workspace['workspace'])
    output = data['output'][0]['content'][0]
    value = json.loads(output['text'])
    value['replacements'][SOURCE] = FIX + '# PUBLIC_CODE_HTTP_MOCK_ONLY\n'
    raw = canonical(value)
    raw = raw.replace('PUBLIC_CODE_HTTP_MOCK_ONLY', ''.join('\\u%04x' % ord(c) for c in 'PUBLIC_CODE_HTTP_MOCK_ONLY'))
    output['text'] = raw
    g = cg.CodeGateway(store, p, transport=httpx.MockTransport(lambda req: httpx.Response(200, json=data)))
    try:
        with pytest.raises(Uncertain):
            g.perform(task['id'], running['fence'])
        with store.transaction() as s:
            action = s.scalar(select(ExternalAction))
            assert action.state == 'UNCERTAIN' and action.reserved > 0 and 'response' not in action.evidence
            assert s.scalar(select(Task).where(Task.payload['kind'].as_string() == 'isolated_coding')) is None
    finally:
        g.close()


def test_pending_command_cannot_select_new_profile(store, bridge, workspace, monkeypatch):
    p = install(store)
    task = develop(store, bridge, workspace)
    original = bridge[0]._apply_pending
    with monkeypatch.context() as m:
        m.setattr(bridge[0], '_apply_pending', lambda *args: None)
        bridge[0].receive(update(21, '/code_authorize ' + task['id']))
    new = cg.CodeProfile.model_validate({**p.model_dump(), 'available_nano_rub': p.available_nano_rub + 1})
    cg.configure(store, 'owner', {'profile': new.model_dump(), 'expected_profile_digest': digest(new.model_dump()),
        'expected_previous_digest': digest(p.model_dump()), 'confirmation': 'CONFIGURE_CODE_HTTP_MOCK'})
    original(bridge[0].profile + ':21', {'kind': 'code_authorize_request', 'task': task['id']})
    assert records(store, ISSUED) == [] and store.get(task['id'])['state'] == 'WAITING_APPROVAL'
