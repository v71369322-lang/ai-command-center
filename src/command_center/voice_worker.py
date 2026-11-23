"""Separate offline voice worker; never run inference in the Telegram poller."""

from datetime import datetime
from hashlib import sha256

from sqlalchemy import select, text

from .models import Audit, Control, TelegramInbox
from .store import Denied, digest
from .telegram_voice_requests import INTAKE, transcription_contract, verify_transcript
from .telegram_voice_transcripts import PROPOSED, propose

FAILED = 'telegram_voice_transcription_failed'
STARTED = 'telegram_voice_transcription_started'


class VoiceWorker:
    def __init__(self, bridge, downloader, decoder, *, since, model_fingerprint, runtime_guard=None):
        if (not isinstance(since, datetime) or since.tzinfo is None or since.utcoffset() is None
                or not callable(getattr(downloader, 'download', None))
                or not callable(getattr(decoder, 'transcribe', None))
                or getattr(decoder, 'model_fingerprint', None) != model_fingerprint
                or not isinstance(model_fingerprint, str) or len(model_fingerprint) != 64
                or any(c not in '0123456789abcdef' for c in model_fingerprint)):
            raise Denied('voice_worker_binding_invalid')
        if runtime_guard is not None and not callable(runtime_guard):
            raise Denied('voice_worker_binding_invalid')
        self.runtime_guard = runtime_guard
        self.bridge, self.downloader, self.decoder = bridge, downloader, decoder
        self.since, self.model_fingerprint = since, model_fingerprint
        self.key = int(digest({'voice_worker': bridge.profile})[:15], 16)
        self.leader = None

    def _guard(self, session, epoch=None):
        if self.runtime_guard:
            self.runtime_guard()
        if self.leader is None:
            raise Denied('voice_worker_leadership_required')
        held = self.leader.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE "
            "locktype='advisory' AND pid=pg_backend_pid() AND granted "
            "AND classid=:high AND objid=:low AND objsubid=1)"),
            {'high': self.key >> 32, 'low': self.key & 0xffffffff})
        self.leader.commit()
        if not held:
            raise Denied('voice_worker_leadership_lost')
        self.bridge.guard()
        self.bridge.store.check_audit(session)
        control = session.get(Control, 1)
        if (control is None or control.halted or control.recovery
                or (epoch is not None and control.epoch != epoch)):
            raise Denied('control_blocked')
        return control.epoch

    def _next(self, session):
        # Indexed inbox selection; no full Store.snapshot()/ORM audit materialization.
        rows = session.scalars(select(TelegramInbox).where(
            TelegramInbox.profile == self.bridge.profile, TelegramInbox.state == 'DONE',
            TelegramInbox.created_at >= self.since,
            TelegramInbox.intent['kind'].as_string() == 'voice_request'
        ).order_by(TelegramInbox.created_at, TelegramInbox.id).limit(1001)).all()
        if len(rows) > 1000:
            raise Denied('voice_worker_queue_limit')
        for row in rows:
            completed = session.scalar(select(Audit.sequence).where(
                Audit.event['kind'].as_string().in_((PROPOSED, FAILED)),
                Audit.event['profile'].as_string() == self.bridge.profile,
                Audit.event['voice_inbox_id'].as_string() == row.id).limit(1))
            intake = session.scalar(select(Audit.sequence).where(
                Audit.event['kind'].as_string() == INTAKE,
                Audit.event['profile'].as_string() == self.bridge.profile,
                Audit.event['inbox_id'].as_string() == row.id).limit(1))
            if completed is None and intake is not None:
                return row.id, row.fingerprint, dict(row.intent)
        return None

    def process_one(self):
        store = self.bridge.store
        with store.engine.connect() as leader:
            held = leader.scalar(text('SELECT pg_try_advisory_lock(:key)'), {'key': self.key})
            leader.commit()
            if not held:
                return {'state': 'BUSY'}
            self.leader = leader
            try:
                return self._process()
            finally:
                self.leader = None
                try:
                    leader.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': self.key})
                    leader.commit()
                except Exception:
                    leader.invalidate()

    def _process(self):
        store = self.bridge.store
        with store.transaction() as session:
            epoch = self._guard(session)
            item = self._next(session)
            if item is None:
                return {'state': 'IDLE'}
            iid, fingerprint, intent = item
            store.audit(session, STARTED, 'transcriber', profile=self.bridge.profile,
                        voice_inbox_id=iid, voice_fingerprint=fingerprint,
                        model_fingerprint=self.model_fingerprint, epoch=epoch, paid_api=False)
        try:
            audio, audio_hash = self.downloader.download(intent)
            if not isinstance(audio, bytes) or sha256(audio).hexdigest() != audio_hash:
                raise Denied('voice_download_hash_invalid')
            with store.transaction() as session:
                self._guard(session, epoch)
            request = transcription_contract(intent, audio_hash)
            response = self.decoder.transcribe(audio)
            verify_transcript(response, request)
            with store.transaction() as session:
                self._guard(session, epoch)
                source = session.get(TelegramInbox, iid)
                if (source is None or source.fingerprint != fingerprint or source.state != 'DONE'
                        or source.intent != intent):
                    raise Denied('voice_worker_source_changed')
            result = propose(self.bridge, iid, response, request, expected_epoch=epoch)
            return {'state': 'PROPOSED', **result}
        except Exception:
            # Raw decoder/provider errors and transcript text must not enter failure logs.
            with store.transaction() as session:
                self._guard(session, epoch)
                store.audit(session, FAILED, 'transcriber', profile=self.bridge.profile,
                            voice_inbox_id=iid, model_fingerprint=self.model_fingerprint,
                            code='offline_transcription_failed', paid_api=False)
                self.bridge.enqueue(session, 'voice-failed:' + iid,
                    'Не удалось разобрать голосовое поручение. Пришлите более короткую запись '
                    'или напишите текстом. Поручение не потеряно; задача не создавалась.')
            return {'state': 'FAILED', 'code': 'offline_transcription_failed'}


