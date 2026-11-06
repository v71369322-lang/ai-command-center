"""Telegram planning admission creates only a waiting F1 task; no provider I/O."""

import httpx
import pytest
from sqlalchemy import select

from command_center.models import ExternalAction, ExternalGrant, Task, TelegramInbox
from command_center.store import Denied
from command_center.telegram_bridge import MockTelegramHTTP, TelegramBridge
from test_telegram_bridge import BotHTTP, OWNER, message


@pytest.fixture
def bridge(store):
    fake = BotHTTP()
    client = MockTelegramHTTP(httpx.MockTransport(fake))
    yield TelegramBridge(store, client, OWNER), fake
    client.close()


def reply(service, inbox_id):
    from command_center.store import digest
    from command_center.models import TelegramDelivery
    delivery_id = digest({'profile': service.profile, 'event': inbox_id + ':reply'})
    with service.store.transaction() as session:
        return session.get(TelegramDelivery, delivery_id).body['text']


def test_prepare_creates_exact_waiting_task_without_provider_or_grant(bridge, store, monkeypatch):
    service, _ = bridge
    monkeypatch.setattr(httpx, 'Client', lambda *a, **k: pytest.fail('no provider client'))
    saved = service.receive(message(1, 'Подготовить безопасный план улучшения очереди'))
    result = service.receive(message(2, '/plan_prepare 1'))
    assert result['state'] == 'DONE'
    text = reply(service, result['inbox_id'])
    assert 'WAITING_APPROVAL' in text and 'AI ещё не вызывался' in text
    with store.transaction() as session:
        command = session.get(TelegramInbox, result['inbox_id'])
        task = session.get(Task, command.task_id)
        assert task.state == 'WAITING_APPROVAL'
        assert task.payload['kind'] == 'saved_request_plan'
        assert task.payload['planning']['request_id'] == saved['inbox_id']
        assert session.scalar(select(ExternalGrant)) is None
        assert session.scalar(select(ExternalAction)) is None


def test_prepare_is_idempotent_for_same_request_context(bridge, store):
    service, _ = bridge
    service.receive(message(1, 'Один запрос — одна задача'))
    first = service.receive(message(2, '/plan_prepare 1'))
    second = service.receive(message(3, '/plan_prepare 1'))
    with store.transaction() as session:
        assert session.get(TelegramInbox, first['inbox_id']).task_id == session.get(
            TelegramInbox, second['inbox_id']).task_id
        assert len(list(session.scalars(select(Task)))) == 1


def test_prepare_halted_finishes_without_task(bridge, store):
    service, _ = bridge
    service.receive(message(1, 'Остановленный запрос'))
    store.halt('owner')
    result = service.receive(message(2, '/plan_prepare 1'))
    assert 'новые запуски остановлены' in reply(service, result['inbox_id'])
    with store.transaction() as session:
        assert session.scalar(select(Task)) is None


def test_prepare_is_profile_scoped(bridge, store):
    service, _ = bridge
    other = TelegramBridge(store, service.client, OWNER + 1)
    other.receive(message(1, 'Чужой запрос', owner=OWNER + 1, chat=OWNER + 1))
    result = service.receive(message(2, '/plan_prepare 1'))
    assert 'не найден' in reply(service, result['inbox_id'])
    with store.transaction() as session:
        assert session.scalar(select(Task)) is None


@pytest.mark.parametrize('value', ['/plan_prepare', '/plan_prepare x',
                                   '/plan_prepare 1 extra', '/plan_prepare 9007199254740992'])
def test_prepare_reference_fails_closed(bridge, value):
    with pytest.raises(Denied, match='telegram_plan_preparation_reference_invalid'):
        bridge[0].receive(message(1, value))
