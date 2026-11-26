"""Exercise the configured outbound transport, not the permissive bridge mock."""
from copy import deepcopy
from uuid import uuid4

import pytest

from command_center.store import Denied
from command_center.telegram_calendar import keyboard
from command_center.telegram_transport import ConfiguredTelegramHTTP
from test_telegram_service import configured as configured


def transport():
    client = object.__new__(ConfiguredTelegramHTTP)
    client.owner = 1234567
    client._token = 'PUBLIC_FIXTURE'
    return client


@pytest.mark.parametrize('version', [1, 2])
def test_configured_transport_accepts_exact_calendar_confirmation(version):
    transport().validate('sendMessage', {'chat_id': 1234567, 'text': 'Проверьте встречу',
                                       'reply_markup': keyboard(str(uuid4()), version)})


@pytest.mark.parametrize('attack', ['url', 'label', 'other_id', 'version', 'extra', 'invalid_uuid', 'row'])
def test_calendar_allowlist_rejects_modified_markup(attack):
    markup = deepcopy(keyboard(str(uuid4()), 1))
    row = markup['inline_keyboard'][0]
    if attack == 'url':
        row[0]['url'] = 'https://outside.example/'
    elif attack == 'label':
        row[0]['text'] = 'Другая операция'
    elif attack == 'other_id':
        row[1]['callback_data'] = f'cl:{uuid4()}:1:n'
    elif attack == 'version':
        row[0]['callback_data'] = row[0]['callback_data'].replace(':1:', ':3:')
    elif attack == 'extra':
        markup['resize_keyboard'] = True
    elif attack == 'invalid_uuid':
        for button in row:
            button['callback_data'] = 'cl:' + 'a' * 36 + ':1:' + button['callback_data'][-1]
    else:
        markup['inline_keyboard'].append(deepcopy(row))
    with pytest.raises(Denied, match='telegram_method_or_scope_forbidden'):
        transport().validate('sendMessage', {'chat_id': 1234567, 'text': 'Встреча', 'reply_markup': markup})


def test_calendar_card_passes_real_configured_polling_transport(configured, store):
    from command_center.attention_schedule import configure
    from command_center.telegram_service import TelegramService
    from test_telegram_service import FakeBot, client_for, update
    configure(store, 'owner', {'enabled': False, 'timezone': 'Europe/Moscow',
        'report_times': ['09:00'], 'quiet_start': '23:00', 'quiet_end': '08:00'}, 0, str(uuid4()))
    fake = FakeBot()
    fake.updates = [update(1, '/calendar 2026-12-01 15:00 10 20 Проверка встречи')]
    client = client_for(configured, fake)
    try:
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        assert len(fake.sent) == 1
        assert fake.sent[0]['reply_markup']['inline_keyboard'][0][0]['text'] == 'Добавить в календарь'
    finally:
        client.close()
