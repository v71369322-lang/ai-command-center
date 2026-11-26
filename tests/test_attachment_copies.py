from copy import deepcopy
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from command_center.attachment_copies import AttachmentCopier, encode, decode, read_copy, identity, STORED, FAILED
from command_center.attachment_files import AttachmentFiles
from command_center.models import Audit, Control, TelegramInbox
from command_center.store import Denied, Store
from command_center.telegram_bridge import MockTelegramHTTP, TelegramBridge
from command_center.telegram_transport import TelegramHTTPError
from command_center.voice_worker import VoiceWorker
from test_telegram_attachments import attachment
from test_telegram_bridge import BotHTTP, OWNER, message
from test_telegram_task_status import response, authority
from test_telegram_voice_files import client, TOKEN
from test_voice_worker import Download, Decoder


DATA = b'inert\x00file\xff'


def source():
    return SimpleNamespace(id='a' * 64 + ':1', profile='a' * 64,
                           fingerprint='b' * 64, intent={'file_size': len(DATA)})


def test_binary_codec_roundtrip_binds_original_source_and_size():
    original = source()
    document = encode(original, DATA, sha256(DATA).hexdigest())
    assert decode(document, original) == DATA
    other = source()
    other.fingerprint = 'c' * 64
    with pytest.raises(Denied):
        decode(document, other)
    with pytest.raises(Denied):
        encode(original, DATA + b'changed', sha256(DATA).hexdigest())


@pytest.mark.parametrize('field,value', [('data64', 'bad!'), ('size', True), ('sha256', '0' * 64),
                                      ('source_id', 'changed')])
def test_corrupt_binary_never_decodes_as_valid_copy(field, value):
    document = encode(source(), DATA, sha256(DATA).hexdigest())
    document[field] = value
    with pytest.raises(Denied):
        decode(document, source())


def file_intent():
    from command_center.telegram_attachments import parse_message
    update = attachment(caption='')
    update['message']['document']['file_size'] = len(DATA)
    return parse_message(update['message'])


def metadata(**changes):
    item = file_intent()
    return {'ok': True, 'result': {k: item[k] for k in ('file_id', 'file_unique_id', 'file_size')}
            | {'file_path': 'documents/file_1.pdf'} | changes}


def test_exact_bound_file_uses_only_fixed_telegram_host():
    calls = []
    def handler(request):
        assert request.url.host == 'api.telegram.org'
        calls.append(request.method)
        return httpx.Response(200, json=metadata()) if request.method == 'POST' else httpx.Response(200, content=DATA)
    configured = client(handler)
    try:
        assert AttachmentFiles(configured, approved_connection='a' * 64).download(file_intent()) == (
            DATA, sha256(DATA).hexdigest())
        assert calls == ['POST', 'GET']
        with pytest.raises(Denied):
            AttachmentFiles(configured, approved_connection='b' * 64)
    finally:
        configured.close()


@pytest.mark.parametrize('change', [{'file_path': '../private'}, {'file_path': 'https://outside.test/file'},
    {'file_path': 'documents/file.pdf?redirect=x'}, {'file_unique_id': 'changed'}, {'file_size': 999},
    {'file_size': float(len(DATA))}])
def test_changed_reference_or_path_never_downloads(change):
    calls = []
    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json=metadata(**change))
    configured = client(handler)
    try:
        with pytest.raises(Denied):
            AttachmentFiles(configured, approved_connection='a' * 64).download(file_intent())
        assert calls == ['POST']
    finally:
        configured.close()


@pytest.mark.parametrize('failure', ['redirect', 'oversize', 'timeout'])
def test_download_failure_is_bounded_and_does_not_expose_token(failure, caplog):
    def handler(request):
        if request.method == 'POST':
            return httpx.Response(200, json=metadata())
        if failure == 'redirect':
            return httpx.Response(302, headers={'Location': 'https://outside.test/'})
        if failure == 'oversize':
            return httpx.Response(200, content=DATA + b'overflow')
        raise httpx.ReadTimeout(TOKEN, request=request)
    configured = client(handler)
    try:
        with pytest.raises((Denied, TelegramHTTPError)) as error:
            AttachmentFiles(configured, approved_connection='a' * 64).download(file_intent())
        assert TOKEN not in str(error.value) + caplog.text
    finally:
        configured.close()


