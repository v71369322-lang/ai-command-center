"""Reversible request archive and unknown-command containment."""
import httpx
import pytest
from sqlalchemy import select

from command_center.models import Audit, Task, TelegramDelivery, TelegramInbox
from command_center.planning_task import create_task
from command_center.request_lifecycle import EVENT
from command_center.request_planning import context
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
    delivery_id = digest({'profile': service.profile, 'event': inbox_id + ':reply'})
    with service.store.transaction() as session:
        return session.get(TelegramDelivery, delivery_id).body['text']


def test_archive_removes_unplanned_request_and_restore_returns_it(bridge, store):
    service, _ = bridge
    saved = service.receive(message(1, 'Тестовый запрос'))
    archived = service.receive(message(2, '/archive_request 1'))
    assert archived['state'] == 'DONE'
    assert 'архивирован' in reply(service, archived['inbox_id'])
    with store.transaction() as session:
        assert session.get(TelegramInbox, saved['inbox_id']).state == 'ARCHIVED'
        event = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == EVENT))
        assert event.event['state'] == 'ARCHIVED' and event.event['version'] == 1
    assert service.receive(message(1, 'Тестовый запрос'))['state'] == 'ARCHIVED'
    requests = service.receive(message(3, '/requests'))
    assert 'пока нет' in reply(service, requests['inbox_id'])

    restored = service.receive(message(4, '/restore_request 1'))
    assert 'возвращён' in reply(service, restored['inbox_id'])
    with store.transaction() as session:
        assert session.get(TelegramInbox, saved['inbox_id']).state == 'NEEDS_PLANNING'
        events = list(session.scalars(select(Audit).where(Audit.event['kind'].as_string() == EVENT)
                                      .order_by(Audit.sequence)))
        assert [row.event['state'] for row in events] == ['ARCHIVED', 'NEEDS_PLANNING']
        assert [row.event['version'] for row in events] == [1, 2]


def test_unknown_slash_command_is_not_saved_as_request(bridge, store):
    service, _ = bridge
    result = service.receive(message(1, '/revieew 123'))
    assert result['state'] == 'DONE'
    assert 'Неизвестная команда' in reply(service, result['inbox_id'])
    with store.transaction() as session:
        row = session.get(TelegramInbox, result['inbox_id'])
        assert row.intent == {'kind': 'unknown_command'} and row.task_id is None
        assert session.scalar(select(Task.id)) is None


def test_task_caption_remains_a_saved_request(bridge):
    service, _ = bridge
    result = service.receive(message(1, '/task Проверить отчёт'))
    assert result['state'] == 'NEEDS_PLANNING'
    with service.store.transaction() as session:
        assert session.get(TelegramInbox, result['inbox_id']).intent == {
            'kind': 'capture', 'text': 'Проверить отчёт'}


def test_request_with_planning_task_cannot_be_archived(bridge, store):
    service, _ = bridge
    saved = service.receive(message(1, 'Запрос с подготовкой'))
    create_task(store, 'owner', context(store, 'owner', saved['inbox_id']))
    with pytest.raises(Denied, match='request_lifecycle_task_exists'):
        service.receive(message(2, '/archive_request 1'))
    with store.transaction() as session:
        assert session.get(TelegramInbox, saved['inbox_id']).state == 'NEEDS_PLANNING'


def test_lifecycle_is_profile_scoped(bridge, store):
    service, _ = bridge
    other = TelegramBridge(store, service.client, OWNER + 1)
    foreign = other.receive(message(1, 'Чужой профиль', owner=OWNER + 1, chat=OWNER + 1))
    result = service.receive(message(2, '/archive_request 1'))
    assert 'не найден' in reply(service, result['inbox_id'])
    with store.transaction() as session:
        assert session.get(TelegramInbox, foreign['inbox_id']).state == 'NEEDS_PLANNING'


def test_forged_lifecycle_history_fails_closed(bridge, store):
    service, _ = bridge
    saved = service.receive(message(1, 'Запрос с повреждённой историей'))
    with store.transaction() as session:
        store.audit(session, EVENT, 'owner', request_id=saved['inbox_id'],
                    request_fingerprint='0' * 64, state='ARCHIVED', version=2,
                    operation_id=service.profile + ':99', input_hash='0' * 64)
    with pytest.raises(Denied, match='request_lifecycle_history_invalid'):
        service.receive(message(2, '/archive_request 1'))
    with store.transaction() as session:
        assert session.get(TelegramInbox, saved['inbox_id']).state == 'NEEDS_PLANNING'


@pytest.mark.parametrize('value', ['/archive_request', '/archive_request x',
                                   '/restore_request 1 extra', '/archive_request 9007199254740992'])
def test_invalid_lifecycle_reference_fails_closed(bridge, value):
    with pytest.raises(Denied, match='telegram_request_lifecycle_reference_invalid'):
        bridge[0].receive(message(1, value))
