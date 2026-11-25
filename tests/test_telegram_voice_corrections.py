import pytest
from sqlalchemy import select

from command_center.models import Audit, TelegramInbox
from command_center.project_inbox import inbox
from command_center.store import Denied
from command_center.telegram_voice_requests import transcription_contract
from command_center.telegram_voice_transcripts import CORRECTED, PROPOSED, TITLE, propose
from test_telegram_bridge import OWNER
from test_telegram_task_status import authority
from test_telegram_voice_requests import bridge as bridge, transcript_callback, voice


def prepared(service):
    original = service.receive(voice())
    request = transcription_contract({'kind': 'voice_request'}, 'a' * 64)
    proposal = propose(service, original['inbox_id'], {'audio_sha256': 'a' * 64, 'language': 'ru',
        'text': 'Встреча завтра в 15 часов', 'duration_seconds': 20.5}, request)
    return original, proposal


def reply(service, fake, proposal, value='Встреча послезавтра в 16 часов', uid=10):
    callback = transcript_callback(service, fake, proposal['proposal_id'], uid=uid)
    mid = callback['callback_query']['message']['message_id']
    return {'update_id': uid, 'message': {'message_id': uid + 100, 'date': 1700000000,
        'from': {'id': OWNER, 'is_bot': False}, 'chat': {'id': OWNER, 'type': 'private'},
        'text': value, 'reply_to_message': {'message_id': mid, 'text': fake.sent[mid - 1]['text']}}}


def corrected(store):
    with store.transaction() as session:
        return session.scalar(select(Audit).where(Audit.event['kind'].as_string() == CORRECTED)
                              .order_by(Audit.sequence.desc())).event


def test_reply_creates_owner_version_and_only_confirmation_saves_it(bridge, store, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    service, fake = bridge
    _, proposal = prepared(service)
    before = authority(store)
    update = reply(service, fake, proposal)
    assert service.receive(update)['state'] == 'DONE'
    assert service.receive(update)['state'] == 'DONE'
    assert inbox(store, 'owner')['total_pending'] == 0
    edit = corrected(store)
    assert edit['actor'] == 'owner' and edit['previous_proposal_id'] == proposal['proposal_id']
    assert edit['confirmed'] is False and edit['task_created'] is False
    with store.transaction() as session:
        raw = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == PROPOSED)).event
        assert raw['text'] == 'Встреча завтра в 15 часов'
        assert raw['audio_sha256'] == edit['audio_sha256']
    result = service.receive(transcript_callback(service, fake, edit['proposal_id'], uid=11))
    assert result['state'] == 'NEEDS_PLANNING' and result['task_id'] is None
    saved = inbox(store, 'owner')['requests']
    assert len(saved) == 1 and saved[0]['text'] == update['message']['text']
    assert authority(store) == before


@pytest.mark.parametrize('choice', ['y', 'n'])
def test_old_card_cannot_save_or_discard_corrected_version(bridge, store, choice):
    service, fake = bridge
    _, proposal = prepared(service)
    service.receive(reply(service, fake, proposal))
    edit = corrected(store)
    assert service.receive(transcript_callback(service, fake, proposal['proposal_id'], choice, uid=11))['state'] == 'DONE'
    assert inbox(store, 'owner')['total_pending'] == 0
    service.receive(transcript_callback(service, fake, edit['proposal_id'], uid=12))
    service.receive(transcript_callback(service, fake, proposal['proposal_id'], uid=13))
    service.receive(transcript_callback(service, fake, edit['proposal_id'], uid=14))
    assert inbox(store, 'owner')['total_pending'] == 1


def test_second_edit_supersedes_first_without_duplicate_request(bridge, store):
    service, fake = bridge
    _, proposal = prepared(service)
    service.receive(reply(service, fake, proposal))
    first = corrected(store)
    service.receive(reply(service, fake, first, 'Встреча без назначенного времени', uid=11))
    second = corrected(store)
    service.receive(transcript_callback(service, fake, first['proposal_id'], uid=12))
    service.receive(transcript_callback(service, fake, second['proposal_id'], uid=13))
    saved = inbox(store, 'owner')['requests']
    assert len(saved) == 1 and saved[0]['text'] == 'Встреча без назначенного времени'


def test_edit_of_old_or_consumed_card_creates_no_new_version(bridge, store):
    service, fake = bridge
    _, proposal = prepared(service)
    service.receive(reply(service, fake, proposal))
    first = corrected(store)
    service.receive(reply(service, fake, proposal, 'Нежелательная устаревшая правка', uid=11))
    assert corrected(store)['proposal_id'] == first['proposal_id']
    service.receive(transcript_callback(service, fake, first['proposal_id'], uid=12))
    service.receive(reply(service, fake, first, 'Правка после сохранения', uid=13))
    assert corrected(store)['proposal_id'] == first['proposal_id']
    assert inbox(store, 'owner')['total_pending'] == 1


def test_forged_quote_does_not_bind_arbitrary_message_or_create_request(bridge, store):
    service, fake = bridge
    _, proposal = prepared(service)
    update = reply(service, fake, proposal)
    update['message']['reply_to_message']['message_id'] = 999999
    assert service.receive(update)['state'] == 'DONE'
    assert inbox(store, 'owner')['total_pending'] == 0
    with store.transaction() as session:
        assert session.scalar(select(Audit).where(Audit.event['kind'].as_string() == CORRECTED)) is None


def test_reply_content_is_data_not_a_control_command(bridge, store):
    service, fake = bridge
    _, proposal = prepared(service)
    before = authority(store)
    service.receive(reply(service, fake, proposal, '/stop'))
    assert corrected(store)['text'] == '/stop'
    assert authority(store) == before


def test_tampered_owner_edit_cannot_be_accepted(bridge, store):
    service, fake = bridge
    _, proposal = prepared(service)
    result = service.receive(reply(service, fake, proposal))
    edit = corrected(store)
    with store.transaction() as session:
        session.get(TelegramInbox, result['inbox_id']).intent = {'kind': 'capture', 'text': 'Подмена'}
    with pytest.raises(Denied, match='voice_correction_integrity'):
        service.receive(transcript_callback(service, fake, edit['proposal_id'], uid=11))


def test_unrelated_reply_stays_an_ordinary_capture(bridge, store):
    service, _ = bridge
    update = {'update_id': 30, 'message': {'message_id': 130, 'date': 1700000000,
        'from': {'id': OWNER, 'is_bot': False}, 'chat': {'id': OWNER, 'type': 'private'},
        'text': 'Новая идея', 'reply_to_message': {'message_id': 5, 'text': 'Другое сообщение'}}}
    assert service.receive(update)['state'] == 'NEEDS_PLANNING'
    assert inbox(store, 'owner')['requests'][0]['text'] == 'Новая идея'


@pytest.mark.parametrize('reply_id', [True, 0, -1, '1'])
def test_invalid_quote_id_is_rejected_before_inbox_write(bridge, reply_id):
    service, _ = bridge
    update = {'update_id': 30, 'message': {'message_id': 130, 'date': 1700000000,
        'from': {'id': OWNER, 'is_bot': False}, 'chat': {'id': OWNER, 'type': 'private'},
        'text': 'Исправление', 'reply_to_message': {'message_id': reply_id, 'text': TITLE}}}
    with pytest.raises(Denied, match='voice_edit_invalid'):
        service.normalize(update)
