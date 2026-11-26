"""Attachment references are data, never commands or downloaded/executed files."""
from copy import deepcopy

import httpx
import pytest
from sqlalchemy import select

from command_center.models import Audit, TelegramDelivery, TelegramInbox
from command_center.store import Denied
from command_center.telegram_attachments import MAX_BYTES, parse_message, summary
from command_center.telegram_bridge import MockTelegramHTTP, TelegramBridge
from command_center.telegram_requests import captured_text
from test_telegram_bridge import BotHTTP, OWNER, message
from test_telegram_task_status import authority, response
from test_telegram_service import configured as configured


def attachment(uid=1, media='document', caption='/stop'):
    update = message(uid, '')
    msg = update['message']
    del msg['text']
    item = {'file_id': 'attachment-fixture', 'file_unique_id': 'stable-fixture', 'file_size': 1234}
    msg[media] = [item] if media == 'photo' else {**item, 'file_name': 'notes.pdf'}
    msg['caption'] = caption
    return update


@pytest.mark.parametrize('media', ['photo', 'document'])
def test_reference_summary_does_not_expose_file_ids_or_execute_caption(media):
    intent = parse_message(attachment(media=media)['message'])
    assert intent['media'] == media
    assert '/stop' in summary(intent)
    assert intent['file_id'] not in summary(intent)


@pytest.mark.parametrize('field,value', [('file_id', '../escape'), ('file_unique_id', ''),
    ('file_size', True), ('file_size', 0), ('file_size', MAX_BYTES + 1),
    ('file_name', 'x' * 241), ('file_name', 'bad\x00name')])
def test_invalid_metadata_is_rejected(field, value):
    msg = attachment()['message']
    msg['document'][field] = value
    with pytest.raises(Denied, match='attachment_invalid'):
        parse_message(msg)


def test_photo_selection_is_largest_and_caption_cannot_leak_known_secret():
    msg = attachment(media='photo')['message']
    msg['photo'].append({**msg['photo'][0], 'file_id': 'larger-fixture', 'file_size': 4321})
    assert parse_message(msg)['file_id'] == 'larger-fixture'
    with pytest.raises(Denied):
        parse_message(msg, lambda text: '/stop' in text)
    msg['document'] = {}
    with pytest.raises(Denied):
        parse_message(msg)


@pytest.fixture
def attachments(store, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    fake = BotHTTP()
    client = MockTelegramHTTP(httpx.MockTransport(fake))
    yield TelegramBridge(store, client, OWNER), fake
    client.close()


@pytest.mark.parametrize('media', ['photo', 'document'])
def test_owner_attachment_survives_reopen_without_commands_downloads_or_authority(attachments, store, media):
    bridge, fake = attachments
    before = authority(store)
    update = attachment(media=media)
    saved = bridge.receive(update)
    assert saved['state'] == 'NEEDS_PLANNING' and saved['task_id'] is None
    assert bridge.receive(update) == saved
    reopened = TelegramBridge(store, bridge.client, OWNER)
    text = response(reopened, message(2, '/request 1'))
    assert '/stop' in text and 'attachment-fixture' not in text
    assert 'notes.pdf' in text if media == 'document' else 'Фотография' in text
    assert '№1' in response(reopened, message(3, '/requests'))
    with store.transaction() as session:
        row = session.get(TelegramInbox, saved['inbox_id'])
        assert '/stop' in captured_text(session, row)
        assert len(list(session.scalars(select(TelegramDelivery).where(
            TelegramDelivery.id == saved['inbox_id'] + ':reply')))) == 1
        assert not list(session.scalars(select(Audit).where(
            Audit.event['kind'].as_string() == 'personal_inbox_record_created')))
    while bridge.deliver_one():
        pass
    assert 'содержимое не прочитано' in fake.sent[0]['text']
    assert authority(store) == before


def test_sensitive_or_foreign_attachment_is_rejected_before_intake(attachments, store):
    bridge, _ = attachments
    update = attachment()
    update['message']['from']['id'] = OWNER + 1
    with pytest.raises(Denied):
        bridge.receive(update)
    update = attachment(caption='PRIVATE KEY')
    with pytest.raises(Denied):
        bridge.receive(update)
    with store.transaction() as session:
        assert not list(session.scalars(select(TelegramInbox)))
    update = attachment()
    bridge.receive(update)
    altered = deepcopy(update)
    altered['message']['document']['file_id'] = 'changed-fixture'
    with pytest.raises(Denied, match='reused'):
        bridge.receive(altered)


def test_configured_polling_reloads_attachment_and_never_calls_file_api(configured, store, monkeypatch):
    from test_telegram_service import FakeBot, client_for, update
    from command_center.telegram_service import TelegramService
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    fake = FakeBot()
    fake.updates = [attachment(caption='Напомни завтра в 11 проверить файл')]
    client = client_for(configured, fake)
    before = authority(store)
    try:
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        fake.updates = [update(2, '/request 1')]
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        assert any('Документ: notes.pdf' in b['text'] for b in fake.sent)
        assert set(method for method, _ in fake.calls) <= {
            'getMe', 'getWebhookInfo', 'getUpdates', 'sendMessage'}
        assert authority(store) == before
        with store.transaction() as session:
            assert not list(session.scalars(select(Audit).where(Audit.event['kind'].as_string().in_(
                ['personal_inbox_record_created', 'personal_inbox_reminder_queued']))))
    finally:
        client.close()
