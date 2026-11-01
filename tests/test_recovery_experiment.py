"""Separate one-call authority over an anchored, closed first failure. No provider I/O."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from threading import Event, Thread
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import select

from command_center.api import create_app
from command_center.coding.first_experiment import (EXPERIMENT_ID, RECOVERY_ID, Evidence,
    REQUIRED, create_task, task_payload, quote)
from command_center.coding.gateway import Gateway
from command_center.coding.http_contract import request_document
from command_center.coding.integration_config import IntegrationConfig
from command_center.coding.recovery import RecoveryExperiment
from command_center.coding.spec import BASE_SHA, CORRECT, INITIAL, OBJECTIVE, REPOSITORY, TEST_SOURCE
from command_center.models import Approval, Audit, ExternalAction, ExternalGrant, Outbox, Task
from command_center.store import Denied, digest
from command_center.runtime_broker import RuntimeBroker
from command_center.runtime_ledger import RuntimeLedger
from command_center.runtime_policy import RuntimeBackend, RuntimeLimits
from command_center.telegram_experiment_authorize import allowed_markup, parse_callback
from test_first_experiment import experiment_config
from test_telegram_readiness import bridge as bridge
from test_telegram_service import OWNER, configured as configured, update
from test_telegram_task_status import authority
from f2_http_support import Credentials, FakeHTTP

LOOP = ('def sum_positive(values):\n    total = 0\n    for value in values:\n'
        '        if value > 0:\n            total += value\n    return total\n')


@pytest.fixture
def recovery(store, tmp_path, monkeypatch, request):
    current_settings = store.settings
    old_revision = 'd' * 40 if current_settings.source_revision != 'd' * 40 else 'e' * 40
    store.settings = replace(current_settings, source_revision=old_revision)
    mode = getattr(request, 'param', 'live')
    original_config = experiment_config(live=mode != 'http_mock')
    with store.transaction() as session:
        until = store.now(session) + timedelta(minutes=20)
    original_config.first_experiment.evidence = {
        name: Evidence(reference='PUBLIC_TEST_DECLARATION_NOT_LIVE_EVIDENCE', expires_at=until.isoformat())
        for name in REQUIRED}
    original = create_task(store, 'owner')
    budget = original_config.tariff.maximum() * 2
    if mode == 'small_envelope':
        budget = original_config.tariff.maximum() + original_config.tariff.cost(100, 32) - 1
    Gateway.authorize_configured(store, original_config, 'owner', original['id'], original['version'],
        budget_nano_rub=budget, final_confirmation=True)
    claimed = store.claim(original['id'])
    store.coding_stage(original['id'], claimed['fence'], 'provider_running', iteration=1)
    data = {'id': 'resp_public_failed_first', 'model': original_config.tariff.model, 'status': 'completed',
            'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                        'content': [{'type': 'output_text', 'text': json.dumps({'source': LOOP})}]}],
            'usage': {'input_tokens': 100, 'output_tokens': 32, 'total_tokens': 132}}
    with store.transaction() as session:
        now = store.now(session)
        action = ExternalAction(id=str(uuid4()), task_id=original['id'], key=original['id'] + ':ai/1',
            kind='openai', request_hash='c' * 64, state='COMPLETE', reserved=0,
            actual=original_config.tariff.cost(100, 32), created_at=now,
            evidence={'method': 'POST', 'response': data, 'usage': data['usage'],
                      'settled_day': now.strftime('%Y-%m-%d'), 'settled_month': now.strftime('%Y-%m')})
        session.add(action)
        store.audit(session, 'external_response', 'gateway', original['id'], action_id=action.id,
                    ledger_digest=Gateway.action_digest(action), response_hash=digest(data))
        original_grant = session.get(ExternalGrant, original['id']).digest
        action_id, actual = action.id, action.actual
    store.coding_stage(original['id'], claimed['fence'], 'external_stopped',
                       failure='provider_or_verifier_contract_rejected', summary='PUBLIC_FAILED_CONTRACT_FIXTURE')
    store.abort(original['id'], claimed['fence'], 'external_coding_blocked', True)
    store.settings = current_settings
    config = original_config.model_copy(deep=True)
    config.first_experiment = RecoveryExperiment.model_validate({**original_config.first_experiment.model_dump(),
        'id': RECOVERY_ID, 'original_task_id': original['id'], 'original_grant_digest': original_grant})
    path = tmp_path / 'recovery-config.json'

    def save():
        raw = json.dumps({**config.model_dump(), 'credential_files': config.credential_files}).encode()
        path.write_bytes(raw)
        path.chmod(0o600)
        monkeypatch.setenv('F2_INTEGRATION_CONFIG_FILE', str(path))
        monkeypatch.setenv('F2_INTEGRATION_CONFIG_SHA256', hashlib.sha256(raw).hexdigest())
    save()
    return config, original['id'], action_id, actual, save


def proof(store, config):
    with store.transaction() as session:
        return config.first_experiment.verify_parent(store, session, config)


def test_recovery_configuration_preserves_type_and_initial_profile_hash(recovery):
    config = recovery[0]
    loaded = IntegrationConfig.load()
    assert isinstance(loaded.first_experiment, RecoveryExperiment)
    assert loaded.first_experiment.call_limit == 1
    assert loaded.first_experiment.original_task_id == recovery[1]
    initial = experiment_config()
    raw = {**initial.model_dump(), 'credential_files': initial.credential_files}
    assert digest(IntegrationConfig.model_validate(raw).model_dump()) == digest(initial.model_dump())
    assert quote('112.5', '0', calls=1)['max_nano_rub'] == 34786800000
    assert config.first_experiment.report()['max_repairs'] == 0


def test_prepare_is_idempotent_and_preserves_old_task_and_financial_ledger(store, recovery):
    config, old_id, action_id, actual, _ = recovery
    before = store.get(old_id)
    one = create_task(store, 'owner', experiment_id=RECOVERY_ID)
    two = create_task(store, 'owner', experiment_id=RECOVERY_ID)
    assert one['id'] == two['id'] and one['state'] == 'WAITING_APPROVAL'
    assert one['payload'] == task_payload(RECOVERY_ID)
    assert store.get(old_id) == before
    with store.transaction() as session:
        assert session.get(ExternalAction, action_id).actual == actual
        assert session.get(ExternalGrant, one['id']) is None and session.get(Approval, one['id']) is None
    assert proof(store, config)['actual_nano_rub'] == actual


def test_recovery_grant_is_new_one_call_authority_and_itself_single_use(store, recovery):
    config = recovery[0]
    one = create_task(store, 'owner', experiment_id=RECOVERY_ID)
    budget = config.tariff.maximum()
    Gateway.authorize_configured(store, config, 'owner', one['id'], one['version'], budget_nano_rub=budget,
                                 final_confirmation=True, expected_config_hash=digest(config.model_dump()))
    with store.transaction() as session:
        grant = session.get(ExternalGrant, one['id'])
        assert grant.document['max_calls'] == 1
        assert grant.document['recovery_parent']['task_id'] == recovery[1]
        assert session.get(ExternalGrant, recovery[1]).document['experiment_id'] == EXPERIMENT_ID
    two = store.create('owner', 'another-recovery-fixture', task_payload(RECOVERY_ID))
    with pytest.raises(Denied, match='already_bound'):
        Gateway.authorize_configured(store, config, 'owner', two['id'], two['version'],
                                     budget_nano_rub=budget, final_confirmation=True)
    assert store.get(two['id'])['state'] == 'WAITING_APPROVAL'


@pytest.mark.parametrize('change', ['no_final_consent', 'wrong_profile', 'two_calls', 'two_reservations'])
def test_recovery_cannot_inherit_or_expand_the_initial_consent(store, recovery, change):
    config = recovery[0]
    task = create_task(store, 'owner', experiment_id=RECOVERY_ID)
    budget = config.tariff.maximum()
    if change == 'two_calls':
        payload = task_payload(RECOVERY_ID)
        payload['coding'].update(max_iterations=2, max_units=2)
        payload['cost'] = 2
        task = store.create('owner', 'expanded-recovery-fixture', payload)
    if change == 'two_reservations':
        budget *= 2
    with pytest.raises(Denied):
        Gateway.authorize_configured(store, config, 'owner', task['id'], task['version'],
            budget_nano_rub=budget, final_confirmation=change != 'no_final_consent',
            expected_config_hash='0' * 64 if change == 'wrong_profile' else digest(config.model_dump()))
    assert store.get(task['id'])['state'] == 'WAITING_APPROVAL'


@pytest.mark.parametrize('change', ['state', 'reason', 'evidence', 'fence', 'grant', 'same_source',
                                   'uncertain', 'reserved', 'two_paid_calls', 'publisher_write', 'decoded_ok',
                                   'parent_attempts', 'original_reserved', 'iteration', 'completed_sandbox', 'unanchored_action'])
def test_recovery_parent_must_be_closed_anchored_and_have_only_one_failed_source_response(store, recovery, change):
    config, old_id, action_id, _, _ = recovery
    with store.transaction() as session:
        parent = session.get(Task, old_id)
        action = session.get(ExternalAction, action_id)
        if change == 'state':
            parent.state = 'RECONCILING'
        elif change == 'reason':
            parent.reason = 'different_failure'
        elif change == 'evidence':
            parent.coding_evidence = {**parent.coding_evidence, 'summary': 'tampered fixture'}
        elif change == 'fence':
            parent.fence += 1
        elif change == 'parent_attempts':
            parent.attempts += 1
        elif change == 'original_reserved':
            parent.reserved = 1
        elif change == 'iteration':
            parent.coding_evidence = {**parent.coding_evidence, 'iteration': 2}
        elif change == 'completed_sandbox':
            parent.coding_evidence = {**parent.coding_evidence, 'agent_result': {}}
        elif change == 'unanchored_action':
            action.actual += 1
        elif change == 'grant':
            config.first_experiment.original_grant_digest = '0' * 64
        elif change == 'same_source':
            store.settings = replace(store.settings, source_revision=session.get(ExternalGrant, old_id).document['revision'])
        elif change in {'uncertain', 'reserved', 'decoded_ok'}:
            if change == 'uncertain':
                action.state = 'UNCERTAIN'
            elif change == 'reserved':
                action.reserved = 1
            else:
                data = deepcopy(action.evidence)
                data['response']['output'][0]['content'][0]['text'] = json.dumps({'source': CORRECT})
                action.evidence = data
            store.audit(session, 'external_interrupted', 'gateway', old_id, action_id=action.id,
                        ledger_digest=Gateway.action_digest(action))
        else:
            extra = ExternalAction(id=str(uuid4()), task_id=old_id, key=old_id + ':extra',
                kind='openai' if change == 'two_paid_calls' else 'github', state='COMPLETE',
                actual=0, reserved=0, request_hash='f' * 64, created_at=store.now(session),
                evidence={'method': 'POST', 'response': {}})
            session.add(extra)
            store.audit(session, 'external_response', 'gateway', old_id, action_id=extra.id,
                        ledger_digest=Gateway.action_digest(extra))
    with pytest.raises(Denied):
        proof(store, config)


def test_new_authority_rechecks_parent_before_any_external_action(store, recovery):
    config = recovery[0]
    task = create_task(store, 'owner', experiment_id=RECOVERY_ID)
    Gateway.authorize_configured(store, config, 'owner', task['id'], task['version'],
        budget_nano_rub=config.tariff.maximum(), final_confirmation=True)
    claimed = store.claim(task['id'])
    with store.transaction() as session:
        session.get(Task, recovery[1]).reason = 'changed_after_consent'
    gateway = Gateway(store, config)
    try:
        with store.transaction() as session, pytest.raises(Denied):
            gateway.authority(session, task['id'], claimed['fence'])
        with store.transaction() as session:
            assert not session.scalar(select(ExternalAction).where(ExternalAction.task_id == task['id']))
    finally:
        gateway.close()


def test_recovery_api_requires_its_own_typed_confirmation(store, recovery, headers):
    config = recovery[0]
    with TestClient(create_app(store.settings, gateway_factory=lambda: Gateway(store, config))) as client:
        task = client.post('/api/experiments/recovery/task', headers=headers['owner']).json()
        assert client.post('/api/experiments/recovery/task', headers=headers['owner']).json()['id'] == task['id']
        status = client.get('/api/experiments/first', headers=headers['owner']).json()
        assert status['id'] == RECOVERY_ID and status['task_state']['id'] == task['id']
        body = {'version': task['version'], 'budget_nano_rub': config.tariff.maximum(),
                'profile_hash': digest(config.model_dump()), 'confirmation': 'AUTHORIZE_FIRST_PAID_EXPERIMENT'}
        url = '/api/experiments/recovery/' + task['id'] + '/authorize'
        assert client.post(url, json=body, headers=headers['owner']).status_code == 422
        body['confirmation'] = 'AUTHORIZE_ONE_PAID_RECOVERY'
        assert client.post(url, json=body, headers=headers['agent']).status_code == 409
        assert client.post(url, json=body, headers=headers['owner']).status_code == 200


@pytest.mark.parametrize('concurrent', [False, True])
def test_recovery_telegram_has_separate_observed_card_and_idempotent_consent(bridge, store, recovery, concurrent):
    service, fake = bridge
    config = recovery[0]
    service.receive(update(10, '/prepare_recovery'))
    service.receive(update(11, '/watch_recovery'))
    before = authority(store)
    service.receive(update(12, '/authorize_recovery'))
    assert authority(store) == before
    while service.deliver_one():
        pass
    number, body = next((i, b) for i, b in reversed(list(enumerate(fake.sent, 1)))
                        if allowed_markup(b.get('reply_markup')))
    token = body['reply_markup']['inline_keyboard'][0][0]['callback_data']
    assert token.startswith('rx:') and 'Один AI-вызов' in body['text']
    assert recovery[1] in body['text'] and 'исходной задачи' in body['text']
    assert parse_callback(token)['kind'] == 'recovery_authorize_confirm'
    callback = {'update_id': 13, 'callback_query': {'id': 'public-recovery-click',
        'from': {'id': OWNER, 'is_bot': False}, 'data': token,
        'message': {'message_id': number, 'chat': {'id': OWNER, 'type': 'private'}}}}
    if concurrent:
        another = deepcopy(callback)
        another['update_id'] = 14
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(service.receive, [callback, another]))
    else:
        service.receive(callback)
    service.receive(callback)
    with store.transaction() as session:
        grants = session.scalars(select(ExternalGrant)).all()
        assert len(grants) == 2
        grant = next(g for g in grants if g.document['experiment_id'] == RECOVERY_ID)
        assert grant.document['max_calls'] == 1 and grant.document['budget'] == config.tariff.maximum()
        assert session.get(Task, recovery[1]).state == 'FAILED'
        assert len(session.scalars(select(ExternalAction)).all()) == 1
        assert len(session.scalars(select(Outbox).where(Outbox.task_id == grant.task_id)).all()) == 1
        assert sum(a.event['kind'] == 'telegram_recovery_approval_consumed'
                   for a in session.scalars(select(Audit))) == 1


def test_gateway_blocks_second_recovery_call_before_io_and_preserves_parent_cost(store, recovery):
    config = recovery[0]
    task = create_task(store, 'owner', experiment_id=RECOVERY_ID)
    Gateway.authorize_configured(store, config, 'owner', task['id'], task['version'],
        budget_nano_rub=config.tariff.maximum(), final_confirmation=True)
    claimed = store.claim(task['id'])
    fake = FakeHTTP(model=config.tariff.model)
    gateway = Gateway(store, config, credentials=Credentials())
    gateway.runtime_guard = lambda: True  # Explicit test-only runtime attestation; production requires the real ledger guard.
    gateway.client.close()
    gateway.client = httpx.Client(transport=httpx.MockTransport(fake.handle))
    context = {'repository': REPOSITORY, 'objective': OBJECTIVE, 'base_sha': BASE_SHA,
               'source': INITIAL, 'acceptance': TEST_SOURCE, 'checks': None, 'attempt': 1}
    try:
        body = request_document(context, config.tariff.model, config.tariff.max_output_tokens)
        gateway.request(task['id'], claimed['fence'], 'ai/1', 'openai', 'POST', '/v1/responses', body)
        context['attempt'] = 2
        body = request_document(context, config.tariff.model, config.tariff.max_output_tokens)
        with pytest.raises(Denied, match='external_iteration_limit'):
            gateway.request(task['id'], claimed['fence'], 'ai/2', 'openai', 'POST', '/v1/responses', body)
        assert fake.ai_calls == 1
        with store.transaction() as session:
            actions = session.scalars(select(ExternalAction)).all()
            assert len(actions) == 2 and all(a.state == 'COMPLETE' and a.reserved == 0 for a in actions)
            assert session.get(ExternalAction, recovery[2]).actual == recovery[3]
    finally:
        gateway.close()


@pytest.mark.parametrize('recovery', ['small_envelope'], indirect=True)
def test_recovery_cumulative_bound_cannot_exceed_original_approved_envelope(store, recovery):
    config = recovery[0]
    with pytest.raises(Denied, match='recovery_cumulative_budget'):
        proof(store, config)


@pytest.mark.parametrize('attack', ['wrong_scope', 'expired', 'not_observed'])
def test_recovery_card_cannot_be_moved_to_first_scope_or_used_stale_or_unseen(bridge, store, recovery, monkeypatch, attack):
    service, fake = bridge
    service.receive(update(20, '/prepare_recovery'))
    service.receive(update(21, '/authorize_recovery'))
    if attack == 'not_observed':
        from command_center.models import TelegramDelivery
        with store.transaction() as session:
            body = next(d.body for d in session.scalars(select(TelegramDelivery))
                        if allowed_markup(d.body.get('reply_markup')))
        number = 999
    else:
        while service.deliver_one():
            pass
        number, body = next((i, b) for i, b in reversed(list(enumerate(fake.sent, 1)))
                            if allowed_markup(b.get('reply_markup')))
    token = body['reply_markup']['inline_keyboard'][0][0]['callback_data']
    if attack == 'wrong_scope':
        token = 'fx:' + token[3:]
    if attack == 'expired':
        with store.transaction() as session:
            later = store.now(session) + timedelta(minutes=3)
        monkeypatch.setattr(store, 'now', lambda s: later)
    callback = {'update_id': 22, 'callback_query': {'id': 'public-recovery-bad-card',
        'from': {'id': OWNER, 'is_bot': False}, 'data': token,
        'message': {'message_id': number, 'chat': {'id': OWNER, 'type': 'private'}}}}
    with pytest.raises(Denied):
        service.receive(callback)
    with store.transaction() as session:
        assert len(session.scalars(select(ExternalGrant)).all()) == 1
        assert len(session.scalars(select(ExternalAction)).all()) == 1


def test_recovery_cancel_and_status_do_not_require_a_working_profile(bridge, store, recovery, monkeypatch):
    service, fake = bridge
    service.receive(update(30, '/prepare_recovery'))
    monkeypatch.setenv('F2_INTEGRATION_CONFIG_FILE', '/missing/public-fixture-only.json')
    service.receive(update(31, '/cancel_recovery'))
    service.receive(update(32, '/recovery'))
    while service.deliver_one():
        pass
    assert 'отменена' in fake.sent[-1]['text']
    assert '/cancel_recovery' in fake.sent[-1]['text']
    assert store.get(recovery[1])['state'] == 'FAILED'


def test_recovery_watch_is_explicit_separate_and_sends_one_scoped_notice(bridge, store, recovery):
    service, fake = bridge
    service.receive(update(40, '/prepare_recovery'))
    service.receive(update(41, '/watch_recovery'))
    service.receive(update(42, '/cancel_recovery'))
    service.collect_results()
    service.collect_results()
    while service.deliver_one():
        pass
    notices = [body['text'] for body in fake.sent if body['text'].startswith('Уведомление восстановительного')]
    assert len(notices) == 1 and '/recovery' in notices[0]
    assert 'отменена' in notices[0]
    assert store.get(recovery[1])['state'] == 'FAILED'


@pytest.mark.parametrize('recovery', ['http_mock'], indirect=True)
def test_recovery_dry_run_real_sandboxes(store, recovery, tmp_path):
    config = recovery[0]
    class OneCallHTTP(FakeHTTP):
        def dispatch(self, request):
            result = super().dispatch(request)
            if request.url.host == 'api.openai.com':
                result['output'][0]['content'][0]['text'] = json.dumps({'source': CORRECT})
            return result
    fake = OneCallHTTP(model=config.tariff.model)
    def gateway():
        return Gateway(store, config, transport=httpx.MockTransport(fake.handle), credentials=Credentials())
    task = create_task(store, 'owner', experiment_id=RECOVERY_ID)
    Gateway.authorize_configured(store, config, 'owner', task['id'], task['version'],
                                 budget_nano_rub=config.tariff.maximum())
    ledger = RuntimeLedger(tmp_path / 'recovery.sqlite')
    ledger.watchdog()
    stop = Event()
    def heartbeat():
        while not stop.wait(.5):
            ledger.watchdog()
    monitor = Thread(target=heartbeat, daemon=True)
    monitor.start()
    service = RuntimeBroker(store, ledger, RuntimeBackend(mode='cloud-rootful-test'), RuntimeLimits(), gateway)
    try:
        service.submit(task['id'], store.settings.source_revision)
        service.last_future.result(timeout=35)
        result = store.get(task['id'])
        assert result['state'] == 'SUCCEEDED', result['coding'].get('failure')
        assert len(result['coding']['test_runs']) == 1 and result['coding']['test_runs'][0]['checks']['passed']
        assert result['coding']['independent_proof']
        assert fake.ai_calls == len(fake.prs) == 1
        assert result['coding']['pr']['mode'] == 'http_mock' and result['coding']['pr']['published'] is False
        assert store.get(recovery[1])['state'] == 'FAILED'
        with store.transaction() as session:
            assert session.get(ExternalAction, recovery[2]).actual == recovery[3]
    finally:
        stop.set()
        monitor.join(timeout=2)
        service.pool.shutdown(wait=True)
