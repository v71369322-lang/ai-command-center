"""Owner agenda reads; no provider HTTP while holding a store transaction."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from .models import Control, TelegramInbox
from .store import Denied


def parse(value):
    words = ' '.join(value.lower().strip().rstrip('?!.,').split())
    aliases = {'/agenda': 'today', '/agenda сегодня': 'today', '/agenda завтра': 'tomorrow',
        '/agenda неделя': 'week', 'расписание на сегодня': 'today',
        'что у меня сегодня': 'today', 'расписание на завтра': 'tomorrow',
        'что у меня завтра': 'tomorrow', 'расписание на неделю': 'week'}
    # Explicit read-only phrasings, not substring matching: a request to add or
    # move an event must never be silently interpreted as an agenda read.
    for day, period in (('сегодня', 'today'), ('завтра', 'tomorrow')):
        for phrase in (f'что у меня {day} в календаре', f'что у меня в календаре {day}',
                       f'покажи календарь на {day}', f'покажи расписание на {day}'):
            aliases[phrase] = period
    if words in aliases:
        return {'kind': 'calendar_agenda', 'period': aliases[words]}
    if words.split()[:1] == ['/agenda']:
        raise Denied('telegram_agenda_period_invalid')
    return None


def render(result):
    zone = ZoneInfo(result['timezone'])
    lines = ['Основной календарь Google · ' + result['timezone']]
    rows = result['events']
    malformed = False
    for row in rows[:15]:
        if row.get('status') == 'cancelled':
            continue
        title = row.get('summary', 'Без названия')
        if not isinstance(title, str):
            malformed = True
            continue
        title = ' '.join(title.split())[:120] or 'Без названия'
        try:
            start = row['start']
            if 'dateTime' in start:
                moment = datetime.fromisoformat(start['dateTime'])
                if moment.tzinfo is None:
                    raise ValueError()
                label = moment.astimezone(zone).strftime('%d.%m %H:%M')
            else:
                label = datetime.strptime(start['date'], '%Y-%m-%d').strftime('%d.%m') + ' · весь день'
        except (KeyError, TypeError, ValueError):
            malformed = True
            continue
        lines.append('• ' + label + ' — ' + title)
    if len(lines) == 1:
        lines.append('Событий за выбранный период не найдено.' if not malformed else
                     'Получены неполные записи; полное расписание показать не удалось.')
    elif malformed:
        lines.append('Некоторые неполные записи не показаны.')
    if result.get('truncated') or len(rows) > 15:
        lines.append('Показана часть событий. Полный список доступен в Google Calendar.')
    lines.append('Другие календари здесь не учитываются. События не изменены.')
    return '\n'.join(lines)


def reply(bridge, iid, intent):
    with bridge.store.transaction() as session:
        bridge.guard()
        bridge.store.check_audit(session)
        row = session.get(TelegramInbox, iid)
        if row.state == 'DONE':
            return
        if row.state != 'RECEIVED':
            raise Denied('telegram_agenda_not_pending')
        control = session.get(Control, 1)
        if bridge.calendar is None:
            text = 'Google Calendar ещё не подключён. События не изменены.'
            from .assistant_policy import assistant_only
            if assistant_only():
                from .personal_inbox import render as personal_render
                text += '\n\n' + personal_render(bridge, session, period=intent['period'], limit=4)
                text += '\n\n' + personal_render(bridge, session, 'reminder', period=intent['period'], limit=4)
            bridge.finish(session, iid, text[:4000])
            return
        if control.halted or control.recovery:
            bridge.finish(session, iid, 'Внешнее чтение календаря на паузе. События не изменены.')
            return
        epoch = control.epoch
        profile = bridge.calendar.profile
        zone = ZoneInfo(profile.timezone)
        today = bridge.store.now(session).astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)
        start = today + timedelta(days=intent['period'] == 'tomorrow')
        end = start + timedelta(days=7 if intent['period'] == 'week' else 1)
    # No Control row/audit lock is held across the potentially slow Google request.
    try:
        result = bridge.calendar.agenda(start.isoformat(), end.isoformat())
        text = render(result)
        status = 'read'
    except (Denied, httpx.HTTPError):
        text = 'Не удалось получить актуальное расписание Google. Подключение требует проверки. События не изменены.'
        status = 'unavailable'
    with bridge.store.transaction() as session:
        bridge.guard()
        bridge.store.check_audit(session)
        row = session.get(TelegramInbox, iid)
        if row.state == 'DONE':
            return
        if row.state != 'RECEIVED':
            raise Denied('telegram_agenda_not_pending')
        control = session.get(Control, 1)
        if control.halted or control.recovery or control.epoch != epoch:
            text = 'Режим работы изменился. Расписание не показано; события не изменены.'
            status = 'discarded'
        from .assistant_policy import assistant_only
        if assistant_only() and status != 'discarded':
            from .personal_inbox import render as personal_render
            # Keep provider errors explicit while still showing local owner records.
            local = personal_render(bridge, session, period=intent['period'], limit=4)
            local += '\n\n' + personal_render(bridge, session, 'reminder', period=intent['period'], limit=4)
            if len(text) > 1800:
                text = text[:1740] + '\nЧасть расписания; полный список в Google Calendar.'
            text += '\n\n' + local[:2100]
        bridge.finish(session, iid, text)
        bridge.store.audit(session, 'telegram_google_agenda_read', 'owner', profile=bridge.profile,
                           inbox_id=iid, period=intent['period'], status=status,
                           events_changed=False, model_called=False)
