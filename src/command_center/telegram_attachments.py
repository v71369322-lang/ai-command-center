"""Owner attachment references; no downloads, content parsing or caption commands."""
import re

from .store import Denied

MAX_BYTES = 10 * 1024 * 1024
FIELDS = {'kind', 'media', 'file_id', 'file_unique_id', 'file_size', 'filename', 'caption', 'message_id'}


def validate(intent, sensitive=lambda _: False):
    if (not isinstance(intent, dict) or set(intent) != FIELDS or intent['kind'] != 'attachment'
            or intent['media'] not in ('photo', 'document')
            or type(intent['file_size']) is not int or not 0 < intent['file_size'] <= MAX_BYTES
            or type(intent['message_id']) is not int or intent['message_id'] <= 0):
        raise Denied('telegram_attachment_invalid')
    for field in ('file_id', 'file_unique_id'):
        if not isinstance(intent[field], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', intent[field]):
            raise Denied('telegram_attachment_invalid')
    for field, limit in [('filename', 240), ('caption', 1200)]:
        value = intent[field]
        if (not isinstance(value, str) or len(value.encode()) > limit or sensitive(value)
                or any(ord(c) < 32 and c not in '\n\t' for c in value)):
            raise Denied('telegram_attachment_invalid')
    if any(sensitive(intent[k]) for k in ('file_id', 'file_unique_id')):
        raise Denied('telegram_attachment_invalid')
    return intent


def parse_message(message, sensitive=lambda _: False):
    if 'photo' in message and 'document' in message:
        raise Denied('telegram_attachment_invalid')
    media = 'photo' if 'photo' in message else 'document'
    item = message.get(media)
    if media == 'photo':
        if not isinstance(item, list) or not 1 <= len(item) <= 10 or not all(isinstance(x, dict) for x in item):
            raise Denied('telegram_attachment_invalid')
        if any(type(x.get('file_size')) is not int for x in item):
            raise Denied('telegram_attachment_invalid')
        item = max(item, key=lambda x: x['file_size'])
    if not isinstance(item, dict):
        raise Denied('telegram_attachment_invalid')
    return validate({'kind': 'attachment', 'media': media, 'file_id': item.get('file_id'),
        'file_unique_id': item.get('file_unique_id'), 'file_size': item.get('file_size'),
        'filename': item.get('file_name', '') if media == 'document' else '',
        'caption': message.get('caption', ''), 'message_id': message.get('message_id')}, sensitive)


def summary(intent):
    validate(intent)
    label = 'Фотография' if intent['media'] == 'photo' else 'Документ'
    name = f": {intent['filename']}" if intent['filename'] else ''
    caption = f"\nПодпись: {intent['caption']}" if intent['caption'] else ''
    return f'{label}{name}{caption}'


def capture(bridge, session, iid, intent):
    from .models import TelegramInbox
    from .telegram_project_picker import keyboard, issue
    value = summary(intent)
    bridge.check_text(value)
    row = session.get(TelegramInbox, iid)
    if row.state == 'NEEDS_PLANNING':
        return
    if row.state != 'RECEIVED':
        raise Denied('telegram_attachment_not_pending')
    bridge.guard()
    row.state = 'NEEDS_PLANNING'
    number = iid.rsplit(':', 1)[1]
    receipt = (f'Вложение сохранено во входящих: №{number}.\n{value}\n'
               'Сохранены подпись и ссылка на файл в Telegram. Файл не скачивался, '
               'содержимое не прочитано. Сохраните оригинал в чате.\n'
               f'Посмотреть: /request {number}')
    delivery = bridge.enqueue(session, iid + ':reply', receipt, keyboard(number, 0))
    issue(bridge, session, delivery, number, 0)
