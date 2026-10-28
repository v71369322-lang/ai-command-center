"""Owner menu: actual PostgreSQL and strict Bot API HTTP mocks, no live calls."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import httpx
import pytest
from sqlalchemy import select

from command_center.models import TelegramDelivery, TelegramInbox
from command_center.store import Denied, canonical
from command_center.telegram_bridge import TelegramBridge
from command_center.telegram_menu import BUTTONS, keyboard
from test_telegram_service import FakeBot, OWNER, client_for, update
from test_telegram_service import configured as configured
from test_telegram_task_status import authority


@pytest.fixture
def bridge(store, configured):
    fake = FakeBot()
    client = client_for(configured, fake)
    yield TelegramBridge(store, client, OWNER), fake
    client.close()


@pytest.mark.parametrize('command', ['/start', '/help', '/menu'])
def test_menu_is_delivered_by_strict_transport_without_execution(bridge, store, command):
    service, fake = bridge
    before = authority(store)
    service.receive(update(1, command))
    assert service.deliver_one()['state'] == 'SENT'
    body = fake.sent[0]
    assert body['reply_markup'] == keyboard()
    assert 'Голос и реальные AI пока отключены' in body['text']
    assert '/menu' in body['text'] and 'ожидает планирования' in body['text']
    assert len(canonical(body).encode()) <= 8192
    assert authority(store) == before


@pytest.mark.parametrize('label,command', BUTTONS)
def test_buttons_reuse_existing_read_only_intents_even_while_halted(bridge, store, label, command):
    service, fake = bridge
    service.receive(update(1, 'Public saved request'))
    store.halt('owner')
    before = authority(store)
    assert service.normalize(update(2, label))[1] == service.normalize(update(2, command))[1]
    service.receive(update(2, label))
    while service.deliver_one():
        pass
    assert fake.sent[-1]['chat_id'] == OWNER
    assert 'выполнение не запускалось' in fake.sent[-1]['text'].lower() or command in {'/help', '/tasks'}
    assert authority(store) == before


@pytest.mark.parametrize('attack', ['sender', 'group', 'forward'])
def test_menu_buttons_keep_owner_private_chat_boundary(bridge, store, attack):
    service, fake = bridge
    value = update(1, BUTTONS[0][0])
    if attack == 'sender':
        value['message']['from']['id'] += 1
    elif attack == 'group':
        value['message']['chat']['type'] = 'group'
    else:
        value['message']['forward_origin'] = {'type': 'user'}
    with pytest.raises(Denied, match='owner_private_chat'):
        service.receive(value)
    with store.transaction() as session:
        assert session.execute(select(TelegramInbox)).first() is None
    assert fake.calls == []


@pytest.mark.parametrize('value', ['📁 Проекты\n/stop', 'Проекты'])
def test_only_exact_button_labels_are_commands_other_text_remains_data(bridge, store, value):
    service, _ = bridge
    before = authority(store)
    result = service.receive(update(1, value))
    with store.transaction() as session:
        row = session.get(TelegramInbox, result['inbox_id'])
        assert row.state == 'NEEDS_PLANNING' and row.intent == {'kind': 'capture', 'text': value}
    assert authority(store) == before


def test_concurrent_duplicate_and_restart_keep_one_menu_receipt(bridge, store):
    service, fake = bridge
    value = update(1, '/menu')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(service.receive, [value, value]))
    restarted = TelegramBridge(store, service.client, OWNER)
    assert results[0] == results[1] == restarted.receive(value)
    assert restarted.deliver_one()['state'] == 'SENT'
    assert restarted.deliver_one() is None
    assert len(fake.sent) == 1 and fake.sent[0]['reply_markup'] == keyboard()


def test_crash_rolls_back_menu_and_restart_recovers_once(bridge, store, monkeypatch):
    service, fake = bridge
    before = authority(store)
    with monkeypatch.context() as patch:
        patch.setattr(service, 'enqueue', lambda *args: (_ for _ in ()).throw(RuntimeError('crash')))
        with pytest.raises(RuntimeError, match='crash'):
            service.receive(update(1, '/menu'))
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.resume_pending()
    restarted.receive(update(1, '/menu'))
    assert restarted.deliver_one()['state'] == 'SENT'
    assert restarted.deliver_one() is None and len(fake.sent) == 1
    assert authority(store) == before


def test_lost_menu_send_response_is_not_repeated(bridge, store):
    service, fake = bridge
    def lost(method):
        if method == 'sendMessage':
            raise httpx.ReadTimeout('public synthetic response loss')
    fake.after = lost
    service.receive(update(1, '/menu'))
    assert service.deliver_one()['state'] == 'UNCERTAIN'
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.recover()
    restarted.receive(update(1, '/menu'))
    assert restarted.deliver_one() is None and len(fake.sent) == 1


def test_revoked_connection_blocks_queued_menu_before_http(bridge, configured):
    service, fake = bridge
    service.receive(update(1, '/menu'))
    path, config = configured
    path.write_text(config.model_copy(update={'mode': 'disabled'}).model_dump_json())
    with pytest.raises(Denied, match='revoked_or_changed'):
        service.deliver_one()
    assert fake.calls == []


@pytest.mark.parametrize('attack', ['contact', 'location', 'url', 'web_app', 'poll', 'extra', 'numeric_bool'])
def test_transport_rejects_every_menu_scope_expansion(bridge, attack):
    service, fake = bridge
    markup = keyboard()
    button = markup['keyboard'][0][0]
    if attack == 'extra':
        markup['one_time_keyboard'] = True
    elif attack == 'numeric_bool':
        markup['resize_keyboard'] = 1
    else:
        field = {'contact': 'request_contact', 'location': 'request_location',
                 'url': 'url', 'web_app': 'web_app', 'poll': 'request_poll'}[attack]
        button[field] = True if attack in {'contact', 'location'} else {'url': 'https://invalid.example'}
    with pytest.raises(Denied, match='method_or_scope'):
        service.client.call('sendMessage', {'chat_id': OWNER, 'text': 'Public menu', 'reply_markup': markup})
    assert fake.calls == []
    assert keyboard()['keyboard'][0][0] == {'text': BUTTONS[0][0]}


def test_tampered_durable_menu_cannot_reach_transport(bridge, admin):
    service, fake = bridge
    service.receive(update(1, '/menu'))
    with admin.transaction() as session:
        row = session.execute(select(TelegramDelivery)).scalar_one()
        body = deepcopy(row.body)
        body['reply_markup']['keyboard'][0][0]['request_contact'] = True
        row.body = body
    with pytest.raises(Denied, match='scope_or_integrity'):
        service.deliver_one()
    assert fake.calls == []
