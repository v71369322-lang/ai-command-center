"""Telegram calendar draft cards; no Google provider access lives here."""

import re
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from .attention_schedule import current as reminder_schedule
from .calendar_drafts import create, decide, list_drafts_locked
from .calendar_sync import sync_state
from .models import Audit, TelegramDelivery, TelegramInbox
from .store import Denied, canonical, digest

ISSUED = 'telegram_calendar_card_issued'
REMINDER = 'telegram_calendar_reminder_queued'
LABEL_ADD = 'Добавить в календарь'
LABEL_CANCEL = 'Отмена'


def parse_command(value):
    """Parse bounded Russian or deterministic input without guessing missing fields."""
    if value == '/calendar':
        return {'kind': 'calendar_list'}
    match = re.fullmatch(
        r'/calendar ([0-9]{4}-[0-9]{2}-[0-9]{2}) ([0-2][0-9]:[0-5][0-9]) '
        r'([1-9][0-9]{0,2}) ([1-9][0-9]{0,3}) (.{1,120})', value, re.DOTALL)
    if match:
        if match[2][:2] > '23':
            raise Denied('telegram_calendar_format_invalid')
        duration, reminder, title = int(match[3]), int(match[4]), match[5]
        if duration > 1440 or not 5 <= reminder <= 1440 or title != title.strip():
            raise Denied('telegram_calendar_format_invalid')
        return {'kind': 'calendar_create', 'date': match[1], 'clock': match[2],
                'duration_minutes': duration, 'reminder_minutes': reminder, 'title': title}
    natural = re.fullmatch(
        r'/calendar (сегодня|завтра|[0-9]{4}-[0-9]{2}-[0-9]{2}) в '
        r'([0-2][0-9]:[0-5][0-9]) на ([1-9][0-9]{0,2}) '
        r'(минуту|минуты|минут|час|часа|часов),? напомни за ([1-9][0-9]{0,2}) '
        r'(минуту|минуты|минут|час|часа|часов)\s+[—-]\s+(.{1,120})', value, re.IGNORECASE | re.DOTALL)
    if not natural or natural[2][:2] > '23':
        raise Denied('telegram_calendar_format_invalid')
    duration = _quantity_minutes(natural[3], natural[4])
    reminder = _quantity_minutes(natural[5], natural[6])
    title = natural[7]
    if duration > 1440 or not 5 <= reminder <= 1440 or title != title.strip():
        raise Denied('telegram_calendar_format_invalid')
    return {'kind': 'calendar_create', 'date': natural[1].lower(), 'clock': natural[2],
            'duration_minutes': duration, 'reminder_minutes': reminder, 'title': title}


def _quantity_minutes(value, unit):
    number = int(value)
    return number * 60 if unit.lower().startswith('час') else number


def parse_callback(value):
    match = re.fullmatch(r'cl:([0-9a-f-]{36}):([12]):([yn])', value) if isinstance(value, str) else None
    if not match or len(value.encode()) > 64:
        raise Denied('telegram_calendar_callback_invalid')
    return {'kind': 'calendar_decide', 'draft_id': match[1], 'version': int(match[2]),
            'confirm': match[3] == 'y', 'calendar_callback': value}


def keyboard(draft_id, version):
    return {'inline_keyboard': [[
        {'text': LABEL_ADD, 'callback_data': f'cl:{draft_id}:{version}:y'},
        {'text': LABEL_CANCEL, 'callback_data': f'cl:{draft_id}:{version}:n'},
    ]]}


def _operation(iid, suffix):
    return str(uuid5(NAMESPACE_URL, f'acc:calendar:{iid}:{suffix}'))


def _document(session, intent):
    schedule = reminder_schedule(session)
    if not schedule.get('configured'):
        raise Denied('calendar_timezone_not_configured')
    zone = ZoneInfo(schedule['timezone'])
    date = intent['date']
    if date in {'сегодня', 'завтра'}:
        # Derive the owner date from the database clock, never from the Telegram client.
        today = session.execute(text('SELECT clock_timestamp()')).scalar_one().astimezone(zone).date()
        date = (today + timedelta(days=date == 'завтра')).isoformat()
    try:
        start = datetime.strptime(date + ' ' + intent['clock'], '%Y-%m-%d %H:%M').replace(tzinfo=zone)
    except ValueError:
        raise Denied('telegram_calendar_format_invalid') from None
    # Round trip rejects nonexistent local wall times during a DST transition.
    if start.astimezone(ZoneInfo('UTC')).astimezone(zone).replace(fold=start.fold) != start:
        raise Denied('calendar_local_time_nonexistent')
    if start.replace(fold=0).utcoffset() != start.replace(fold=1).utcoffset():
        raise Denied('calendar_local_time_ambiguous')
    end = start + timedelta(minutes=intent['duration_minutes'])
    return {'title': intent['title'], 'start': start.isoformat(), 'end': end.isoformat(),
            'timezone': schedule['timezone'], 'note': '',
            'telegram_reminder_minutes': intent['reminder_minutes']}


