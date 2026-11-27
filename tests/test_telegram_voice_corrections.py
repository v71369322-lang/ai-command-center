import pytest
from sqlalchemy import select

from command_center.models import Audit, TelegramInbox
from command_center.project_inbox import inbox
from command_center.store import Denied
from command_center.telegram_voice_requests import transcription_contract
from command_center.telegram_voice_transcripts import CORRECTED, PROPOSED, TITLE, propose
from test_telegram_bridge import OWNER
from test_telegram_task_status import authority, response
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



def test_fragment_edit_keeps_raw_text_and_uses_existing_one_save_boundary(bridge, store):
    service, fake = bridge
    _, proposal = prepared(service)
    before = authority(store)
    update = reply(service, fake, proposal, 'Замени «15» на «09:15»')
    service.receive(update)
    service.receive(update)
    edit = corrected(store)
    assert edit['text'] == 'Встреча завтра в 09:15 часов'
    assert edit['edit_mode'] == 'replace_once' and edit['confirmed'] is False
    with store.transaction() as tx:
        raw = tx.scalar(select(Audit).where(Audit.event['kind'].as_string() == PROPOSED)).event
        assert raw['text'] == 'Встреча завтра в 15 часов'
        assert edit['previous_text_hash'] == raw['text_hash']
    assert inbox(store, 'owner')['total_pending'] == 0
    service.receive(transcript_callback(service, fake, proposal['proposal_id'], uid=11))
    assert inbox(store, 'owner')['total_pending'] == 0
    service.receive(transcript_callback(service, fake, edit['proposal_id'], uid=12))
    service.receive(transcript_callback(service, fake, edit['proposal_id'], uid=13))
    saved = inbox(store, 'owner')['requests']
    assert len(saved) == 1 and saved[0]['text'] == edit['text']
    assert authority(store) == before


@pytest.mark.parametrize('value', ['Замени «нет» на «да»', 'Замени 15 на 16'])
def test_invalid_fragment_creates_no_correction_or_saved_request(bridge, store, value):
    service, fake = bridge
    _, proposal = prepared(service)
    receipt = response(service, reply(service, fake, proposal, value))
    with store.transaction() as tx:
        assert tx.scalar(select(Audit).where(Audit.event['kind'].as_string() == CORRECTED)) is None
    assert 'Правка не применена' in receipt
    assert inbox(store, 'owner')['total_pending'] == 0


def test_chained_fragment_edit_and_stale_reply_keep_latest_whole_text(bridge, store):
    service, fake = bridge
    _, proposal = prepared(service)
    service.receive(reply(service, fake, proposal, 'Замени «15» на «16»'))
    first = corrected(store)
    service.receive(reply(service, fake, first, 'Замени «завтра» на «послезавтра»', uid=11))
    latest = corrected(store)
    assert latest['text'] == 'Встреча послезавтра в 16 часов'
    service.receive(reply(service, fake, first, 'Замени «16» на «17»', uid=12))
    assert corrected(store)['proposal_id'] == latest['proposal_id']
    service.receive(transcript_callback(service, fake, latest['proposal_id'], uid=13))
    assert inbox(store, 'owner')['requests'][0]['text'] == latest['text']


def test_fragment_result_cannot_exceed_existing_text_budget(bridge, store):
    service, fake = bridge
    _, proposal = prepared(service)
    value = 'Замени «15» на «' + 'x' * (2000 - len('Замени «15» на «»'.encode())) + '»'
    assert len(value.encode()) == 2000
    receipt = response(service, reply(service, fake, proposal, value))
    assert 'итоговый текст слишком длинный' in receipt
    with store.transaction() as tx:
        assert tx.scalar(select(Audit).where(Audit.event['kind'].as_string() == CORRECTED)) is None


def test_fragment_previous_hash_tamper_is_refused(bridge, store, admin):
    service, fake = bridge
    _, proposal = prepared(service)
    service.receive(reply(service, fake, proposal, 'Замени «15» на «16»'))
    edit = corrected(store)
    callback = transcript_callback(service, fake, edit['proposal_id'], uid=11)
    assert inbox(store, 'owner')['total_pending'] == 0
    # Fault injection uses the test admin, never weaker application permissions.
    with admin.transaction() as tx:
        audit = tx.scalar(select(Audit).where(Audit.event['kind'].as_string() == CORRECTED))
        audit.event = {**audit.event, 'previous_text_hash': '0' * 64}
    from command_center.telegram_voice_transcripts import _proposal
    with pytest.raises(Denied, match='voice_correction_integrity'):
        with store.transaction() as tx:
            _proposal(service, tx, {'proposal_id': edit['proposal_id'],
                'message_id': callback['callback_query']['message']['message_id']})



def test_full_and_fragment_corrections_can_be_combined_without_losing_provenance(bridge, store):
    service, fake = bridge
    _, proposal = prepared(service)
    service.receive(reply(service, fake, proposal, 'Встреча послезавтра в 16 часов'))
    first = corrected(store)
    assert 'edit_mode' not in first
    service.receive(reply(service, fake, first, 'Замени «16» на «17»', uid=11))
    second = corrected(store)
    assert second['text'] == 'Встреча послезавтра в 17 часов'
    service.receive(reply(service, fake, second, 'Встреча без назначенного времени', uid=12))
    third = corrected(store)
    assert 'edit_mode' not in third
    service.receive(transcript_callback(service, fake, third['proposal_id'], uid=13))
    assert inbox(store, 'owner')['requests'][0]['text'] == 'Встреча без назначенного времени'
