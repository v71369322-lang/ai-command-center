"""Real PostgreSQL and observed mock Bot API delivery, never real Telegram/AI."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from command_center.models import Audit, TelegramDelivery
from command_center.plan_acceptance import EVENT as ACCEPTED
from command_center.project_inbox import classify
from command_center.project_setup import save as setup_save
from command_center.request_planning import context
from command_center.store import Denied
from command_center.telegram_plan_acceptance import ISSUED, CONSUMED, allowed_markup, keyboard, parse_callback
from test_project_setup import full
from test_request_plan_store import persist
from test_request_planning import response
from test_telegram_readiness import bridge as bridge
from test_telegram_service import configured as configured, OWNER, update
from test_telegram_task_status import authority
from test_telegram_readiness import ledger


@pytest.fixture
def content(bridge, store):
    service, _ = bridge
    rid = service.receive(update(10, 'Public bounded Command Center improvement'))['inbox_id']
    classify(store, 'owner', rid, 'command-center', 0, str(uuid4()))
    setup_save(store, 'owner', 'command-center', 0,
               {**full(), 'deployment_target': 'command-center-staging'}, str(uuid4()))
    snapshot = context(store, 'owner', rid)
    persist(store, snapshot, response(snapshot))
    return rid


def records(store, kind):
    with store.transaction() as tx:
        return list(tx.scalars(select(Audit).where(Audit.event['kind'].as_string() == kind)))


def issue(bridge):
    return bridge[0].receive(update(20, '/plan_accept 10'))


def callback(body, message_id, uid=30):
    return {'update_id': uid, 'callback_query': {'id': 'public-content-click-'+str(uid),
        'from': {'id': OWNER, 'is_bot': False},
        'data': body['reply_markup']['inline_keyboard'][0][0]['callback_data'],
        'message': {'message_id': message_id, 'chat': {'id': OWNER, 'type': 'private'}}}}


def click(bridge, uid=30):
    while bridge[0].deliver_one():
        pass
    index, body = next((i, b) for i, b in reversed(list(enumerate(bridge[1].sent, 1)))
                       if allowed_markup(b.get('reply_markup')))
    return callback(body, index, uid)


def test_all_content_delivery_then_exact_click_is_atomic_and_not_authority(bridge, store, content):
    before = authority(store), ledger(store)
    issue(bridge)
    assert not records(store, ACCEPTED)
    button = click(bridge)
    assert any('Перечень полей согласован' in b['text'] for b in bridge[1].sent)
    assert any('содержание' in b['text'].lower() and 'не разрешает' in b['text'] for b in bridge[1].sent)
    bridge[0].receive(button)
    assert len(records(store, ACCEPTED)) == len(records(store, CONSUMED)) == 1
    bridge[0].receive(button)
    assert len(records(store, ACCEPTED)) == 1
    assert (authority(store), ledger(store)) == before
    bridge[0].receive(update(40, '/plan_acceptance 10'))


def test_pending_final_card_is_not_confirmation(bridge, store, content):
    issue(bridge)
    e = records(store, ISSUED)[0].event
    with store.transaction() as tx:
        body = deepcopy(tx.get(TelegramDelivery, e['delivery_id']).body)
    assert bridge[0].receive(callback(body, 999))['state'] == 'DONE'
    assert not records(store, ACCEPTED) and not records(store, CONSUMED)


@pytest.mark.parametrize('attack', ['uncertain_page', 'fake_sent_page', 'page_body', 'card_body', 'wrong_message'])
def test_mutable_delivery_state_or_changed_display_does_not_authorize(bridge, store, content, admin, attack):
    issue(bridge)
    e = records(store, ISSUED)[0].event
    if attack == 'fake_sent_page':
        with admin.transaction() as tx:
            tx.get(TelegramDelivery, e['pages'][0]['delivery_id']).state = 'UNCERTAIN'
    button = click(bridge)
    with admin.transaction() as tx:
        page = tx.get(TelegramDelivery, e['pages'][0]['delivery_id'])
        card = tx.get(TelegramDelivery, e['delivery_id'])
        if attack == 'uncertain_page':
            page.state = 'UNCERTAIN'
        elif attack == 'fake_sent_page':
            page.state, page.message_id = 'SENT', 999
        elif attack == 'page_body':
            page.body = {**page.body, 'text': 'Changed public content'}
        elif attack == 'card_body':
            card.body = {**card.body, 'text': 'Approve execution instead'}
        else:
            button['callback_query']['message']['message_id'] += 100
    assert bridge[0].receive(button)['state'] == 'DONE'
    assert not records(store, ACCEPTED) and not records(store, CONSUMED)


def test_expiry_is_not_extended_on_click(bridge, store, content, monkeypatch):
    issue(bridge)
    button = click(bridge)
    with store.transaction() as tx:
        future = store.now(tx) + timedelta(seconds=301)
    monkeypatch.setattr(store, 'now', lambda tx: future)
    bridge[0].receive(button)
    assert not records(store, ACCEPTED) and not records(store, CONSUMED)


def test_changed_setup_requires_new_card(bridge, store, content):
    from command_center.project_setup import patch
    issue(bridge)
    button = click(bridge)
    patch(store, 'owner', 'command-center', 1, 'acceptance', ['New public criterion'], str(uuid4()))
    assert bridge[0].receive(button)['state'] == 'DONE'
    assert not records(store, ACCEPTED)


def test_two_clicks_consume_once(bridge, store, content):
    issue(bridge)
    first = click(bridge)
    second = deepcopy(first)
    second['update_id'] = 31
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(bridge[0].receive, [first, second]))
    assert len(records(store, ACCEPTED)) == len(records(store, CONSUMED)) == 1


@pytest.mark.parametrize('attack', ['foreign_owner', 'group', 'forwarded'])
def test_confirmation_stays_in_the_bound_private_owner_chat(bridge, store, content, attack):
    issue(bridge)
    button = click(bridge)
    if attack == 'foreign_owner':
        button['callback_query']['from']['id'] += 1
    elif attack == 'group':
        button['callback_query']['message']['chat']['type'] = 'group'
    else:
        button['callback_query']['message']['forward_origin'] = {'type': 'hidden_user'}
    with pytest.raises(Denied):
        bridge[0].receive(button)
    assert not records(store, ACCEPTED)


def test_expiry_during_finalization_rolls_back_content_acceptance(bridge, store, content, monkeypatch):
    import command_center.telegram_plan_acceptance as module
    issue(bridge)
    button = click(bridge)
    original = module.accept_locked
    with store.transaction() as tx:
        future = store.now(tx) + timedelta(seconds=301)
    def expire(*args, **kwargs):
        value = original(*args, **kwargs)
        monkeypatch.setattr(store, 'now', lambda tx: future)
        return value
    monkeypatch.setattr(module, 'accept_locked', expire)
    with pytest.raises(Denied, match='expired'):
        bridge[0].receive(button)
    assert not records(store, ACCEPTED) and not records(store, CONSUMED)


def test_failure_after_acceptance_rolls_back_consumption_and_receipt(bridge, store, content, monkeypatch):
    issue(bridge)
    button = click(bridge)
    with monkeypatch.context() as patch:
        patch.setattr(bridge[0], 'finish', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('public failure')))
        with pytest.raises(RuntimeError):
            bridge[0].receive(button)
    assert not records(store, ACCEPTED) and not records(store, CONSUMED)
    bridge[0].receive(button)
    assert len(records(store, ACCEPTED)) == len(records(store, CONSUMED)) == 1


def test_all_pages_of_large_plan_must_be_observed(bridge, store, content):
    import json
    snapshot = context(store, 'owner', content)
    data = response(snapshot)
    data['id'] = 'resp_public_large_plan'
    plan = {'context_digest': snapshot.binding, 'disposition': 'ready_for_review', 'summary': 'План',
        'steps': [{'description': str(i)+'Д'*125, 'acceptance': ['К'*125, 'Р'*125, 'Т'*125]} for i in range(8)],
        'questions': []}
    data['output'][-1]['content'][0]['text'] = json.dumps(plan, ensure_ascii=False)
    persist(store, snapshot, data)
    issue(bridge)
    e = records(store, ISSUED)[0].event
    assert len(e['pages']) > 1
    button = click(bridge)
    bridge[0].receive(button)
    assert len(records(store, ACCEPTED)) == 1


@pytest.mark.parametrize('attack', ['label', 'extra_button', 'url', 'prefix'])
def test_transport_accepts_only_the_exact_content_keyboard(bridge, attack):
    value = keyboard('A'*32)
    if attack == 'label':
        value['inline_keyboard'][0][0]['text'] = 'Execute now'
    elif attack == 'extra_button':
        value['inline_keyboard'][0].append(value['inline_keyboard'][0][0])
    elif attack == 'url':
        value['inline_keyboard'][0][0]['url'] = 'https://example.invalid'
    else:
        value['inline_keyboard'][0][0]['callback_data'] = 'pc:bad'
    assert not allowed_markup(value)
    with pytest.raises(Denied):
        bridge[0].client.validate('sendMessage', {'chat_id': OWNER, 'text': 'public', 'reply_markup': value})
    assert parse_callback('pc:'+'A'*32)['kind'] == 'plan_accept_confirm'
