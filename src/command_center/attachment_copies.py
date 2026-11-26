"""Bounded binary Inbox records, isolated from commands and covered by PG backups.

Base64 is an encoding, NOT encryption. Same DB custody as other personal data;
existing AES-GCM database backups include these records without a new host key.
"""
import base64
from hashlib import sha256
import time

from sqlalchemy import func, select

from .models import Audit, TelegramInbox
from .store import Denied, digest
from .telegram_attachments import MAX_BYTES
from .telegram_requests import captured_text

STORED = 'telegram_attachment_copy_stored'
FAILED = 'telegram_attachment_copy_failed'
MAX_TOTAL = 16 * 1024 * 1024
MAX_FILES = 32
FIELDS = {'kind', 'source_id', 'source_fingerprint', 'size', 'sha256', 'data64'}


def identity(source):
    # A separate DATA namespace, never an independent authorization namespace.
    profile = digest({'attachment_data_for': source.profile})
    return profile, profile + ':' + source.id.rsplit(':', 1)[1]


def encode(source, data, checksum):
    if (not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES
            or len(data) != source.intent['file_size'] or sha256(data).hexdigest() != checksum):
        raise Denied('attachment_copy_bytes_invalid')
    return {'kind': 'attachment_copy', 'source_id': source.id, 'source_fingerprint': source.fingerprint,
            'size': len(data), 'sha256': checksum, 'data64': base64.b64encode(data).decode('ascii')}


