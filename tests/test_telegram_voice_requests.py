import httpx
import pytest

from command_center.models import TelegramInbox
from command_center.store import Denied
from command_center.telegram_bridge import MockTelegramHTTP, TelegramBridge
from command_center.telegram_voice_requests import transcription_contract, verify_transcript
from command_center.telegram_voice_transcripts import propose
from command_center.project_inbox import inbox
from test_telegram_bridge import BotHTTP, OWNER
from test_telegram_task_status import authority, response


def voice(uid=1, caption=None, **changes):
    audio = {'file_id': 'AwACAgIAAxkBAA_task_fixture', 'file_unique_id': 'AgADtaskfixture123',
             'duration': 24, 'file_size': 52000, 'mime_type': 'audio/ogg'}
    audio.update(changes)
    message = {'message_id': uid + 100, 'date': 1700000000,
               'from': {'id': OWNER, 'is_bot': False}, 'chat': {'id': OWNER, 'type': 'private'},
               'voice': audio}
    if caption is not None:
        message['caption'] = caption
    return {'update_id': uid, 'message': message}


@pytest.fixture
def bridge(store):
    fake = BotHTTP()
    client = MockTelegramHTTP(httpx.MockTransport(fake))
    service = TelegramBridge(store, client, OWNER)
    yield service, fake
    client.close()


@pytest.mark.parametrize('caption', [None, '', '/task'])
def test_voice_request_is_saved_without_download_ai_or_task(bridge, store, caption):
    service, _ = bridge
    before = authority(store)
    result = service.receive(voice(caption=caption))
    assert result['state'] == 'DONE' and result['task_id'] is None
    assert authority(store) == before
    with store.transaction() as session:
        row = session.get(TelegramInbox, result['inbox_id'])
        assert row.intent['kind'] == 'voice_request' and row.intent['file_size'] == 52000
    text = response(service, {
        'update_id': 2, 'message': {'message_id': 102, 'date': 1700000000,
        'from': {'id': OWNER, 'is_bot': False}, 'chat': {'id': OWNER, 'type': 'private'}, 'text': '/voice'}})
    assert 'ожидающие расшифровки: 1' in text and 'не запускали AI' in text


@pytest.mark.parametrize('changes', [
    {'duration': 0}, {'duration': 121}, {'file_size': 5 * 1024 * 1024 + 1},
    {'mime_type': 'application/zip'}, {'file_unique_id': '../bad'},
])
def test_invalid_voice_request_fails_before_write(bridge, store, changes):
    service, _ = bridge
    before = authority(store)
    with pytest.raises(Denied, match='voice_request_invalid'):
        service.receive(voice(**changes))
    assert authority(store) == before


def test_unknown_voice_caption_cannot_become_command(bridge):
    service, _ = bridge
    with pytest.raises(Denied, match='caption_invalid'):
        service.receive(voice(caption='/stop'))


def test_voice_transcript_contract_never_creates_task_or_selects_project():
    request = transcription_contract({'kind': 'voice_request'}, 'a' * 64)
    assert request['create_task'] is False and request['select_project'] is False
    result = verify_transcript({'audio_sha256': 'a' * 64, 'language': 'ru',
        'text': 'Проверь проект и подготовь исправление', 'duration_seconds': 20.5}, request)
    assert result['confirmed'] is False and result['task_created'] is False
    with pytest.raises(Denied, match='voice_transcription_response_invalid'):
        verify_transcript({'audio_sha256': 'b' * 64, 'language': 'ru',
            'text': 'Подмена', 'duration_seconds': 20.5}, request)


def test_system_status_is_read_only_and_names_all_roles(bridge, store):
    service, _ = bridge
    before = authority(store)
    text = response(service, {'update_id': 9, 'message': {'message_id': 109, 'date': 1700000000,
        'from': {'id': OWNER, 'is_bot': False}, 'chat': {'id': OWNER, 'type': 'private'},
        'text': '/system'}})
    for value in ('Telegram и диспетчер', 'AI-аналитик', 'Исполнитель', 'Проверяющий', 'Watchdog'):
        assert value in text
    assert 'обычные проекты ещё не подключены' in text
    assert authority(store) == before


def transcript_callback(service, fake, proposal_id, choice='y', uid=3):
    while service.deliver_one():
        pass
    data = f'vr:{proposal_id}:{choice}'
    index = next(i for i, body in enumerate(fake.sent, 1)
                 if any(button.get('callback_data') == data
                        for row in body.get('reply_markup', {}).get('inline_keyboard', []) for button in row))
    return {'update_id': uid, 'callback_query': {'id': 'voice-fixture',
        'from': {'id': OWNER, 'is_bot': False}, 'data': data,
        'message': {'message_id': index, 'chat': {'id': OWNER, 'type': 'private'}}}}


def test_verified_transcript_requires_observed_owner_confirmation_before_request(bridge, store):
    service, fake = bridge
    original = service.receive(voice())
    request = transcription_contract({'kind': 'voice_request'}, 'a' * 64)
    proposal = propose(service, original['inbox_id'], {'audio_sha256': 'a' * 64, 'language': 'ru',
        'text': 'Проверь проект и подготовь исправление', 'duration_seconds': 20.5}, request)
    assert inbox(store, 'owner')['total_pending'] == 0
    result = service.receive(transcript_callback(service, fake, proposal['proposal_id']))
    assert result['state'] == 'NEEDS_PLANNING' and result['task_id'] is None
    saved = inbox(store, 'owner')['requests'][0]
    assert saved['text'] == 'Проверь проект и подготовь исправление'
    assert saved['project_id'] is None


def test_rejected_transcript_never_enters_project_queue(bridge, store):
    service, fake = bridge
    original = service.receive(voice())
    request = transcription_contract({'kind': 'voice_request'}, 'b' * 64)
    proposal = propose(service, original['inbox_id'], {'audio_sha256': 'b' * 64, 'language': 'ru',
        'text': 'Ошибочная расшифровка', 'duration_seconds': 20.5}, request)
    result = service.receive(transcript_callback(service, fake, proposal['proposal_id'], 'n'))
    assert result['state'] == 'DONE'
    assert inbox(store, 'owner')['total_pending'] == 0
