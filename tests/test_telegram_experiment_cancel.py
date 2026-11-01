"""Actual PG + strict mocks; no live task, provider, credentials or server access."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select, text

from command_center.coding.gateway import Gateway
from command_center.coding.integration_config import FileCredentials
from command_center.models import Approval, Audit, Control, Task, TelegramInbox
from command_center.store import Denied
from command_center.telegram_bridge import TelegramBridge
from test_readiness import send
from test_telegram_experiment import active as active, create
from test_telegram_readiness import bridge as bridge, ledger
from test_telegram_service import OWNER, configured as configured, update
from test_telegram_task_status import authority


def cancel(bridge, uid=1):
    service, fake = bridge
    service.receive(update(uid, '/cancel_experiment'))
    while service.deliver_one():
        pass
    return fake.sent[-1]['text']


def defer(bridge, monkeypatch, uid=1):
    service = bridge[0]
    with monkeypatch.context() as patch:
        patch.setattr(service, '_apply_pending', lambda *a: (_ for _ in ()).throw(RuntimeError('fixture crash')))
        with pytest.raises(RuntimeError):
            service.receive(update(uid, '/cancel_experiment'))


def test_missing_at_intake_never_cancels_task_created_afterward(bridge, store, monkeypatch):
    defer(bridge, monkeypatch)
    task = create(store)
    before = authority(store), ledger(store)
    bridge[0].resume_pending()
    assert bridge[0].deliver_one()['state'] == 'SENT'
    assert 'ещё не был создан' in bridge[1].sent[-1]['text']
    assert store.get(task['id'])['state'] == 'WAITING_APPROVAL'
    assert (authority(store), ledger(store)) == before


@pytest.mark.parametrize('state', ['WAITING_APPROVAL', 'READY', 'RUNNING', 'VERIFYING', 'RECONCILING', 'CANCEL_REQUESTED'])
def test_shortcut_uses_existing_f1_state_transition_only(bridge, store, state):
    task = create(store)
    with store.transaction() as session:
        row = session.get(Task, task['id'])
        row.state = state
    before = ledger(store)
    body = cancel(bridge)
    expected = 'CANCELLED' if state in {'WAITING_APPROVAL', 'READY'} else 'CANCEL_REQUESTED'
    assert store.get(task['id'])['state'] == expected
    assert 'Намерение отмены' in body and 'спорные резервы сохраняются' in body
    assert ledger(store) == before


@pytest.mark.parametrize('state', ['SUCCEEDED', 'FAILED', 'CANCELLED', 'SECURITY_BLOCKED'])
def test_terminal_history_and_authority_are_not_rewritten(bridge, store, state):
    task = create(store)
    with store.transaction() as session:
        session.get(Task, task['id']).state = state
    before = authority(store), ledger(store)
    assert 'уже завершена или заблокирована' in cancel(bridge)
    assert (authority(store), ledger(store)) == before


def test_running_cancel_revokes_approval_preserves_money_and_blocks_next_call(bridge, store, active):
    gateway, task, fake = active
    send(gateway, task)
    money, calls = ledger(store), deepcopy(fake.calls)
    cancel(bridge)
    assert store.get(task['id'])['state'] == 'CANCEL_REQUESTED'
    assert ledger(store) == money
    with store.transaction() as session:
        assert session.get(Approval, task['id']).revoked is True
    with pytest.raises(Denied):
        send(gateway, task, 2)
    assert fake.calls == calls


@pytest.mark.parametrize('timeout', [False, True])
def test_cancel_during_http_keeps_completed_usage_or_uncertain_reserve(bridge, store, active, timeout):
    gateway, task, fake = active
    def during(request):
        if request.url.host == 'api.openai.com':
            bridge[0].receive(update(1, '/cancel_experiment'))
            if timeout:
                raise httpx.ReadTimeout('fixture response lost')
    fake.after = during
    with pytest.raises(Denied):
        send(gateway, task)
    status = gateway.status(task['id'])
    # Dedicated experiment fixture: 100 input * 67_500 + 32 output * 405_000 nano-RUB.
    assert status['actual_nano_rub'] == (0 if timeout else 19_710_000)
    assert (status['uncertain_nano_rub'] > 0) == timeout
    assert store.get(task['id'])['state'] == 'CANCEL_REQUESTED'
    fake.after = None
    before = len(fake.calls)
    with pytest.raises(Denied):
        send(gateway, task, 2)
    assert len(fake.calls) == before and fake.ai_calls == 1


def test_existing_unknown_reserve_is_not_reconciled_or_released_by_cancel(bridge, store, active):
    gateway, task, fake = active
    fake.after = lambda request: (_ for _ in ()).throw(httpx.ReadTimeout('fixture loss'))
    with pytest.raises(Denied):
        send(gateway, task)
    before, calls = ledger(store), deepcopy(fake.calls)
    cancel(bridge)
    assert ledger(store) == before and fake.calls == calls
    assert gateway.status(task['id'])['result_uncertain'] is True


def test_duplicate_concurrent_cancel_and_restart_apply_once(bridge, store, active):
    _, task, _ = active
    service = bridge[0]
    command = update(1, '/cancel_experiment')
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(service.receive, [command] * 3))
    assert results[0] == results[1] == results[2]
    view = store.get(task['id'])
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.receive(command)
    restarted.resume_pending()
    assert store.get(task['id']) == view
    with store.transaction() as session:
        effects = session.scalars(select(Audit).where(Audit.event['kind'].as_string() == 'cancel_requested',
            Audit.event['task_id'].as_string() == task['id'])).all()
        assert len(effects) == 1


def test_enqueue_crash_rolls_back_cancellation_and_recovers_receipt_once(bridge, store, active, monkeypatch):
    _, task, _ = active
    service = bridge[0]
    original = store.get(task['id'])
    with monkeypatch.context() as patch:
        patch.setattr(service, 'enqueue', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('fixture crash')))
        with pytest.raises(RuntimeError):
            service.receive(update(1, '/cancel_experiment'))
    assert store.get(task['id']) == original
    with store.transaction() as session:
        assert not session.get(Approval, task['id']).revoked
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.resume_pending()
    assert store.get(task['id'])['state'] == 'CANCEL_REQUESTED'
    restarted.resume_pending()
    assert restarted.deliver_one()['state'] == 'SENT'
    assert restarted.deliver_one() is None


@pytest.mark.parametrize('tamper', ['request_key', 'payload_number', 'fingerprint', 'intent', 'source', 'expired'])
def test_delayed_receipt_cannot_rebind_or_bypass_integrity(bridge, store, monkeypatch, tamper):
    task = create(store)
    defer(bridge, monkeypatch)
    with store.transaction() as session:
        if tamper == 'request_key':
            session.get(Task, task['id']).request_key = 'owner:archived'
        elif tamper == 'payload_number':
            session.execute(text("UPDATE tasks SET payload=jsonb_set(payload,'{cost}','2.0'::jsonb) WHERE id=:id"),
                            {'id': task['id']})
        elif tamper in {'fingerprint', 'intent'}:
            inbox = session.get(TelegramInbox, bridge[0].profile + ':1')
            if tamper == 'fingerprint':
                inbox.fingerprint = '0' * 64
            else:
                inbox.intent = {'kind': 'experiment'}
    if tamper == 'request_key':
        create(store)  # Same canonical key, but a different immutable task ID.
    if tamper == 'source':
        monkeypatch.setattr(store, 'settings', replace(store.settings, source_revision='a' * 40))
    if tamper == 'expired':
        original = store.now
        monkeypatch.setattr(store, 'now', lambda session: original(session) + timedelta(seconds=121))
    before = authority(store), ledger(store)
    if tamper in {'fingerprint', 'intent', 'source'}:
        with pytest.raises(Denied):
            bridge[0].resume_pending()
    else:
        # Exercise the actual apply path; resume_pending journals a Denied as
        # a rejected command, without cancelling either old or replacement work.
        from command_center.telegram_experiment_cancel import apply
        with pytest.raises(Denied):
            apply(bridge[0], bridge[0].profile + ':1')
    assert (authority(store), ledger(store)) == before


@pytest.mark.parametrize('state', ['halted', 'recovery'])
def test_cancel_available_while_stopped_without_resuming_or_touching_money(bridge, store, active, state, monkeypatch):
    _, task, _ = active
    store.halt('owner')
    if state == 'recovery':
        with store.transaction() as session:
            session.get(Control, 1).recovery = True
    before = ledger(store)
    monkeypatch.setattr(Gateway, '__init__', lambda *a, **k: pytest.fail('no Gateway'))
    monkeypatch.setattr(FileCredentials, 'get', lambda *a: pytest.fail('no credentials'))
    monkeypatch.setattr(httpx, 'Client', lambda *a, **k: pytest.fail('no HTTP client'))
    cancel(bridge)
    assert ledger(store) == before and store.snapshot()['halted']
    assert store.get(task['id'])['state'] == 'CANCEL_REQUESTED'


@pytest.mark.parametrize('attack', ['user', 'group', 'forward', 'sender_chat', 'arguments'])
def test_only_exact_private_owner_command_can_cancel(bridge, store, attack):
    create(store)
    command = update(1, '/cancel_experiment' + (' confirm' if attack == 'arguments' else ''))
    if attack == 'user':
        command['message']['from']['id'] += 1
    elif attack == 'group':
        command['message']['chat']['type'] = 'group'
    elif attack == 'forward':
        command['message']['forward_origin'] = {'type': 'user'}
    elif attack == 'sender_chat':
        command['message']['sender_chat'] = {'id': OWNER}
    before = authority(store), ledger(store)
    with pytest.raises(Denied):
        bridge[0].receive(command)
    assert (authority(store), ledger(store)) == before


def test_response_loss_never_reapplies_cancellation(bridge, store, active):
    _, task, _ = active
    service, fake = bridge
    fake.after = lambda method: (_ for _ in ()).throw(httpx.ReadTimeout('fixture loss'))
    command = update(1, '/cancel_experiment')
    service.receive(command)
    version = store.get(task['id'])['version']
    assert service.deliver_one()['state'] == 'UNCERTAIN'
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.recover()
    restarted.receive(command)
    assert restarted.deliver_one() is None and store.get(task['id'])['version'] == version


def test_locked_composition_retains_f1_role_and_operator_ownership_rules(store):
    task = create(store)
    with store.transaction() as session:
        for actor, revoke in [('agent', False), ('viewer', False), ('operator', True), ('operator', False)]:
            with pytest.raises(Denied):
                store._cancel_locked(session, actor, task['id'], revoke)
    assert store.get(task['id'])['state'] == 'WAITING_APPROVAL'