def main():
    """Protected, exact opt-in; no model/token discovery or implicit activation."""
    import argparse
    import json
    import signal
    import threading

    from pydantic import BaseModel, ConfigDict, Field

    from .offline_speech import OfflineSpeech
    from .store import Store
    from .telegram_bridge import TelegramBridge
    from .telegram_service import service_settings
    from .telegram_transport import ConfiguredTelegramHTTP, connection, private_read
    from .telegram_voice_files import TelegramVoiceFiles

    class Profile(BaseModel):
        model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
        enabled: bool = False
        connection_file: str
        connection_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
        source_revision: str = Field(pattern=r'^[a-f0-9]{40}$')
        model_directory: str
        model_manifest: dict[str, str]
        since: str

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['inspect', 'run'])
    parser.add_argument('--config', required=True)
    parser.add_argument('--approved-profile')
    args = parser.parse_args()
    client, store = None, None
    try:
        profile = Profile.model_validate_json(private_read(args.config, 8192))
        fingerprint = digest(profile.model_dump())
        if args.action == 'inspect':
            print(json.dumps({'enabled': profile.enabled, 'profile_digest': fingerprint,
                              'source_revision': profile.source_revision, 'paid_api': False,
                              'network_contacted': False, 'model_loaded': False}))
            return
        if not profile.enabled or args.approved_profile != fingerprint:
            raise Denied('voice_exact_profile_approval_required')
        settings = service_settings()
        if settings.source_revision != profile.source_revision:
            raise Denied('voice_source_revision_mismatch')
        bound = connection(profile.connection_file)
        if bound.source_revision != profile.source_revision or digest(bound.model_dump()) != profile.connection_digest:
            raise Denied('voice_connection_mismatch')
        since = datetime.fromisoformat(profile.since)
        if since.tzinfo is None or since.utcoffset() is None:
            raise Denied('voice_since_timezone_required')
        # Load offline model before opening a credential-bearing HTTP client.
        decoder = OfflineSpeech(profile.model_directory, profile.model_manifest)
        client = ConfiguredTelegramHTTP(profile.connection_file, profile.connection_digest, profile.source_revision)
        store = Store(settings)
        bridge = TelegramBridge(store, client, client.owner)
        files = TelegramVoiceFiles(client, approved_connection=profile.connection_digest)
        stop = threading.Event()

        def guard():
            current = Profile.model_validate_json(private_read(args.config, 8192))
            if current != profile or stop.is_set():
                raise Denied('voice_profile_revoked_or_changed')

        worker = VoiceWorker(bridge, files, decoder, since=since,
                             model_fingerprint=decoder.model_fingerprint, runtime_guard=guard)
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, lambda *_: stop.set())
        if not hasattr(signal, 'SIGALRM'):
            raise Denied('voice_worker_posix_deadline_required')

        def timeout(*_):
            raise Denied('voice_worker_time_limit')

        signal.signal(signal.SIGALRM, timeout)
        while not stop.is_set():
            # Re-read the protected profile before each voice note (revocation).
            guard()
            signal.alarm(90)
            try:
                worker.process_one()
            finally:
                signal.alarm(0)
            stop.wait(1)
    except Exception:
        parser.exit(1, 'offline_voice_worker_failed_closed; inspect protected configuration and audit\n')
    finally:
        if client:
            client.close()
        if store:
            store.engine.dispose()


if __name__ == '__main__':
    main()
