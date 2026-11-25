"""Small deterministic meeting dialogue; missing details are never invented."""
from datetime import date, datetime, timedelta
import re
from zoneinfo import ZoneInfo

from sqlalchemy import select

from .attention_schedule import current as schedule
from .models import Audit, Control, TelegramInbox
from .store import Denied, digest

UPDATED = 'telegram_calendar_dialogue_updated'
TTL = timedelta(minutes=10)


def extract(value, *, initial=False):
    value = value.strip().rstrip('.!?').strip()
    if not value or len(value) > 500:
        return None
    if initial:
        match = re.fullmatch(r'(?:запиши|добавь|создай)(?: мне)? (.+)', value, re.I)
        if not match or not re.search(r'\b(?:встречу|созвон|событие)\b', match[1], re.I):
            return None
        value = match[1]
    if re.search(r'\b(?:не|или|отмени|перенеси|удали)\b', value, re.I):
        return {'ambiguous': True}
    fields = {}
    patterns = {
        'date': r'\b(?:послезавтра|завтра|сегодня|\d{4}-\d{2}-\d{2})\b',
        'clock': r'\b(?:[01]?\d|2[0-3]):[0-5]\d\b',
        'duration': r'\bна ([1-9]\d{0,2}) (минуту|минуты|минут|час|часа|часов)\b',
    }
    rest = value
    for field, pattern in patterns.items():
        matches = list(re.finditer(pattern, rest, re.I))
        if len(matches) > 1:
            return {'ambiguous': True}
        if not matches:
            continue
        match = matches[0]
        if field == 'duration':
            fields['duration_minutes'] = int(match[1]) * (60 if match[2].lower().startswith('час') else 1)
            if fields['duration_minutes'] > 1440:
                return {'ambiguous': True}
        elif field == 'clock':
            fields['clock'] = match[0].zfill(5)
        else:
            fields['date'] = match[0].lower()
        rest = rest[:match.start()] + ' ' + rest[match.end():]
    if 'date' in fields and fields['date'][0].isdigit():
        try:
            date.fromisoformat(fields['date'])
        except ValueError:
            return {'ambiguous': True}
    rest = re.sub(r'\b(?:в|мне|пожалуйста)\b', ' ', rest, flags=re.I)
    rest = re.sub(r'\s+', ' ', rest).strip(' ,;—-')
    if initial:
        title = re.sub(r'\bвстречу\b', 'Встреча', rest, flags=re.I)
        title = re.sub(r'\bсобытие\b', 'Событие', title, flags=re.I)
        if not 1 <= len(title) <= 120 or re.search(r'\d', title):
            return {'ambiguous': True}
        fields['title'] = title[0].upper() + title[1:]
    elif rest:
        return None
    return fields or None


def _latest(session, profile):
    row = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == UPDATED,
        Audit.event['profile'].as_string() == profile).order_by(Audit.sequence.desc()).limit(1))
    if not row:
        return None
    event = row.event
    if event.get('fields_hash') != digest(event.get('fields')):
        raise Denied('calendar_dialogue_history_invalid')
    return event


def handle_locked(bridge, session, iid, value):
    """Called for text capture or an observed, owner-accepted voice transcript."""
    fields = extract(value, initial=True)
    initial = fields is not None
    previous = _latest(session, bridge.profile)
    now = bridge.store.now(session)
    active = (previous and previous['state'] == 'OPEN'
              and now < datetime.fromisoformat(previous['expires_at']))
    if not initial:
        if not active:
            return False
        if value.strip().lower().rstrip('.!') == 'отмена':
            bridge.store.audit(session, UPDATED, 'owner', profile=bridge.profile, source_iid=iid,
                fields=previous['fields'], fields_hash=previous['fields_hash'], state='CANCELLED',
                expires_at=previous['expires_at'], root_iid=previous['root_iid'])
            bridge.finish(session, iid, 'Подготовка встречи отменена. Событие не создавалось.')
            return True
        fields = extract(value)
        if fields is None:
            return False
    control = session.get(Control, 1)
    if control.halted or control.recovery:
        bridge.finish(session, iid, 'Подготовка встреч на паузе. Событие не создано. Снять остановку: /resume.')
        return True
    if fields.get('ambiguous'):
        bridge.finish(session, iid, 'Не удалось однозначно разобрать детали встречи. '
                      'Укажите дату, время в формате 15:00 и длительность, например «на 30 минут». '
                      'Событие не создано.')
        return True
    settings = schedule(session)
    if not settings.get('configured'):
        bridge.finish(session, iid, 'Сначала нужно настроить ваш часовой пояс. Событие не создано.')
        return True
    zone = ZoneInfo(settings['timezone'])
    writer = getattr(bridge, 'calendar_writer', None)
    if writer and writer.profile.timezone != settings['timezone']:
        bridge.finish(session, iid, 'Часовой пояс календаря не совпадает с настройками. Событие не создано.')
        return True
    context = digest({'timezone': settings['timezone'], 'epoch': control.epoch,
                      'revision': bridge.store.settings.source_revision})
    if not initial and previous.get('context') != context:
        bridge.finish(session, iid, 'Настройки встречи изменились. Повторите поручение целиком; событие не создано.')
        return True
    if fields.get('date') in {'сегодня', 'завтра', 'послезавтра'}:
        # Pin relative dates at the message's processing time; subsequent answers
        # never move an already-resolved date across midnight.
        days = {'сегодня': 0, 'завтра': 1, 'послезавтра': 2}[fields['date']]
        received = session.get(TelegramInbox, iid).created_at
        fields['date'] = (received.astimezone(zone).date() + timedelta(days=days)).isoformat()
    merged = fields if initial else {**previous['fields'], **fields}
    complete = all(k in merged for k in ('title', 'date', 'clock', 'duration_minutes'))
    intent = {'kind': 'calendar_create', **merged, 'reminder_minutes': 20}
    if complete:
        from .telegram_calendar import _document
        from .calendar_drafts import validate
        try:
            document = validate(_document(session, intent))
        except (Denied, ValueError):
            bridge.finish(session, iid, 'Дата или время некорректны. Повторите поручение с точной датой и временем.')
            return True
        if datetime.fromisoformat(document['start']) <= now:
            bridge.finish(session, iid, 'Это время уже прошло. Укажите будущую дату и время; событие не создано.')
            return True
    expires = (now + TTL).isoformat() if initial else previous['expires_at']
    bridge.store.audit(session, UPDATED, 'owner', profile=bridge.profile, source_iid=iid,
        root_iid=iid if initial else previous['root_iid'], fields=merged, fields_hash=digest(merged),
        state='READY' if complete else 'OPEN', expires_at=expires, context=context)
    if complete:
        from .telegram_calendar import create_card_locked
        create_card_locked(bridge, session, iid, intent)
        return True
    questions = []
    if 'date' not in merged:
        questions.append('На какую дату?')
    if 'clock' not in merged:
        questions.append('Во сколько? Например, 15:00.')
    if 'duration_minutes' not in merged:
        questions.append('Сколько продлится? Например, на 30 минут.')
    date = f"Дата: {merged['date']} ({settings['timezone']}).\n" if 'date' in merged else ''
    bridge.finish(session, iid, date + '\n'.join(questions) +
                  '\nОтветьте обычным сообщением. Для отмены напишите «отмена». Событие ещё не создано.')
    return True