def decode(document, source):
    if (not isinstance(document, dict) or set(document) != FIELDS or document['kind'] != 'attachment_copy'
            or document['source_id'] != source.id or document['source_fingerprint'] != source.fingerprint
            or type(document['size']) is not int or not 0 < document['size'] <= MAX_BYTES
            or document['size'] != source.intent['file_size'] or not isinstance(document['data64'], str)
            or len(document['data64']) != 4 * ((document['size'] + 2) // 3)):
        raise Denied('attachment_copy_integrity')
    try:
        data = base64.b64decode(document['data64'], validate=True)
    except (ValueError, TypeError):
        raise Denied('attachment_copy_integrity') from None
    if len(data) != document['size'] or sha256(data).hexdigest() != document['sha256']:
        raise Denied('attachment_copy_integrity')
    return data


def copied_event(session, source):
    return session.scalar(select(Audit).where(Audit.event['kind'].as_string() == STORED,
        Audit.event['profile'].as_string() == source.profile,
        Audit.event['request_id'].as_string() == source.id).limit(1))


def read_copy(store, session, source, *, profile):
    if source.profile != profile or source.intent.get('kind') != 'attachment':
        raise Denied('attachment_copy_owner_scope')
    store.check_audit(session)
    captured_text(session, source, states=frozenset({'NEEDS_PLANNING', 'ARCHIVED'}))
    event = copied_event(session, source)
    namespace, iid = identity(source)
    row = session.get(TelegramInbox, iid)
    if (event is None or row is None or event.event.get('actor') != 'attachment_worker'
            or row.profile != namespace or row.state != 'STORED_ATTACHMENT' or row.task_id is not None
            or event.event.get('copy_id') != iid or event.event.get('source_fingerprint') != source.fingerprint
            or row.fingerprint != event.event.get('copy_fingerprint') or digest(row.intent) != row.fingerprint):
        raise Denied('attachment_copy_integrity')
    return decode(row.intent, source)


def status(session, source):
    event = copied_event(session, source)
    if event:
        namespace, iid = identity(source)
        found = session.execute(select(TelegramInbox.profile, TelegramInbox.state, TelegramInbox.fingerprint)
            .where(TelegramInbox.id == iid)).first()
        if (not found or found.profile != namespace or found.state != 'STORED_ATTACHMENT'
                or event.event.get('actor') != 'attachment_worker'
                or event.event.get('source_fingerprint') != source.fingerprint
                or event.event.get('copy_id') != iid or event.event.get('copy_fingerprint') != found.fingerprint):
            return 'Независимая копия требует проверки. Сохраните оригинал в Telegram.'
        return 'Независимая копия сохранена; будет включена в штатную резервную копию базы.'
    failed = session.scalar(select(Audit.sequence).where(Audit.event['kind'].as_string() == FAILED,
        Audit.event['profile'].as_string() == source.profile,
        Audit.event['request_id'].as_string() == source.id).limit(1))
    return ('Независимая копия не сохранена. Сохраните оригинал в Telegram.' if failed else
            'Независимая копия ещё не подтверждена. Сохраните оригинал в Telegram.')


class AttachmentCopier:
    def __init__(self, downloader):
        self.downloader = downloader
        self.next_scan = 0.0

    @staticmethod
    def quota(session, source, size):
        namespace, _ = identity(source)
        rows = list(session.execute(select(TelegramInbox.intent['size'].as_integer()).where(
            TelegramInbox.profile == namespace, TelegramInbox.state == 'STORED_ATTACHMENT')).scalars())
        if (len(rows) >= MAX_FILES or any(type(n) is not int or not 0 < n <= MAX_BYTES for n in rows)
                or sum(rows) + size > MAX_TOTAL
                or session.scalar(select(func.count()).select_from(TelegramInbox)) >= 1000):
            raise Denied('attachment_copy_quota')

    def process_one(self, worker):
        if time.monotonic() < self.next_scan:
            return {'state': 'IDLE'}
        bridge, store = worker.bridge, worker.bridge.store
        with store.transaction() as session:
            epoch = worker._guard(session, audit=False)
            completed = select(Audit.sequence).where(Audit.event['kind'].as_string().in_((STORED, FAILED)),
                Audit.event['profile'].as_string() == bridge.profile,
                Audit.event['request_id'].as_string() == TelegramInbox.id).exists()
            current_source = select(Audit.sequence).where(
                Audit.event['kind'].as_string() == 'telegram_update_received',
                Audit.event['profile'].as_string() == bridge.profile,
                Audit.event['revision'].as_string() == store.settings.source_revision,
                Audit.event['intent_hash'].as_string() == TelegramInbox.fingerprint,
                Audit.event['update_id'].as_string() == func.split_part(TelegramInbox.id, ':', 2)).exists()
            source = session.scalar(select(TelegramInbox).where(TelegramInbox.profile == bridge.profile,
                TelegramInbox.state == 'NEEDS_PLANNING', TelegramInbox.created_at >= worker.since,
                TelegramInbox.intent['kind'].as_string() == 'attachment', ~completed, current_source)
                .order_by(TelegramInbox.created_at, TelegramInbox.id).limit(1))
            if source is None:
                self.next_scan = time.monotonic() + 5
                return {'state': 'IDLE'}
            store.check_audit(session)
            captured_text(session, source)
            iid, fingerprint, intent = source.id, source.fingerprint, dict(source.intent)
        try:
            with store.transaction() as session:
                worker._guard(session, epoch)
                self.quota(session, source, intent['file_size'])
            data, checksum = self.downloader.download(intent)
            document = encode(source, data, checksum)
            copy_fingerprint = digest(document)
            with store.transaction() as session:
                worker._guard(session, epoch)
                current = session.get(TelegramInbox, iid)
                if (current is None or current.state != 'NEEDS_PLANNING' or current.fingerprint != fingerprint
                        or current.intent != intent):
                    raise Denied('attachment_copy_source_changed')
                captured_text(session, current)
                namespace, copy_id = identity(current)
                if copied_event(session, current) or session.get(TelegramInbox, copy_id):
                    raise Denied('attachment_copy_already_stored')
                self.quota(session, current, len(data))
                session.add(TelegramInbox(id=copy_id, profile=namespace, intent=document,
                    fingerprint=copy_fingerprint, state='STORED_ATTACHMENT', created_at=store.now(session)))
                store.audit(session, STORED, 'attachment_worker', profile=bridge.profile, request_id=iid,
                    source_fingerprint=fingerprint, copy_id=copy_id, copy_fingerprint=copy_fingerprint,
                    size=len(data), sha256=checksum)
                bridge.enqueue(session, iid + ':copy', f'Независимая копия вложения №{iid.rsplit(":", 1)[1]} сохранена. '
                    'Содержимое не читалось.')
            return {'state': 'ATTACHMENT_COPIED'}
        except Exception as error:
            from .voice_worker import admission_busy
            if admission_busy(error, store):
                raise
            with store.transaction() as session:
                worker._guard(session, epoch)
                current = session.get(TelegramInbox, iid)
                if current is not None and copied_event(session, current):
                    # A lost COMMIT response is not proof that the copy failed.
                    read_copy(store, session, current, profile=bridge.profile)
                    return {'state': 'ATTACHMENT_COPIED'}
                reason = 'quota' if isinstance(error, Denied) and str(error) == 'attachment_copy_quota' else 'unavailable'
                store.audit(session, FAILED, 'attachment_worker', profile=bridge.profile, request_id=iid,
                    source_fingerprint=fingerprint, reason=reason)
                bridge.enqueue(session, iid + ':copy', f'Независимая копия вложения №{iid.rsplit(":", 1)[1]} '
                    'не сохранена. Сохраните оригинал в Telegram. '
                    + ('Достигнут лимит хранилища.' if reason == 'quota' else 'Загрузка или проверка файла не удалась.'))
            return {'state': 'ATTACHMENT_FAILED'}
