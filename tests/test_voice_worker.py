from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from command_center.models import Control, TelegramInbox
from command_center.store import Denied
from command_center.voice_worker import VoiceWorker
from command_center.telegram_voice_requests import pending_count
from test_telegram_voice_requests import voice
from test_telegram_voice_requests import transcript_callback
from command_center.project_inbox import inbox
from command_center.telegram_bridge import MockTelegramHTTP, TelegramBridge
from test_telegram_bridge import BotHTTP, OWNER
import httpx


@pytest.fixture
def bridge(store):
    client = MockTelegramHTTP(httpx.MockTransport(fake := BotHTTP()))
    yield TelegramBridge(store, client, OWNER), fake
    client.close()


class Download:
    def __init__(self):
        self.calls = 0

    def download(self, intent):
        self.calls += 1
        return b'audio', sha256(b'audio').hexdigest()


class Decoder:
    model_fingerprint = 'a' * 64

    def transcribe(self, audio):
        return {'audio_sha256': sha256(audio).hexdigest(), 'language': 'ru',
                'text': 'Завтра позвонить поставщику', 'duration_seconds': 2.5}


def worker(service, download, decoder=None, since=None):
    return VoiceWorker(service, download, decoder or Decoder(),
        since=since or datetime.now(timezone.utc) - timedelta(minutes=1), model_fingerprint='a' * 64)


def test_voice_to_readback_to_saved_request_without_task_or_paid_call(bridge, store):
    service, fake = bridge
    service.receive(voice())
    download = Download()
    runner = worker(service, download)
    result = runner.process_one()
    assert result['state'] == 'PROPOSED'
    assert runner.process_one()['state'] == 'IDLE' and download.calls == 1
    assert inbox(store, 'owner')['total_pending'] == 0
    with store.transaction() as session:
        assert pending_count(session, service.profile) == 0
    service.receive(transcript_callback(service, fake, result['proposal_id']))
    assert inbox(store, 'owner')['requests'][0]['text'] == 'Завтра позвонить поставщику'
    assert store.snapshot()['tasks'] == []


def test_stop_before_download_and_epoch_change_during_decode_block_readback(bridge, store):
    service, _ = bridge
    service.receive(voice())
    download = Download()
    with store.transaction() as session:
        session.get(Control, 1).halted = True
    with pytest.raises(Denied, match='control_blocked'):
        worker(service, download).process_one()
    assert download.calls == 0
    with store.transaction() as session:
        session.get(Control, 1).halted = False

    class StopDecoder(Decoder):
        def transcribe(self, audio):
            with store.transaction() as session:
                session.get(Control, 1).epoch += 1
            return super().transcribe(audio)

    with pytest.raises(Denied, match='control_blocked'):
        worker(service, download, StopDecoder()).process_one()
    assert inbox(store, 'owner')['total_pending'] == 0


def test_decoder_failure_is_redacted_and_not_retried_forever(bridge, store):
    service, _ = bridge
    service.receive(voice())
    download = Download()

    class BadDecoder(Decoder):
        def transcribe(self, audio):
            raise RuntimeError('private provider traceback')

    runner = worker(service, download, BadDecoder())
    assert runner.process_one()['state'] == 'FAILED'
    assert runner.process_one()['state'] == 'IDLE'
    assert download.calls == 1
    assert 'private provider traceback' not in str(store.snapshot())


def test_cutover_does_not_process_old_voice_messages(bridge):
    service, _ = bridge
    service.receive(voice())
    download = Download()
    runner = worker(service, download, since=datetime.now(timezone.utc) + timedelta(minutes=1))
    assert runner.process_one()['state'] == 'IDLE' and download.calls == 0


def test_profile_revocation_during_inference_blocks_readback(bridge):
    service, _ = bridge
    service.receive(voice())
    active = [True]

    class RevokeDecoder(Decoder):
        def transcribe(self, audio):
            active[0] = False
            return super().transcribe(audio)

    def guard():
        if not active[0]:
            raise Denied('voice_profile_revoked')

    runner = VoiceWorker(service, Download(), RevokeDecoder(),
        since=datetime.now(timezone.utc) - timedelta(minutes=1), model_fingerprint='a' * 64,
        runtime_guard=guard)
    with pytest.raises(Denied, match='profile_revoked'):
        runner.process_one()


def test_tampered_inbox_cannot_be_downloaded_even_with_recomputed_row_hash(bridge, store):
    from command_center.store import digest
    service, _ = bridge
    received = service.receive(voice())
    with store.transaction() as session:
        row = session.get(TelegramInbox, received['inbox_id'])
        row.intent = row.intent | {'file_size': 100}
        row.fingerprint = digest(row.intent)
    download = Download()
    with pytest.raises(Denied, match='intake_binding_changed'):
        worker(service, download).process_one()
    assert download.calls == 0


