import httpx
import pytest

from command_center.store import Denied
from command_center.telegram_bridge import MockTelegramHTTP, TelegramBridge
from command_center.telegram_calendar_voice import transcription_contract, verify_transcript
from test_telegram_bridge import BotHTTP, OWNER
from test_telegram_task_status import authority, response


def voice(uid=1, **changes):
    audio = {'file_id': 'AwACAgIAAxkBAA_fixture', 'file_unique_id': 'AgADfixture123',
             'duration': 18, 'file_size': 42000, 'mime_type': 'audio/ogg'}
    audio.update(changes)
    return {'update_id': uid, 'message': {'message_id': uid + 100, 'date': 1700000000,
            'from': {'id': OWNER, 'is_bot': False}, 'chat': {'id': OWNER, 'type': 'private'},
            'caption': '/calendar', 'voice': audio}}


@pytest.fixture
def bridge(store):
    fake = BotHTTP()
    client = MockTelegramHTTP(httpx.MockTransport(fake))
    service = TelegramBridge(store, client, OWNER)
    yield service, fake
    client.close()


def test_voice_is_saved_pending_without_download_task_or_external_call(bridge, store):
    service, _ = bridge
    before = authority(store)
    result = service.receive(voice())
    assert result['state'] == 'DONE' and result['task_id'] is None
    after = authority(store)
    assert after[0] == before[0] and after[1:] == before[1:]
    reply = response(service, {'update_id': 2, 'message': {'message_id': 102, 'date': 1700000000,
        'from': {'id': OWNER, 'is_bot': False}, 'chat': {'id': OWNER, 'type': 'private'},
        'text': '/calendar'}})
    assert 'ожидающих расшифровки: 1' in reply
    assert service.receive(voice()) == result


@pytest.mark.parametrize('changes', [
    {'duration': 0}, {'duration': 121}, {'file_size': 5 * 1024 * 1024 + 1},
    {'mime_type': 'application/zip'}, {'file_unique_id': '../bad'},
])
def test_invalid_voice_metadata_fails_before_inbox_write(bridge, store, changes):
    service, _ = bridge
    before = authority(store)
    with pytest.raises(Denied, match='calendar_voice_invalid'):
        service.receive(voice(**changes))
    assert authority(store) == before


def test_voice_without_calendar_caption_routes_to_general_request(bridge):
    service, _ = bridge
    update = voice()
    update['message'].pop('caption')
    result = service.receive(update)
    assert result['state'] == 'DONE'


def test_transcript_contract_requires_exact_audio_and_owner_readback():
    intent = {'kind': 'calendar_voice'}
    request = transcription_contract(intent, 'a' * 64)
    assert request['create_event'] is False and request['requires_owner_readback'] is True
    result = verify_transcript({'audio_sha256': 'a' * 64, 'language': 'ru',
        'text': 'Завтра в 15:00 созвон на полчаса', 'duration_seconds': 17.4}, request)
    assert result == {'text': 'Завтра в 15:00 созвон на полчаса', 'audio_sha256': 'a' * 64,
                      'confirmed': False, 'event_created': False}
    with pytest.raises(Denied, match='transcription_response_invalid'):
        verify_transcript({'audio_sha256': 'b' * 64, 'language': 'ru', 'text': 'Подмена',
                           'duration_seconds': 17.4}, request)
