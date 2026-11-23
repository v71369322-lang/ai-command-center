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