def test_idle_worker_does_not_rescan_entire_audit_history_each_second(bridge, store, monkeypatch):
    service, _ = bridge
    download = Download()
    monkeypatch.setattr(store, 'check_audit', lambda _: pytest.fail('no full audit scan for an empty read-only poll'))
    assert worker(service, download).process_one()['state'] == 'IDLE'
    assert download.calls == 0


def test_full_audit_is_still_required_before_any_download(bridge, store, monkeypatch):
    service, _ = bridge
    service.receive(voice())
    download = Download()

    def invalid(_):
        raise Denied('audit_integrity_failure')

    monkeypatch.setattr(store, 'check_audit', invalid)
    with pytest.raises(Denied, match='audit_integrity_failure'):
        worker(service, download).process_one()
    assert download.calls == 0


def test_real_admission_contention_retries_without_download_or_false_heartbeat(bridge, store):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from command_center.voice_worker import heartbeat, process_or_pause

    service, _ = bridge
    service.receive(voice())
    download = Download()
    runner = worker(service, download)
    locked, release = Event(), Event()

    def hold():
        with store.transaction():
            locked.set()
            assert release.wait(20)

    with ThreadPoolExecutor(max_workers=1) as pool:
        holder = pool.submit(hold)
        try:
            assert locked.wait(5)
            assert process_or_pause(runner) == {'state': 'BUSY'}
            assert not heartbeat(runner, lambda: pytest.fail('no lock acquired'), 'b' * 64, 'BUSY')
            assert download.calls == 0
        finally:
            release.set()
        holder.result(timeout=5)
    assert process_or_pause(runner)['state'] == 'PROPOSED'
    assert download.calls == 1
    assert heartbeat(runner, lambda: None, 'b' * 64, 'IDLE')


@pytest.mark.parametrize('sqlstate,query,params,expected', [
    ('57014', 'control', {'id_1': 1}, True),
    ('55P03', 'control', {'id_1': 1}, True),
    ('08006', 'control', {'id_1': 1}, False),
    ('57014', 'audit', {'id_1': 1}, False),
    ('57014', 'control', {'id_1': 2}, False),
    ('57014', None, None, False),
])
def test_only_exact_admission_timeout_is_retriable(store, sqlstate, query, params, expected):
    from types import SimpleNamespace
    from sqlalchemy import select
    from sqlalchemy.exc import OperationalError
    from command_center.voice_worker import admission_busy
    statement = str(select(Control).where(Control.id == 1).with_for_update().compile(
        dialect=store.engine.dialect)) if query == 'control' else query
    error = OperationalError(statement, params, SimpleNamespace(sqlstate=sqlstate))
    assert admission_busy(error, store) is expected


def test_audit_timeout_remains_fatal_for_processing_and_heartbeat(bridge, store, monkeypatch):
    from types import SimpleNamespace
    from sqlalchemy.exc import OperationalError
    from command_center.voice_worker import heartbeat, process_or_pause
    service, _ = bridge
    service.receive(voice())
    download = Download()
    runner = worker(service, download)

    def fail(_):
        raise OperationalError('SELECT audit', {}, SimpleNamespace(sqlstate='57014'))

    monkeypatch.setattr(store, 'check_audit', fail)
    with pytest.raises(OperationalError):
        process_or_pause(runner)
    with pytest.raises(OperationalError):
        heartbeat(runner, lambda: None, 'b' * 64, 'IDLE')
    assert download.calls == 0


def test_contention_after_download_does_not_permanently_fail_voice(bridge, store):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from sqlalchemy import select
    from sqlalchemy.exc import OperationalError
    from command_center.voice_worker import process_or_pause
    service, _ = bridge
    service.receive(voice())
    transaction = store.transaction

    @contextmanager
    def busy():
        statement = select(Control).where(Control.id == 1).with_for_update().compile(
            dialect=store.engine.dialect)
        raise OperationalError(str(statement), statement.params, SimpleNamespace(sqlstate='57014'))
        yield  # pragma: no cover

    class BusyDownload(Download):
        def download(self, intent):
            result = super().download(intent)
            store.transaction = busy
            return result

    download = BusyDownload()
    try:
        assert process_or_pause(worker(service, download)) == {'state': 'BUSY'}
    finally:
        store.transaction = transaction
    assert worker(service, Download()).process_one()['state'] == 'PROPOSED'
