"""Actual PG and strict Bot API mocks; no real messages, AI or credentials."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from threading import Event

import httpx
import pytest
from sqlalchemy import select, text

from command_center.coding.first_experiment import task_payload
from command_center.coding.gateway import Gateway
from command_center.coding.integration_config import FileCredentials
from command_center.models import Audit, Control, Task, TelegramDelivery, TelegramInbox
from command_center.store import Denied, canonical, digest
from command_center.telegram_bridge import TelegramBridge
from command_center.telegram_experiment_watch import NOTICE, WATCH, current
from test_telegram_experiment import active as active, complete_fixture, create
from test_readiness import send
from test_telegram_readiness import bridge as bridge, ledger
from test_telegram_service import OWNER, configured as configured, update
from test_telegram_task_status import authority


def command(bridge, uid=1, value='/watch_experiment', *, deliver=True):
    service, fake = bridge
    service.receive(update(uid, value))
    if deliver:
        while service.deliver_one():
            pass
        return fake.sent[-1]['text']


def notices(store, profile=None):
    with store.transaction() as session:
        query = select(Audit).where(Audit.event['kind'].as_string() == NOTICE)
        if profile:
            query = query.where(Audit.event['profile'].as_string() == profile)
        return [dict(a.event) for a in session.scalars(query)]


def test_empty_watch_does_not_register_future_task_or_grant(bridge, store):
    before = authority(store), ledger(store)
    assert 'ещё не создан' in command(bridge)
    assert (authority(store), ledger(store)) == before
    with store.transaction() as session:
        assert current(bridge[0], session) is None
    create(store)
    bridge[0].collect_results()
    assert not notices(store)


@pytest.mark.parametrize('enabled', [False, True])
def test_default_is_silent_and_watch_is_explicit(bridge, store, active, enabled):
    _, task, _ = active
    if enabled:
        command(bridge)
    complete_fixture(store, task)
    before = authority(store), ledger(store)
    bridge[0].collect_results()
    assert bool(notices(store)) == enabled
    assert (authority(store), ledger(store)) == before


@pytest.mark.parametrize('state', ['FAILED', 'CANCELLED', 'RECONCILING', 'SECURITY_BLOCKED'])
def test_terminal_outcome_is_reported_once_without_claiming_success(bridge, store, state):
    task = create(store)
    command(bridge)
    with store.transaction() as session:
        row = session.get(Task, task['id'])
        row.state, row.reason = state, 'PRIVATE_REASON_NOT_FOR_TELEGRAM'
    before = authority(store), ledger(store)
    for _ in range(3):
        bridge[0].collect_results()
    assert len(notices(store)) == 1
    assert bridge[0].deliver_one()['state'] == 'SENT'
    body = bridge[1].sent[-1]['text']
    assert 'Уведомление первого AI-эксперимента' in body and task['id'] in body
    assert 'PRIVATE_' not in body and 'независимо проверен' not in body
    assert (authority(store), ledger(store)) == before


def test_time_poll_restart_and_concurrency_do_not_repeat_same_notice(bridge, store, active):
    _, task, _ = active
    command(bridge)
    complete_fixture(store, task)
    service = bridge[0]
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda _: service.collect_results(), range(3)))
    assert len(notices(store)) == 1
    assert service.deliver_one()['state'] == 'SENT'
    sent = deepcopy(bridge[1].sent)
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.collect_results()
    assert restarted.deliver_one() is None and bridge[1].sent == sent
    assert 'реальный PR не опубликован' in sent[-1]['text']


def test_new_visible_outcome_not_clock_or_private_evidence_creates_update(bridge, store, monkeypatch):
    task = create(store)
    command(bridge)
    with store.transaction() as session:
        row = session.get(Task, task['id'])
        row.state = 'RECONCILING'
    bridge[0].collect_results()
    original = store.now
    monkeypatch.setattr(store, 'now', lambda session: original(session) + timedelta(seconds=30))
    bridge[0].collect_results()
    with store.transaction() as session:
        row = session.get(Task, task['id'])
        row.coding_evidence = {'private': 'PRIVATE_PROVIDER_DETAIL_CHANGED'}
    bridge[0].collect_results()
    assert len(notices(store)) == 1
    with store.transaction() as session:
        session.get(Task, task['id']).state = 'CANCELLED'
    bridge[0].collect_results()
    assert len(notices(store)) == 2


def test_settled_billing_notifies_changed_amounts_without_claiming_recovered_result(bridge, store, active):
    gateway, task, fake = active
    command(bridge)
    fake.after = lambda request: (_ for _ in ()).throw(httpx.ReadTimeout('fixture response loss'))
    with pytest.raises(Denied):
        send(gateway, task)
    store.abort(task['id'], task['fence'], 'external_outcome_uncertain', False, usage_unknown=True)
    bridge[0].collect_results()
    action = gateway.status(task['id'])['actions'][0]['id']
    gateway.reconcile_usage('owner', action, 100, 32, 'fixture billing evidence')
    before, calls = (authority(store), ledger(store)), deepcopy(fake.calls)
    bridge[0].collect_results()
    bridge[0].collect_results()
    assert len(notices(store)) == 2
    while bridge[0].deliver_one():
        pass
    body = bridge[1].sent[-1]['text']
    assert 'Спорный резерв по журналу: 0 ₽' in body and 'Внешняя операция не сверена' in body
    assert (authority(store), ledger(store)) == before and fake.calls == calls


@pytest.mark.parametrize('state', ['WAITING_APPROVAL', 'READY', 'RUNNING', 'VERIFYING', 'CANCEL_REQUESTED'])
def test_nonterminal_task_does_not_notify(bridge, store, state):
    task = create(store)
    command(bridge)
    with store.transaction() as session:
        session.get(Task, task['id']).state = state
    bridge[0].collect_results()
    assert not notices(store)


def test_unwatch_cancels_only_unsent_notices_and_reenable_does_not_replay_cancelled(bridge, store, active):
    _, task, _ = active
    command(bridge)
    complete_fixture(store, task)
    bridge[0].collect_results()
    notice_id = notices(store)[0]['delivery_id']
    command(bridge, 2, '/experiment', deliver=False)  # Unrelated reply must survive.
    command(bridge, 3, '/unwatch_experiment', deliver=False)
    with store.transaction() as session:
        assert session.get(TelegramDelivery, notice_id).state == 'CANCELLED'
        assert session.scalar(select(TelegramDelivery).where(
            TelegramDelivery.id != notice_id, TelegramDelivery.state == 'NEW')) is not None
    command(bridge, 4)
    bridge[0].collect_results()
    assert bridge[0].deliver_one() is None
    assert len(notices(store)) == 1
    assert not any('Уведомление первого' in s['text'] for s in bridge[1].sent)


@pytest.mark.parametrize('sending', [False, True])
def test_send_uncertainty_or_inflight_send_is_preserved_on_unwatch(bridge, store, active, sending):
    _, task, _ = active
    command(bridge)
    complete_fixture(store, task)
    bridge[0].collect_results()
    notice_id = notices(store)[0]['delivery_id']
    if sending:
        with store.transaction() as session:
            row = session.get(TelegramDelivery, notice_id)
            row.state, row.deadline = 'SENDING', store.now(session) - timedelta(seconds=1)
    else:
        bridge[1].after = lambda method: (_ for _ in ()).throw(httpx.ReadTimeout('public fixture loss'))
        assert bridge[0].deliver_one()['state'] == 'UNCERTAIN'
        bridge[1].after = None
    command(bridge, 2, '/unwatch_experiment')
    with store.transaction() as session:
        assert session.get(TelegramDelivery, notice_id).state == ('SENDING' if sending else 'UNCERTAIN')
    restarted = TelegramBridge(store, bridge[0].client, OWNER)
    restarted.recover()
    command((restarted, bridge[1]), 3)
    restarted.collect_results()
    assert restarted.deliver_one() is None
    with store.transaction() as session:
        assert session.get(TelegramDelivery, notice_id).state == 'UNCERTAIN'


def test_unwatch_during_actual_send_does_not_retract_or_repeat_inflight_notice(bridge, store, active):
    _, task, _ = active
    command(bridge)
    complete_fixture(store, task)
    bridge[0].collect_results()
    entered, release = Event(), Event()
    def block(method):
        if bridge[1].sent[-1]['text'].startswith('Уведомление первого'):
            entered.set()
            assert release.wait(5)
    bridge[1].after = block
    with ThreadPoolExecutor(max_workers=1) as pool:
        sending = pool.submit(bridge[0].deliver_one)
        try:
            assert entered.wait(5)
            command(bridge, 2, '/unwatch_experiment', deliver=False)
        finally:
            release.set()
        assert sending.result(timeout=5)['state'] == 'SENT'
    bridge[1].after = None
    command(bridge, 3)
    bridge[0].collect_results()
    assert bridge[0].deliver_one() is None
    assert len([body for body in bridge[1].sent if body['text'].startswith('Уведомление первого')]) == 1


def test_new_source_does_not_reactivate_old_watch_but_can_revoke_pending_notice(bridge, store, active, monkeypatch):
    _, task, _ = active
    command(bridge)
    complete_fixture(store, task)
    bridge[0].collect_results()
    notice_id = notices(store)[0]['delivery_id']
    monkeypatch.setattr(store, 'settings', replace(store.settings, source_revision='a' * 40))
    bridge[0].collect_results()
    assert len(notices(store)) == 1
    command(bridge, 2, '/unwatch_experiment', deliver=False)
    with store.transaction() as session:
        assert session.get(TelegramDelivery, notice_id).state == 'CANCELLED'


@pytest.mark.parametrize('state', ['halted', 'recovery'])
def test_notification_does_not_resume_work_or_touch_authority(bridge, store, active, state, monkeypatch):
    _, task, _ = active
    command(bridge)
    complete_fixture(store, task)
    store.halt('owner')
    if state == 'recovery':
        with store.transaction() as session:
            session.get(Control, 1).recovery = True
    before = authority(store), ledger(store)
    monkeypatch.setattr(Gateway, '__init__', lambda *a, **k: pytest.fail('no gateway'))
    monkeypatch.setattr(FileCredentials, 'get', lambda *a: pytest.fail('no credentials'))
    monkeypatch.setattr(httpx, 'Client', lambda *a, **k: pytest.fail('no new HTTP client'))
    bridge[0].collect_results()
    assert bridge[0].deliver_one()['state'] == 'SENT'
    assert (authority(store), ledger(store)) == before


@pytest.mark.parametrize('tamper', ['inbox', 'fingerprint', 'payload_number', 'phantom_watch'])
def test_invalid_consent_or_task_never_notifies(bridge, store, active, tamper):
    _, task, _ = active
    command(bridge)
    complete_fixture(store, task)
    with store.transaction() as session:
        if tamper in {'inbox', 'fingerprint'}:
            row = session.get(TelegramInbox, bridge[0].profile + ':1')
            if tamper == 'inbox':
                row.intent = {'kind': 'experiment'}
            else:
                row.fingerprint = '0' * 64
        elif tamper == 'payload_number':
            session.execute(text("UPDATE tasks SET payload=jsonb_set(payload,'{cost}','2.0'::jsonb) WHERE id=:id"),
                            {'id': task['id']})
        else:
            store.audit(session, WATCH, 'owner', task['id'], profile=bridge[0].profile,
                        inbox_id=bridge[0].profile + ':999', enabled=True, payload_hash=digest(task_payload()))
    with pytest.raises(Denied):
        bridge[0].collect_results()
    assert not notices(store)


def test_duplicate_watch_and_crash_rollback_are_idempotent(bridge, store, monkeypatch):
    create(store)
    service, _ = bridge
    command_data = update(1, '/watch_experiment')
    with monkeypatch.context() as patch:
        patch.setattr(service, 'enqueue', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('fixture crash')))
        with pytest.raises(RuntimeError):
            service.receive(command_data)
    with store.transaction() as session:
        assert current(service, session) is None
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.resume_pending()
    restarted.receive(command_data)
    command((restarted, bridge[1]), 2)
    with store.transaction() as session:
        assert len(session.scalars(select(Audit).where(Audit.event['kind'].as_string() == WATCH)).all()) == 1


@pytest.mark.parametrize('attack', ['user', 'group', 'forward', 'sender_chat', 'arguments'])
def test_only_explicit_private_owner_command_can_subscribe(bridge, store, attack):
    create(store)
    command_data = update(1, '/watch_experiment' + (' confirm' if attack == 'arguments' else ''))
    if attack == 'user':
        command_data['message']['from']['id'] += 1
    elif attack == 'group':
        command_data['message']['chat']['type'] = 'group'
    elif attack == 'forward':
        command_data['message']['forward_origin'] = {'type': 'user'}
    elif attack == 'sender_chat':
        command_data['message']['sender_chat'] = {'id': OWNER}
    with pytest.raises(Denied):
        bridge[0].receive(command_data)
    with store.transaction() as session:
        assert current(bridge[0], session) is None


def test_unrelated_connection_and_regular_experiment_query_do_not_subscribe(bridge, store, active):
    _, task, _ = active
    command(bridge, value='/experiment')
    complete_fixture(store, task)
    bridge[0].collect_results()
    assert not notices(store)
    with store.transaction() as session:
        store.audit(session, WATCH, 'owner', task['id'], profile='foreign', inbox_id='foreign:1',
                    enabled=True, payload_hash=digest(task_payload()))
    bridge[0].collect_results()
    assert not notices(store)


def test_notice_transport_is_bounded_and_does_not_echo_private_evidence(bridge, store, active):
    _, task, _ = active
    command(bridge)
    complete_fixture(store, task, live=True)
    bridge[0].collect_results()
    assert bridge[0].deliver_one()['state'] == 'SENT'
    body = bridge[1].sent[-1]
    assert 'Зафиксирован Draft PR:' in body['text']
    assert 'PRIVATE_' not in canonical(body) and 'parse_mode' not in body
    assert len(body['text']) <= 4096 and len(canonical(body).encode()) <= 8192
