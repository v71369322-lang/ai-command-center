"""Explicit owner retrieval through the existing durable Telegram delivery queue."""
import re

from sqlalchemy import select, func

from .attachment_copies import read_copy, copied_event
from .models import Control, TelegramDelivery, TelegramInbox
from .store import Denied, digest


def number(value):
    if not isinstance(value, str) or not re.fullmatch(r'0|[1-9][0-9]{0,15}', value) or int(value) >= 2**53:
        raise Denied('attachment_retrieval_number_invalid')
    return value


def keyboard(value):
    return {'inline_keyboard': [[{'text': 'Получить файл', 'callback_data': 'af:' + number(value)}]]}


def allowed_markup(value):
    try:
        token = value['inline_keyboard'][0][0]['callback_data']
        return token.startswith('af:') and value == keyboard(token[3:])
    except (KeyError, IndexError, TypeError, AttributeError, Denied):
        return False


def offer(bridge, session, key, value):
    source = session.get(TelegramInbox, bridge.profile + ':' + number(value))
    if source is not None and source.intent.get('kind') == 'attachment' and copied_event(session, source):
        bridge.enqueue(session, key + ':file-button', 'Получить сохранённую копию вложения №' + value + '.', keyboard(value))


def queue(bridge, session, iid, value):
    control = session.get(Control, 1)
    if control.halted or control.recovery:
        bridge.finish(session, iid, 'Выдача файла на паузе. Возобновить: /resume.')
        return
    source = session.get(TelegramInbox, bridge.profile + ':' + number(value))
    try:
        data = read_copy(bridge.store, session, source, profile=bridge.profile)
    except Denied:
        bridge.finish(session, iid, 'Сохранённая копия недоступна или требует проверки. Оригинал остаётся в Telegram.')
        return
    oid = digest({'profile': bridge.profile, 'event': iid + ':file'})
    if not session.get(TelegramDelivery, oid):
        if session.scalar(select(func.count()).select_from(TelegramDelivery)) >= 1000:
            raise Denied('telegram_delivery_capacity')
        # Never persist another copy of the bytes in the outbox or audit.
        from hashlib import sha256
        body = {'chat_id': bridge.owner, 'attachment': {'source_id': source.id,
            'sha256': sha256(data).hexdigest(), 'epoch': control.epoch,
            'revision': bridge.store.settings.source_revision}}
        session.add(TelegramDelivery(id=oid, profile=bridge.profile, body=body, state='NEW'))
        session.flush()
        bridge.store.audit(session, 'telegram_delivery_queued', 'system', delivery_id=oid, request_hash=digest(body))
    bridge.finish(session, iid, 'Сохранённая копия №' + value + ' подготовлена к отправке.')


def payload(bridge, session, body):
    """Called only after the existing queued-body audit anchor was checked."""
    ref = body.get('attachment')
    control = session.get(Control, 1)
    if (set(body) != {'chat_id', 'attachment'} or not isinstance(ref, dict)
            or set(ref) != {'source_id', 'sha256', 'epoch', 'revision'}
            or type(ref['epoch']) is not int or control.halted or control.recovery
            or ref['epoch'] != control.epoch or ref['revision'] != bridge.store.settings.source_revision
            or not isinstance(ref['source_id'], str)):
        raise Denied('attachment_retrieval_stopped_or_changed')
    source = session.get(TelegramInbox, ref['source_id'])
    data = read_copy(bridge.store, session, source, profile=bridge.profile)
    from hashlib import sha256
    if sha256(data).hexdigest() != ref['sha256']:
        raise Denied('attachment_retrieval_integrity')
    suffix = '.jpg' if source.intent['media'] == 'photo' else '.bin'
    if source.intent['media'] == 'document':
        extension = source.intent['filename'].rsplit('.', 1)[-1].lower()
        if extension in {'pdf', 'txt', 'docx', 'xlsx', 'csv', 'png', 'jpg', 'jpeg', 'webp', 'zip', 'pptx', 'json'}:
            suffix = '.' + extension
    # Fixed safe name: original untrusted names are displayed in the source card.
    return data, 'attachment-' + number(source.id.rsplit(':', 1)[1]) + suffix