def create_card(bridge, iid, intent):
    with bridge.store.transaction() as session:
        bridge.store.check_audit(session)
        row = session.get(TelegramInbox, iid)
        if row.state == 'DONE':
            return
        if row.state != 'RECEIVED':
            raise Denied('telegram_calendar_not_pending')
        document = _document(session, intent)
    draft = create(bridge.store, 'owner', document, _operation(iid, 'create'), digest(intent))
    with bridge.store.transaction() as session:
        bridge.store.check_audit(session)
        row = session.get(TelegramInbox, iid)
        if row.state == 'DONE':
            return
        if row.state != 'RECEIVED':
            raise Denied('telegram_calendar_not_pending')
        text = (f"Черновик календаря\n{draft['document']['title']}\n"
                f"{draft['document']['start']} — {draft['document']['end']}\n"
                f"Telegram напомнит за {draft['document']['telegram_reminder_minutes']} мин.\n\n"
                'Подтверждение пока сохранит событие локально. Google ещё не подключён.')
        delivery = bridge.finish(session, iid, text, keyboard(draft['id'], draft['version']))
        bridge.store.audit(session, ISSUED, 'owner', profile=bridge.profile, draft_id=draft['id'],
                           version=draft['version'], delivery_id=delivery,
                           document_hash=digest(draft['document']))


def _verify(bridge, session, intent):
    delivery = session.scalar(select(TelegramDelivery).where(
        TelegramDelivery.profile == bridge.profile, TelegramDelivery.state == 'SENT',
        TelegramDelivery.message_id == intent['message_id']).limit(1))
    if not delivery or delivery.body.get('chat_id') != bridge.owner:
        raise Denied('telegram_calendar_card_not_observed')
    expected = keyboard(intent['draft_id'], intent['version'])
    if canonical(delivery.body.get('reply_markup')) != canonical(expected):
        raise Denied('telegram_calendar_card_not_observed')
    issued = session.execute(select(Audit).where(
        Audit.event['kind'].as_string() == ISSUED,
        Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['draft_id'].as_string() == intent['draft_id'],
        Audit.event['version'].as_integer() == intent['version'],
        Audit.event['delivery_id'].as_string() == delivery.id)).first()
    observed = session.execute(select(Audit).where(
        Audit.event['kind'].as_string() == 'telegram_delivery_observed',
        Audit.event['delivery_id'].as_string() == delivery.id,
        Audit.event['message_id'].as_integer() == intent['message_id'],
        Audit.event['state'].as_string() == 'SENT')).first()
    if not issued or not observed:
        raise Denied('telegram_calendar_card_not_observed')


def apply_decision(bridge, iid, intent):
    with bridge.store.transaction() as session:
        bridge.store.check_audit(session)
        row = session.get(TelegramInbox, iid)
        if row.state == 'DONE':
            return
        if row.state != 'RECEIVED':
            raise Denied('telegram_calendar_not_pending')
        _verify(bridge, session, intent)
    result = decide(bridge.store, 'owner', intent['draft_id'], intent['version'],
                    _operation(iid, 'decision'), intent['confirm'])
    with bridge.store.transaction() as session:
        row = session.get(TelegramInbox, iid)
        if row.state != 'DONE':
            text = ('Событие подтверждено локально. Google Calendar ещё не подключён; '
                    'внешний вызов не выполнялся.' if result['state'] == 'CONFIRMED_LOCAL'
                    else 'Черновик календаря отменён. Внешний вызов не выполнялся.')
            bridge.finish(session, iid, text)


def list_reply(session, profile=None):
    rows = list_drafts_locked(session, 'owner', 5)
    from .telegram_calendar_voice import pending_count
    voices = pending_count(session, profile) if profile else 0
    if not rows:
        voice = f'\nГолосовых заметок, ожидающих расшифровки: {voices}.\n' if voices else '\n'
        return ('Черновиков календаря пока нет.' + voice + 'Пример:\n'
                '/calendar завтра в 15:00 на 30 минут, напомни за 20 минут — Созвон\n\n'
                'Google Calendar ещё не подключён.')
    labels = {'DRAFT': 'ждёт подтверждения', 'CONFIRMED_LOCAL': 'подтверждено локально',
              'CANCELLED': 'отменено'}
    sync_labels = {'NOT_PREPARED': '', 'PREPARED': ' · Google подготовлен',
                   'UNKNOWN': ' · Google требует сверки', 'SYNCED': ' · Google синхронизирован'}
    lines = [f"• {row['document']['start']} · {row['document']['title']} · {labels[row['state']]}"
             f"{sync_labels[sync_state(session, row['id'])['state']]}" for row in rows]
    voice = f'\nГолосовых заметок, ожидающих расшифровки: {voices}.' if voices else ''
    return ('Последние события календаря:\n' + '\n'.join(lines) + voice
            + '\n\nGoogle Calendar ещё не подключён; просмотр ничего не отправляет.')


def collect_reminders(bridge, session):
    """Queue each confirmed local reminder once through the existing delivery path."""
    now = bridge.store.now(session)
    queued = []
    for row in list_drafts_locked(session, 'owner', 20):
        if row['state'] != 'CONFIRMED_LOCAL':
            continue
        document = row['document']
        start, end = datetime.fromisoformat(document['start']), datetime.fromisoformat(document['end'])
        due = start - timedelta(minutes=document['telegram_reminder_minutes'])
        if not due <= now < end:
            continue
        existing = session.execute(select(Audit).where(
            Audit.event['kind'].as_string() == REMINDER,
            Audit.event['profile'].as_string() == bridge.profile,
            Audit.event['draft_id'].as_string() == row['id'])).first()
        if existing:
            continue
        text = (f"Напоминание: {document['title']}\nНачало: {document['start']}\n\n"
                'Google Calendar может быть ещё не подключён. Напоминание ничего не запускает.')
        delivery = bridge.enqueue(session, f"calendar-reminder:{row['id']}:{digest(document)}", text)
        bridge.store.audit(session, REMINDER, 'system', profile=bridge.profile, draft_id=row['id'],
                           delivery_id=delivery, document_hash=digest(document), due_at=due.isoformat())
        queued.append(delivery)
    return queued