@pytest.fixture
def copies(store, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    transport = MockTelegramHTTP(httpx.MockTransport(BotHTTP()))
    bridge = TelegramBridge(store, transport, OWNER)
    class Files:
        calls = 0
        after = None
        def download(self, intent):
            self.calls += 1
            if self.after:
                self.after()
            return DATA, sha256(DATA).hexdigest()
    files = Files()
    runner = VoiceWorker(bridge, Download(), Decoder(), since=datetime.now(timezone.utc) - timedelta(minutes=1),
                         model_fingerprint='a' * 64, attachment_copier=AttachmentCopier(files))
    update = attachment(caption='Напомни завтра в 11 проверить файл')
    update['message']['document']['file_size'] = len(DATA)
    saved = bridge.receive(update)
    yield bridge, runner, files, saved['inbox_id']
    transport.close()


def test_copy_survives_restart_and_telegram_unavailable_without_duplicate_or_authority(copies, store):
    bridge, runner, files, iid = copies
    before = authority(store)
    assert runner.process_one()['state'] == 'ATTACHMENT_COPIED'
    assert runner.process_one()['state'] == 'IDLE' and files.calls == 1
    with store.transaction() as session:
        original = session.get(TelegramInbox, iid)
        assert read_copy(store, session, original, profile=bridge.profile) == DATA
        assert len(list(session.scalars(select(Audit).where(Audit.event['kind'].as_string() == STORED)))) == 1
        with pytest.raises(Denied, match='owner_scope'):
            read_copy(store, session, original, profile='0' * 64)
    reopened = TelegramBridge(store, bridge.client, OWNER)
    assert 'Независимая копия сохранена' in response(reopened, message(2, '/request 1'))
    assert 'inert' not in response(reopened, message(3, '/requests'))
    assert authority(store) == before
    fresh = Store(store.settings)
    try:
        with fresh.transaction() as session:
            assert read_copy(fresh, session, session.get(TelegramInbox, iid), profile=bridge.profile) == DATA
    finally:
        fresh.engine.dispose()
    # Retrieval has no Telegram capability; actual bytes remain in the DB.
    with store.transaction() as session:
        original = session.get(TelegramInbox, iid)
        profile, vault_id = identity(original)
        row = session.get(TelegramInbox, vault_id)
        assert profile != bridge.profile and row.task_id is None
        changed = deepcopy(row.intent)
        changed['data64'] = 'A' * len(changed['data64'])
        row.intent = changed
    with store.transaction() as session:
        with pytest.raises(Denied, match='integrity'):
            read_copy(store, session, session.get(TelegramInbox, iid), profile=bridge.profile)


def test_stop_and_epoch_change_during_download_cannot_store_or_announce_copy(copies, store):
    _, runner, files, _ = copies
    with store.transaction() as session:
        session.get(Control, 1).halted = True
    with pytest.raises(Denied, match='control_blocked'):
        runner.process_one()
    assert files.calls == 0
    with store.transaction() as session:
        session.get(Control, 1).halted = False
    def stop():
        with store.transaction() as session:
            session.get(Control, 1).epoch += 1
    files.after = stop
    with pytest.raises(Denied, match='control_blocked'):
        runner.process_one()
    with store.transaction() as session:
        assert not list(session.scalars(select(Audit).where(Audit.event['kind'].as_string().in_((STORED, FAILED)))))


def test_quota_failure_keeps_source_and_does_not_download_or_retry(copies, store, monkeypatch):
    bridge, runner, files, iid = copies
    monkeypatch.setattr('command_center.attachment_copies.MAX_TOTAL', 1)
    assert runner.process_one()['state'] == 'ATTACHMENT_FAILED'
    assert runner.process_one()['state'] == 'IDLE' and files.calls == 0
    assert 'не сохранена' in response(bridge, message(2, '/request 1'))
    with store.transaction() as session:
        assert session.get(TelegramInbox, iid).state == 'NEEDS_PLANNING'


def test_pending_voice_has_priority_over_attachment_download(copies, store):
    from test_telegram_voice_requests import voice
    bridge, runner, files, _ = copies
    bridge.receive(voice(uid=2))
    assert runner.process_one()['state'] == 'PROPOSED'
    assert files.calls == 0
    assert runner.process_one()['state'] == 'ATTACHMENT_COPIED'


def test_uncertain_commit_reconciles_existing_copy_without_false_failure(copies, store, monkeypatch):
    _, runner, files, _ = copies
    original = store.transaction
    lost = False
    @contextmanager
    def transaction():
        nonlocal lost
        trigger = False
        with original() as session:
            yield session
            if not lost and session.scalar(select(Audit.sequence).where(
                    Audit.event['kind'].as_string() == STORED).limit(1)):
                trigger = True
        if trigger:
            lost = True
            raise RuntimeError('synthetic lost COMMIT response')
    monkeypatch.setattr(store, 'transaction', transaction)
    assert runner.process_one()['state'] == 'ATTACHMENT_COPIED' and lost
    assert runner.process_one()['state'] == 'IDLE' and files.calls == 1
    with original() as session:
        assert not list(session.scalars(select(Audit).where(Audit.event['kind'].as_string() == FAILED)))
        assert len(list(session.scalars(select(Audit).where(Audit.event['kind'].as_string() == STORED)))) == 1


def test_old_revision_is_not_silently_backfilled(copies, store):
    _, runner, files, _ = copies
    original = store.settings
    try:
        store.settings = replace(original, source_revision='f' * 40 if original.source_revision != 'f' * 40 else 'e' * 40)
        assert runner.process_one()['state'] == 'IDLE' and files.calls == 0
    finally:
        store.settings = original


def test_existing_worker_lock_prevents_second_downloader(copies, store):
    from sqlalchemy import text
    _, runner, files, _ = copies
    with store.engine.connect() as connection:
        connection.execute(text('SELECT pg_advisory_lock(:key)'), {'key': runner.key})
        connection.commit()
        try:
            assert runner.process_one()['state'] == 'BUSY' and files.calls == 0
        finally:
            connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': runner.key})
            connection.commit()


def test_owner_web_inbox_reads_attachment_metadata_and_never_binary(copies, client, headers):
    _, runner, _, _ = copies
    assert runner.process_one()['state'] == 'ATTACHMENT_COPIED'
    result = client.get('/api/telegram/requests', headers=headers['owner'])
    assert result.status_code == 200
    rows = result.json()['requests']
    assert len(rows) == 1 and 'notes.pdf' in rows[0]['text']
    assert 'data64' not in result.text and 'aW5lcnQ' not in result.text
    assert client.get('/api/telegram/requests', headers=headers['agent']).status_code == 409
