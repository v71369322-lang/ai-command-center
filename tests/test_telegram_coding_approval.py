"""Actual PG/Approval/Outbox and observed mock Telegram; no live execution or AI."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from command_center.isolated_coding import create, report
from command_center.models import Approval, Outbox, Task, TelegramDelivery
from command_center.project_setup import patch
from command_center.store import Denied, canonical, digest
from command_center.telegram_coding_approval import ISSUED, CONSUMED, allowed_markup, keyboard, parse_callback
from test_isolated_coding import binding, save, TEST_SOURCE
import test_plan_acceptance
from test_telegram_readiness import bridge as bridge, ledger
from test_telegram_service import configured as configured, OWNER, update
from test_telegram_plan_acceptance import callback, records


@pytest.fixture
def task(store, bridge, monkeypatch):
    monkeypatch.setattr(test_plan_acceptance, 'capture', lambda _, value:
                        bridge[0].receive(update(10, value))['inbox_id'])
    return create(store, 'owner', save(store, binding(store, monkeypatch)))


def issue(bridge, task, uid=20):
    return bridge[0].receive(update(uid, '/coding_authorize ' + task['id']))


def click(bridge, uid=30):
    while bridge[0].deliver_one():
        pass
    index, body = next((i, b) for i, b in reversed(list(enumerate(bridge[1].sent, 1)))
                       if allowed_markup(b.get('reply_markup')))
    return callback(body, index, uid)


def approvals(store):
    with store.transaction() as session:
        return len(session.scalars(select(Approval)).all()), len(session.scalars(select(Outbox)).all())


def test_exact_review_creates_existing_f1_approval_only_after_observed_click(bridge, store, task):
    before = ledger(store)
    issue(bridge, task)
    assert approvals(store) == (0, 0) and store.get(task['id'])['state'] == 'WAITING_APPROVAL'
    button = click(bridge)
    texts = '\n'.join(b['text'] for b in bridge[1].sent)
    assert 'return 1' in texts and '+    return 2' in texts and TEST_SOURCE in texts
    assert 'Сеть и credentials запрещены' in texts and 'rootless-required' in texts
    bridge[0].receive(button)
    assert approvals(store) == (1, 1) and len(records(store, CONSUMED)) == 1
    assert ledger(store) == before
    assert store.get(task['id'])['state'] == 'READY'
    with store.transaction() as session:
        approval = session.get(Approval, task['id'])
        assert not approval.used and not approval.revoked
        assert approval.expires_at <= store.now(session) + timedelta(seconds=120)
    assert store.claim(task['id'])['state'] == 'RUNNING'


@pytest.mark.parametrize('attack', ['pending', 'uncertain_page', 'fake_sent', 'page_body', 'card_body', 'wrong_message'])
def test_undelivered_or_changed_review_never_approves(bridge, store, task, admin, attack):
    issue(bridge, task)
    e = records(store, ISSUED)[0].event
    if attack == 'pending':
        with store.transaction() as session:
            body = deepcopy(session.get(TelegramDelivery, e['delivery_id']).body)
        button = callback(body, 999)
    else:
        if attack == 'fake_sent':
            with admin.transaction() as session:
                session.get(TelegramDelivery, e['pages'][0]['delivery_id']).state = 'UNCERTAIN'
        button = click(bridge)
        with admin.transaction() as session:
            page = session.get(TelegramDelivery, e['pages'][0]['delivery_id'])
            card = session.get(TelegramDelivery, e['delivery_id'])
            if attack == 'uncertain_page':
                page.state = 'UNCERTAIN'
            elif attack == 'fake_sent':
                page.state, page.message_id = 'SENT', 999
            elif attack == 'page_body':
                page.body = {**page.body, 'text': 'Different source'}
            elif attack == 'card_body':
                card.body = {**card.body, 'text': 'Different authority'}
            else:
                button['callback_query']['message']['message_id'] += 100
    bridge[0].receive(button)
    assert approvals(store) == (0, 0) and not records(store, CONSUMED)


def test_concurrent_clicks_restart_and_replay_consume_once(bridge, store, task):
    issue(bridge, task)
    first = click(bridge)
    second = deepcopy(first)
    second['update_id'] = 31
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(bridge[0].receive, [first, second]))
    bridge[0].receive(first)
    assert approvals(store) == (1, 1) and len(records(store, CONSUMED)) == 1


@pytest.mark.parametrize('change', ['setup', 'project', 'halt', 'cancel', 'other_approval'])
def test_changed_state_invalidates_review(bridge, store, task, change):
    issue(bridge, task)
    button = click(bridge)
    if change == 'setup':
        patch(store, 'owner', 'command-center', 1, 'acceptance', ['New public criterion'], str(uuid4()))
    elif change == 'project':
        from command_center.project_inbox import classify
        rid = task['payload']['specification']['acceptance_reference']['request_id']
        classify(store, 'owner', rid, 'vanilla-sugar', 1, str(uuid4()))
    elif change == 'halt':
        store.halt('owner')
    elif change == 'cancel':
        store.cancel('owner', task['id'])
    else:
        store.approve('owner', task['id'], 1)
    bridge[0].receive(button)
    assert not records(store, CONSUMED)
    assert approvals(store) == ((1, 1) if change == 'other_approval' else (0, 0))


@pytest.mark.parametrize('attack', ['foreign_owner', 'group', 'forwarded'])
def test_only_private_bound_owner_can_confirm(bridge, store, task, attack):
    issue(bridge, task)
    button = click(bridge)
    if attack == 'foreign_owner':
        button['callback_query']['from']['id'] += 1
    elif attack == 'group':
        button['callback_query']['message']['chat']['type'] = 'group'
    else:
        button['callback_query']['message']['forward_origin'] = {'type': 'hidden_user'}
    with pytest.raises(Denied):
        bridge[0].receive(button)
    assert approvals(store) == (0, 0)


def test_expired_card_does_not_refresh_on_replay(bridge, store, task, monkeypatch):
    issue(bridge, task)
    button = click(bridge)
    with store.transaction() as session:
        future = store.now(session) + timedelta(seconds=301)
    monkeypatch.setattr(store, 'now', lambda _: future)
    bridge[0].receive(button)
    assert approvals(store) == (0, 0) and not records(store, CONSUMED)


@pytest.mark.parametrize('seconds', [121, 301])
def test_expiry_during_finalization_rolls_back_approval_outbox_consumption(bridge, store, task, monkeypatch, seconds):
    issue(bridge, task)
    button = click(bridge)
    original = store._approve_locked
    with store.transaction() as session:
        future = store.now(session) + timedelta(seconds=seconds)
    def expire(*args, **kwargs):
        value = original(*args, **kwargs)
        monkeypatch.setattr(store, 'now', lambda _: future)
        return value
    monkeypatch.setattr(store, '_approve_locked', expire)
    with pytest.raises(Denied, match='expired'):
        bridge[0].receive(button)
    assert approvals(store) == (0, 0) and not records(store, CONSUMED)
    assert store.get(task['id'])['state'] == 'WAITING_APPROVAL'


def test_reply_failure_rolls_back_and_retry_can_finish(bridge, store, task, monkeypatch):
    issue(bridge, task)
    button = click(bridge)
    with monkeypatch.context() as patcher:
        patcher.setattr(bridge[0], 'finish', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('public failure')))
        with pytest.raises(RuntimeError):
            bridge[0].receive(button)
    assert approvals(store) == (0, 0) and not records(store, CONSUMED)
    bridge[0].receive(button)
    assert approvals(store) == (1, 1) and len(records(store, CONSUMED)) == 1


def test_connection_revocation_after_approval_rolls_back_everything(bridge, store, task, monkeypatch):
    issue(bridge, task)
    button = click(bridge)
    original = store._approve_locked
    def revoke(*args, **kwargs):
        value = original(*args, **kwargs)
        monkeypatch.setattr(bridge[0], 'guard', lambda: (_ for _ in ()).throw(Denied('public_revoked')))
        return value
    monkeypatch.setattr(store, '_approve_locked', revoke)
    with pytest.raises(Denied, match='revoked'):
        bridge[0].receive(button)
    assert approvals(store) == (0, 0) and not records(store, CONSUMED)


def test_pending_command_cannot_select_a_later_task_version(bridge, store, task, monkeypatch, admin):
    with monkeypatch.context() as patcher:
        patcher.setattr(bridge[0], '_apply_pending', lambda *a: None)
        issue(bridge, task)
    with admin.transaction() as session:
        session.get(Task, task['id']).version += 1
    issue(bridge, task)
    assert not records(store, ISSUED) and approvals(store) == (0, 0)
    issue(bridge, task, uid=21)
    assert records(store, ISSUED)[0].event['pin']['task_version'] == 2


@pytest.mark.parametrize('attack', ['label', 'url', 'extra', 'bad_token'])
def test_only_fixed_coding_button_can_be_sent(bridge, attack):
    markup = keyboard('A'*32)
    if attack == 'label':
        markup['inline_keyboard'][0][0]['text'] = 'Authorize paid AI'
    elif attack == 'url':
        markup['inline_keyboard'][0][0]['url'] = 'https://example.invalid'
    elif attack == 'extra':
        markup['inline_keyboard'][0].append(markup['inline_keyboard'][0][0])
    else:
        markup['inline_keyboard'][0][0]['callback_data'] = 'ca:bad'
    with pytest.raises(Denied):
        bridge[0].client.validate('sendMessage', {'chat_id': OWNER, 'text': 'Public', 'reply_markup': markup})
    assert parse_callback('ca:'+'A'*32)['kind'] == 'coding_authorize_confirm'


def test_unknown_task_does_not_create_one(bridge, store):
    bridge[0].receive(update(20, '/coding_authorize ' + str(uuid4())))
    assert not records(store, ISSUED) and approvals(store) == (0, 0)


@pytest.mark.parametrize('value', ['/coding_authorize', '/coding_authorize bad', '/coding_authorize 123 extra'])
def test_bad_command_does_not_enter_request_inbox(bridge, value):
    with pytest.raises(Denied):
        bridge[0].receive(update(20, value))


def test_large_cyrillic_source_is_complete_and_all_parts_are_required(bridge, store, task, admin):
    # Materialize a separate, larger owner-reviewed task using the same specification.
    with store.transaction() as session:
        row = session.get(Task, task['id'])
        original = deepcopy(row.payload)
    body = {'request_id': original['specification']['acceptance_reference']['request_id'],
            'expected_spec_digest': original['spec_digest'], 'snapshot': original['snapshot'],
            'replacements': {k: v + '# ' + 'Д'*1000 + '\n' for k, v in original['replacements'].items()}}
    larger = create(store, 'owner', save(store, body))
    issue(bridge, larger)
    button = click(bridge)
    text = [b['text'] for b in bridge[1].sent if 'Часть ' in b['text']]
    joined = ''.join(t.split('\n', 3)[3] for t in text)
    assert 'Д'*1000 in joined and len(text) > 2
    assert all(len(t.encode()) <= 2000 for t in text)
    e = records(store, ISSUED)[0].event
    with admin.transaction() as session:
        session.get(TelegramDelivery, e['pages'][-1]['delivery_id']).state = 'UNCERTAIN'
    bridge[0].receive(button)
    assert approvals(store) == (0, 0)
    issue(bridge, larger, uid=21)
    bridge[0].receive(click(bridge, uid=31))
    assert approvals(store) == (1, 1)


def test_coding_status_is_scoped_read_only_and_checks_result_evidence(bridge, store, task, admin):
    before = approvals(store), ledger(store)
    bridge[0].receive(update(20, '/coding_status ' + task['id']))
    while bridge[0].deliver_one():
        pass
    assert 'WAITING_APPROVAL' in bridge[1].sent[-1]['text']
    assert (approvals(store), ledger(store)) == before
    store.approve('owner', task['id'], 1)
    claimed = store.claim(task['id'])
    # Simulated trusted-runner finish; this test does not execute code or containers.
    expected = {**report(claimed['payload']), 'checks': [{'command': c, 'passed': True}
        for c in claimed['payload']['specification']['verification_commands']],
        'passed': True, 'independent_verification': True}
    store.finish(task['id'], claimed['fence'], canonical(expected), digest(expected), actual_cost=0)
    bridge[0].receive(update(21, '/coding_status ' + task['id']))
    while bridge[0].deliver_one():
        pass
    assert 'Результат независимо проверен' in bridge[1].sent[-1]['text']
    with admin.transaction() as session:
        session.get(Task, task['id']).artifact = 'forged'
    bridge[0].receive(update(22, '/coding_status ' + task['id']))
    while bridge[0].deliver_one():
        pass
    assert 'Подтверждённого результата пока нет' in bridge[1].sent[-1]['text']


def test_another_bot_profile_cannot_review_or_read_task(bridge, store, task, monkeypatch):
    monkeypatch.setattr(bridge[0], 'profile', 'a'*64)
    issue(bridge, task)
    bridge[0].receive(update(21, '/coding_status ' + task['id']))
    while bridge[0].deliver_one():
        pass
    assert 'не найдена' in bridge[1].sent[-1]['text']
    assert approvals(store) == (0, 0) and not records(store, ISSUED)


def test_help_keeps_new_command_inside_existing_transport_limits(bridge):
    bridge[0].receive(update(1, '/help'))
    while bridge[0].deliver_one():
        pass
    assert '/coding_authorize UUID' in bridge[1].sent[-1]['text']
