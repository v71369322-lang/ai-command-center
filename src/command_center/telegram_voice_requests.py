"""Bounded owner voice-request intake; no download or transcription here."""

import re

from sqlalchemy import func, select

from .models import Audit, TelegramInbox
from .store import Denied, digest

INTAKE = 'telegram_voice_request_received'
MAX_SECONDS = 120
MAX_BYTES = 5 * 1024 * 1024


def parse_message(message, sensitive=lambda _: False):
    voice = message.get('voice') if isinstance(message, dict) else None
    caption = message.get('caption')
    if caption not in {None, '', '/task'} or not isinstance(voice, dict):
        raise Denied('telegram_voice_request_caption_invalid')
    file_id, unique = voice.get('file_id'), voice.get('file_unique_id')
    duration, size, mime = voice.get('duration'), voice.get('file_size'), voice.get('mime_type')
    if (not isinstance(file_id, str) or not 1 <= len(file_id) <= 256 or sensitive(file_id)
            or not isinstance(unique, str) or not re.fullmatch(r'[A-Za-z0-9_-]{6,128}', unique)
            or type(duration) is not int or not 1 <= duration <= MAX_SECONDS
            or type(size) is not int or not 1 <= size <= MAX_BYTES
            or mime not in {'audio/ogg', 'audio/mpeg', 'audio/mp4'}):
        raise Denied('telegram_voice_request_invalid')
    return {'kind': 'voice_request', 'file_id': file_id, 'file_unique_hash': digest(unique),
            'file_ref_hash': digest(file_id), 'duration_seconds': duration,
            'file_size': size, 'mime_type': mime}


def capture(bridge, session, iid, intent):
    row = session.get(TelegramInbox, iid)
    if row.state == 'DONE':
        return
    if row.state != 'RECEIVED' or row.intent != intent:
        raise Denied('telegram_voice_request_not_pending')
    existing = session.execute(select(Audit).where(
        Audit.event['kind'].as_string() == INTAKE,
        Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['inbox_id'].as_string() == iid)).first()
    if not existing:
        bridge.store.audit(session, INTAKE, 'owner', profile=bridge.profile, inbox_id=iid,
                           file_unique_hash=intent['file_unique_hash'], file_ref_hash=intent['file_ref_hash'],
                           duration_seconds=intent['duration_seconds'], file_size=intent['file_size'],
                           mime_type=intent['mime_type'], file_downloaded=False,
                           transcription_requested=False, project_selected=False, task_created=False)
    bridge.finish(session, iid, 'Голосовое поручение сохранено. Сейчас оно ожидает безопасной расшифровки; '
                  'файл не скачивался, AI и исполнитель не запускались. Состояние: /voice.')


def pending_count(session, profile):
    value = session.scalar(select(func.count()).select_from(Audit).where(
        Audit.event['kind'].as_string() == INTAKE,
        Audit.event['profile'].as_string() == profile,
        Audit.event['transcription_requested'].as_boolean().is_(False)))
    if type(value) is not int or not 0 <= value <= 1000:
        raise Denied('telegram_voice_request_history_invalid')
    return value


def reply(session, profile):
    count = pending_count(session, profile)
    return (f'Голосовые поручения, ожидающие расшифровки: {count}.\n'
            'Они ещё не являются текстовыми запросами, не назначены проектам и не запускали AI или исполнителя.\n'
            'После подключения доверенной расшифровки текст сначала будет показан вам и только затем сохранён как запрос.')


def transcription_contract(intent, audio_sha256):
    if (not isinstance(intent, dict) or intent.get('kind') != 'voice_request'
            or not re.fullmatch(r'[a-f0-9]{64}', audio_sha256 or '')):
        raise Denied('voice_transcription_request_invalid')
    return {'audio_sha256': audio_sha256, 'language': 'ru', 'max_seconds': MAX_SECONDS,
            'max_text_bytes': 2000, 'create_task': False, 'select_project': False,
            'requires_owner_readback': True}


def verify_transcript(response, request):
    if (not isinstance(response, dict)
            or set(response) != {'audio_sha256', 'language', 'text', 'duration_seconds'}
            or response.get('audio_sha256') != request.get('audio_sha256')
            or response.get('language') != 'ru' or not isinstance(response.get('text'), str)
            or not 1 <= len(response['text'].encode()) <= request.get('max_text_bytes', 0)
            or response['text'] != response['text'].strip()
            or type(response.get('duration_seconds')) not in {int, float}
            or not 0 < response['duration_seconds'] <= request.get('max_seconds', 0)):
        raise Denied('voice_transcription_response_invalid')
    return {'text': response['text'], 'audio_sha256': response['audio_sha256'],
            'confirmed': False, 'task_created': False, 'project_selected': False}
