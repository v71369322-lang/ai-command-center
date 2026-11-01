import httpx
import pytest
from sqlalchemy import select

from command_center.attention_schedule import configure
from command_center.calendar_drafts import list_drafts
from command_center.models import TelegramDelivery
from command_center.store import Denied
from command_center.telegram_bridge import MockTelegramHTTP, TelegramBridge
from test_telegram_bridge import BotHTTP, OWNER, message
from test_telegram_task_status import authority, response
from uuid import uuid4


@pytest.fixture
def bridge(store):
    fake = BotHTTP()
    client = MockTelegramHTTP(httpx.MockTransport(fake))
    service = TelegramBridge(store, client, OWNER)
    configure(store, 'owner', {'enabled': True, 'timezone': 'Asia/Almaty',
              'report_times': ['09:00'], 'quiet_start': '23:00', 'quiet_end': '08:00'},
              0, str(uuid4()))
    yield service, fake
    client.close()


def callback(service, fake, choice='y', uid=2):
    while service.deliver_one():
        pass
    index, card = next((i, body) for i, body in enumerate(fake.sent, 1)
                       if body.get('reply_markup', {}).get('inline_keyboard', [[{}]])[0][0]
                       .get('callback_data', '').startswith('cl:'))
    data = next(button['callback_data'] for button in card['reply_markup']['inline_keyboard'][0]
                if button['callback_data'].endswith(':' + choice))
    return {'update_id': uid, 'callback_query': {'id': 'calendar-fixture',
            'from': {'id': OWNER, 'is_bot': False}, 'data': data,
            'message': {'message_id': index, 'chat': {'id': OWNER, 'type': 'private'}}}}


def test_calendar_card_confirmation_is_local_and_replay_safe(bridge, store):
    service, fake = bridge
    before = authority(store)
    command = message(1, '/calendar 2026-11-03 15:00 30 20 Созвон по проекту')
    service.receive(command)
    result = service.receive(callback(service, fake))
    assert result['state'] == 'DONE'
    drafts = list_drafts(store, 'owner')
    assert len(drafts) == 1 and drafts[0]['state'] == 'CONFIRMED_LOCAL'
    assert drafts[0]['document']['start'] == '2026-11-03T15:00:00+05:00'
    assert drafts[0]['external_sync'] is False
    # Calendar audit and transport bookkeeping cannot create execution authority.
    after = authority(store)
    assert after[0] == before[0] and after[1:] == before[1:]
    assert service.receive(command)['state'] == 'DONE'
    assert len(list_drafts(store, 'owner')) == 1


def test_cancel_and_list_never_call_provider(bridge, store):
    service, fake = bridge
    service.receive(message(1, '/calendar 2026-12-01 09:30 45 10 Встреча'))
    service.receive(callback(service, fake, 'n'))
    reply = response(service, message(3, '/calendar'))
    assert 'отменено' in reply and 'Google Calendar ещё не подключён' in reply
    assert list_drafts(store, 'owner')[0]['state'] == 'CANCELLED'


@pytest.mark.parametrize('value', [
    '/calendar завтра в три встреча', '/calendar 2026-11-03 25:00 30 20 Встреча',
    '/calendar 2026-11-03 15:00 0 20 Встреча', '/calendar 2026-11-03 15:00 30 2 Встреча',
])
def test_ambiguous_or_invalid_calendar_input_is_not_captured(bridge, store, value):
    service, _ = bridge
    before = authority(store)
    with pytest.raises(Denied, match='telegram_calendar_format_invalid'):
        service.receive(message(1, value))
    assert authority(store) == before


def test_forged_or_unobserved_callback_cannot_decide(bridge, store):
    service, fake = bridge
    service.receive(message(1, '/calendar 2026-11-03 15:00 30 20 Встреча'))
    update = callback(service, fake)
    with store.transaction() as session:
        delivery = session.scalar(select(TelegramDelivery).where(TelegramDelivery.state == 'SENT'))
        delivery.state = 'UNCERTAIN'
    with pytest.raises(Denied, match='calendar_card_not_observed'):
        service.receive(update)
    assert list_drafts(store, 'owner')[0]['state'] == 'DRAFT'


def test_calendar_requires_an_explicit_owner_timezone(store):
    fake = BotHTTP()
    client = MockTelegramHTTP(httpx.MockTransport(fake))
    service = TelegramBridge(store, client, OWNER)
    with pytest.raises(Denied, match='timezone_not_configured'):
        service.receive(message(1, '/calendar 2026-11-03 15:00 30 20 Встреча'))
    client.close()
