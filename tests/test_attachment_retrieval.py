"""Public synthetic fixtures; local HTTP checks plus CI PostgreSQL acceptance."""
from copy import deepcopy

import httpx
import pytest
from sqlalchemy import select

from command_center.models import Audit, Control, TelegramDelivery, TelegramInbox
from command_center.store import Denied
from command_center.telegram_attachment_retrieval import keyboard, allowed_markup
from command_center.telegram_bridge import TelegramBridge
from command_center.telegram_transport import TelegramHTTPError
from test_attachment_copies import copies as copies, DATA
from test_telegram_bridge import OWNER, message
from test_telegram_task_status import authority
from test_telegram_voice_files import client, TOKEN


def test_multipart_upload_is_fixed_host_owner_and_exact_bytes():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.host == 'api.telegram.org' and request.url.path.endswith('/sendDocument')
        assert DATA in request.content and str(OWNER).encode() in request.content
        assert b'attachment-1.pdf' in request.content
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': 51, 'chat': {'id': OWNER}}})
    configured = client(handler)
    configured.owner = OWNER
    try:
        assert configured.send_document(DATA, 'attachment-1.pdf')['message_id'] == 51
        for bad in ['../secret', 'https://outside.test/file', 'attachment-1.pdf\r\nHeader: x']:
            with pytest.raises(Denied):
                configured.send_document(DATA, bad)
        assert len(calls) == 1
    finally:
        configured.close()


@pytest.mark.parametrize('response', [
    httpx.Response(302, headers={'location': 'https://outside.test'}),
    httpx.Response(200, content=b'x' * 65537),
    httpx.Response(200, json={'ok': True, 'result': {'message_id': 1, 'chat': {'id': OWNER + 1}}}),
])
def test_upload_rejects_redirect_oversize_and_wrong_recipient(response):
    configured = client(lambda _: response)
    configured.owner = OWNER
    try:
        with pytest.raises((Denied, TelegramHTTPError)) as error:
            configured.send_document(DATA, 'attachment-1.bin')
        assert TOKEN not in str(error.value)
    finally:
        configured.close()


def test_button_shape_does_not_allow_urls_or_another_action():
    assert allowed_markup(keyboard('1'))
    changed = deepcopy(keyboard('1'))
    changed['inline_keyboard'][0][0]['url'] = 'https://outside.test'
    assert not allowed_markup(changed)
    for bad in ['-1', '01', '9007199254740992', '1/../2']:
        with pytest.raises(Denied):
            keyboard(bad)


def file_rows(store):
    with store.transaction() as tx:
        return list(tx.scalars(select(TelegramDelivery).where(TelegramDelivery.body.op('?')('attachment'))))


def prepare(copies):
    bridge, runner, _, _ = copies
    assert runner.process_one()['state'] == 'ATTACHMENT_COPIED'
    return bridge


def drain(bridge):
    for _ in range(20):
        if bridge.deliver_one() is None:
            return
    raise AssertionError('synthetic delivery queue did not drain')


def test_explicit_request_sends_db_copy_once_after_restart(copies, store, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    bridge = prepare(copies)
    before = authority(store)
    bridge.receive(message(2, 'Пришли файл №1'))
    bridge.receive(message(2, 'Пришли файл №1'))
    sent = []
    bridge.client.send_document = lambda data, name: (sent.append((data, name)) or
        {'message_id': 99, 'chat': {'id': OWNER}})
    restarted = TelegramBridge(store, bridge.client, OWNER)
    drain(restarted)
    drain(restarted)
    assert sent == [(DATA, 'attachment-1.pdf')]
    rows = file_rows(store)
    assert len(rows) == 1 and rows[0].state == 'SENT'
    assert 'data64' not in str(rows[0].body) and rows[0].message_id == 99
    assert authority(store) == before


def test_callback_and_private_owner_scope(copies, store):
    bridge = prepare(copies)
    update = message(2, '')
    update['callback_query'] = {'id': 'public-fixture', 'from': update['message']['from'],
        'message': update.pop('message'), 'data': 'af:1'}
    bridge.receive(update)
    assert len(file_rows(store)) == 1
    update = message(3, '/file 1', owner=OWNER + 1)
    with pytest.raises(Denied, match='owner_private'):
        bridge.receive(update)
    assert len(file_rows(store)) == 1


@pytest.mark.parametrize('change', ['stop', 'epoch', 'corrupt', 'revision'])
def test_changed_admission_or_copy_suppresses_queued_upload(copies, store, change):
    bridge = prepare(copies)
    bridge.receive(message(2, '/file 1'))
    with store.transaction() as tx:
        if change == 'stop':
            tx.get(Control, 1).halted = True
        elif change == 'epoch':
            tx.get(Control, 1).epoch += 1
        elif change == 'revision':
            from dataclasses import replace
            store.settings = replace(store.settings, source_revision='e' * 40)
        else:
            from command_center.attachment_copies import identity
            source = tx.get(TelegramInbox, copies[3])
            row = tx.get(TelegramInbox, identity(source)[1])
            row.intent = dict(row.intent, sha256='0' * 64)
    bridge.client.send_document = lambda *_: pytest.fail('revoked upload must not be sent')
    drain(bridge)
    assert file_rows(store)[0].state == 'CANCELLED'


def test_uncertain_http_is_never_automatically_retried(copies, store):
    bridge = prepare(copies)
    bridge.receive(message(2, '/file 1'))
    calls = []
    def lost(*args):
        calls.append(True)
        raise TelegramHTTPError('telegram_document_delivery_uncertain')
    bridge.client.send_document = lost
    drain(bridge)
    drain(TelegramBridge(store, bridge.client, OWNER))
    assert calls == [True] and file_rows(store)[0].state == 'UNCERTAIN'
    with store.transaction() as tx:
        assert not list(tx.scalars(select(Audit).where(Audit.event['kind'].as_string() == 'task_created')))
        notices = [r for r in tx.scalars(select(TelegramDelivery))
                   if 'Отправка файла не подтверждена' in r.body.get('text', '')]
        assert len(notices) == 1 and notices[0].state == 'SENT'


def test_missing_copy_keeps_original_and_cannot_upload(copies, store):
    bridge, _, _, iid = copies
    bridge.receive(message(2, '/file 1'))
    bridge.receive(message(3, '/file 999'))
    assert file_rows(store) == []
    with store.transaction() as tx:
        assert tx.get(TelegramInbox, iid).state == 'NEEDS_PLANNING'


def test_body_tampering_is_rejected_before_upload(copies, store):
    bridge = prepare(copies)
    bridge.receive(message(2, '/file 1'))
    oid = file_rows(store)[0].id
    with store.transaction() as tx:
        row = tx.get(TelegramDelivery, oid)
        row.body = dict(row.body, chat_id=OWNER + 1)
    bridge.client.send_document = lambda *_: pytest.fail('tampered upload')
    with pytest.raises(Denied, match='scope_or_integrity'):
        drain(bridge)
