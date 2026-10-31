"""Owner Telegram views for the attention center remain read-only and replay-safe."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from command_center.attention_schedule import configure
from command_center.models import TelegramDelivery, TelegramInbox
from command_center.store import Denied
from command_center.telegram_bridge import MockTelegramHTTP, TelegramBridge
from command_center.telegram_menu import keyboard
from test_telegram_bridge import BotHTTP, OWNER, message
from test_telegram_task_status import authority, response


@pytest.fixture
def bridge(store):
    client = MockTelegramHTTP(httpx.MockTransport(BotHTTP()))
    yield TelegramBridge(store, client, OWNER)
    client.close()


def test_attention_snapshot_is_bounded_read_only_and_uses_shared_counts(bridge, store):
    bridge.receive(message(1, 'Секретный текст заявки, который не должен попасть в сводку'))
    store.halt('owner')
    before = authority(store)
    reply = response(bridge, message(2, '/attention'))
    assert 'Центр внимания AI Commander' in reply
    assert '1 · Новые запуски остановлены' in reply
    assert 'Запросов без проекта: 1.' in reply
    assert 'Запросов, ожидающих планирования: 1.' in reply
    assert 'Секретный текст' not in reply
    assert 'выполнение не запускалось' in reply and len(reply) < 4096
    assert authority(store) == before


def test_reminder_status_reads_exact_version_without_configuring(bridge, store):
    before = authority(store)
    assert 'ещё не настроены' in response(bridge, message(1, '/reminders'))
    assert authority(store) == before
    document = {'enabled': True, 'timezone': 'Asia/Almaty',
                'report_times': ['09:15', '18:30'], 'quiet_start': '22:00', 'quiet_end': '07:00'}
    configure(store, 'owner', document, 0, str(uuid4()))
    before = authority(store)
    reply = response(bridge, message(2, '/reminders'))
    assert 'Напоминания центра внимания: включены.' in reply
    assert 'Часовой пояс: Asia/Almaty.' in reply
    assert 'Время сводок: 09:15, 18:30.' in reply
    assert 'Тихие часы: 22:00–07:00.' in reply and 'Версия настройки: 1.' in reply
    assert authority(store) == before


@pytest.mark.parametrize('command', ['/attention now', '/reminders enable', '/attention /stop'])
def test_attention_arguments_are_rejected_without_capture_or_authority(bridge, store, command):
    before = authority(store)
    with pytest.raises(Denied, match='attention_arguments_forbidden'):
        bridge.receive(message(1, command))
    with store.transaction() as session:
        assert session.execute(select(TelegramInbox)).first() is None
    assert authority(store) == before


def test_duplicate_restart_and_lost_ack_keep_one_durable_snapshot(bridge, store):
    bridge.receive(message(1, 'Запрос'))
    command = message(2, '/attention')
    before = authority(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(bridge.receive, [command, command]))
    initial = response(bridge, command)
    restarted = TelegramBridge(store, bridge.client, OWNER)
    assert results[0] == results[1] == restarted.receive(command)
    assert response(restarted, command) == initial
    with store.transaction() as session:
        deliveries = session.execute(select(TelegramDelivery)).scalars().all()
        assert len(deliveries) == 2
    assert authority(store) == before


def test_foreign_or_group_chat_cannot_read_attention(bridge):
    update = message(1, '/attention')
    update['message']['chat']['type'] = 'group'
    with pytest.raises(Denied, match='owner_private_chat'):
        bridge.receive(update)


def test_owner_menu_exposes_read_only_attention_views():
    rows = [[button['text'] for button in row] for row in keyboard()['keyboard']]
    assert rows == [['📁 Проекты', '📥 Запросы'], ['🔔 Центр внимания', '⏰ Напоминания'],
                    ['🧪 Результаты тестов', 'ℹ️ Помощь']]
