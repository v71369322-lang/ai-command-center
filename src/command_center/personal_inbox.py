"""Personal records over checked Telegram intake and the existing audit/outbox."""
from datetime import date, datetime, timedelta
import re
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, cast, select

from .models import Audit, Control, TelegramInbox
from .store import Denied, digest

CREATED = 'personal_inbox_record_created'
CHANGED = 'personal_inbox_record_changed'
REMINDER = 'personal_inbox_reminder_queued'
LABELS = {'task': 'Задача', 'idea': 'Идея', 'note': 'Заметка', 'reminder': 'Напоминание'}
STATES = {'active': 'активна', 'deferred': 'отложена', 'delegated': 'делегирована',
          'waiting': 'в ожидании', 'blocked': 'заблокирована', 'done': 'выполнена'}
MAX_RECORDS = 1000


def parse(value):
    """Deliberately bounded phrases; no model calls or guessed dates/categories."""
    text = ' '.join(value.strip().split()).rstrip('.!?')
    low = text.lower()
    for kind, words in {'task': ('мои задачи', 'покажи задачи', 'список задач'),
                        'idea': ('мои идеи', 'покажи идеи'),
                        'note': ('мои заметки', 'покажи заметки'),
                        'reminder': ('мои напоминания', 'покажи напоминания')}.items():
        if low in words:
            return {'action': 'list', 'category': kind}
    commands = {'готово': 'done', 'заверши': 'done', 'отложи': 'deferred',
                'возобнови': 'active', 'делегируй': 'delegated',
                'заблокируй': 'blocked', 'ожидание': 'waiting'}
    match = re.fullmatch(r'(' + '|'.join(commands) + r') (?:задачу )?№?([0-9]{1,16})', low)
    if match:
        return {'action': 'status', 'number': match[2], 'status': commands[match[1]]}
    match = re.fullmatch(r'это (задача|идея|заметка) №?([0-9]{1,16})', low)
    if match:
        return {'action': 'category', 'number': match[2],
                'category': {'задача': 'task', 'идея': 'idea', 'заметка': 'note'}[match[1]]}
    if re.match(r'^напомни\b', low):
        if (re.search(r'\b(?:или|либо|если)\b', low)
                or len(re.findall(r'\bв [0-2]?\d(?::[0-5]\d)?\b', low)) > 1):
            return {'action': 'invalid_reminder'}
        match = re.fullmatch(r'напомни(?: мне)? (сегодня|завтра|послезавтра|\d{4}-\d{2}-\d{2}) '
                             r'в ([0-2]?\d(?::[0-5]\d)?)[,:]? (.+)', text, re.I)
        if not match or int(match[2].split(':')[0]) > 23:
            return {'action': 'invalid_reminder'}
        return {'action': 'create', 'category': 'reminder', 'title': match[3],
                'date': match[1].lower(),
                'clock': match[2].zfill(5) if ':' in match[2] else match[2].zfill(2) + ':00'}
    match = re.fullmatch(r'(?:(?:запиши|сохрани)(?: мне)? )?'
                        r'(идею|идея|заметку|заметка|задачу|задача)[: ,]+(.+)', text, re.I)
    if match:
        category = {'идею': 'idea', 'идея': 'idea', 'заметку': 'note', 'заметка': 'note',
                    'задачу': 'task', 'задача': 'task'}[match[1].lower()]
        return {'action': 'create', 'category': category, 'title': match[2]}
    if re.match(r'^(купить|позвонить|проверить|заказать|подготовить|забрать|отправить|оплатить)\s', low):
        return {'action': 'create', 'category': 'task', 'title': text}
    return None


def project_hint(value):
    aliases = {'vanilla-sugar': r'\b(?:кондитерск\w*|vanilla\s*&?\s*sugar|ваниль и сахар)\b',
               'lnauto': r'\b(?:автосервис\w*|lnauto)\b',
               'capital-lab': r'\bcapital lab\b', 'command-center': r'\b(?:jarvis|джарвис)\b'}
    matches = [key for key, pattern in aliases.items() if re.search(pattern, value, re.I)]
    return matches[0] if len(matches) == 1 else None


def due_at(intent, received, timezone, now):
    zone = ZoneInfo(timezone)
    day = intent['date']
    relative = {'сегодня': 0, 'завтра': 1, 'послезавтра': 2}
    if day in relative:
        day = (received.astimezone(zone).date() + timedelta(days=relative[day])).isoformat()
    local = datetime.combine(date.fromisoformat(day), datetime.strptime(intent['clock'], '%H:%M').time())
    moment = local.replace(tzinfo=zone)
    if (moment.astimezone(ZoneInfo('UTC')).astimezone(zone).replace(tzinfo=None) != local
            or moment.replace(fold=0).utcoffset() != moment.replace(fold=1).utcoffset()
            or not now < moment <= now + timedelta(days=366)):
        raise ValueError('personal_reminder_time_invalid')
    return moment.isoformat()


def records(bridge, session, request_ids=None):
    query = select(Audit).where(
        Audit.event['kind'].as_string().in_([CREATED, CHANGED]),
        Audit.event['profile'].as_string() == bridge.profile)
    if request_ids is not None:
        if not request_ids:
            return {}
        query = query.where(Audit.event['request_id'].as_string().in_(request_ids))
    rows = list(session.scalars(query.order_by(Audit.sequence).limit(5001)))
    if len(rows) > 5000:
        raise Denied('personal_inbox_history_limit')
    source_ids = [row.event.get('request_id') for row in rows if isinstance(row.event.get('request_id'), str)]
    sources = {row.id: row for row in session.scalars(select(TelegramInbox).where(TelegramInbox.id.in_(source_ids)))}
    result = {}
    for row in rows:
        e = row.event
        rid, document = e.get('request_id'), e.get('document')
        if not isinstance(rid, str):
            raise Denied('personal_inbox_history_invalid')
        previous = result.get(rid)
        if (e.get('actor') != 'owner' or not isinstance(document, dict)
                or set(document) != {'title', 'category', 'status', 'due_at'}
                or document['category'] not in LABELS or document['status'] not in STATES
                or not isinstance(document['title'], str) or not 1 <= len(document['title']) <= 500
                or (document['due_at'] is not None and document['category'] != 'reminder')
                or e.get('document_hash') != digest(document)
                or e.get('version') != (previous['version'] + 1 if previous else 1)
                or (e['kind'] == CREATED) != (previous is None)):
            raise Denied('personal_inbox_history_invalid')
        source = sources.get(rid)
        if (not source or source.profile != bridge.profile or source.task_id is not None
                or source.fingerprint != e.get('request_fingerprint')):
            raise Denied('personal_inbox_source_changed')
        if document['due_at'] is not None:
            try:
                moment = datetime.fromisoformat(document['due_at'])
                if moment.tzinfo is None:
                    raise ValueError()
            except (ValueError, TypeError):
                raise Denied('personal_inbox_history_invalid') from None
        result[rid] = {'id': rid, 'version': e['version'], **document}
    # Archived requests retain history but cannot keep producing notifications.
    result = {rid: item for rid, item in result.items() if sources[rid].state == 'NEEDS_PLANNING'}
    from .telegram_requests import captured_text
    for rid, item in result.items():
        bridge.check_text(captured_text(session, sources[rid]))
        bridge.check_text(item['title'])
    return result


def render(bridge, session, category='task', *, period=None, limit=12):
    from .project_inbox import history, PROJECTS
    assigned, _ = history(session)
    labels = dict(PROJECTS)
    items = list(records(bridge, session).values())
    items = [r for r in items if r['category'] == category and r['status'] != 'done']
    if period is not None:
        from .attention_schedule import current
        timezone = current(session).get('timezone', 'Europe/Moscow')
        today = bridge.store.now(session).astimezone(ZoneInfo(timezone)).date()
        end = today + timedelta(days=1 if period == 'tomorrow' else 6 if period == 'week' else 0)
        items = [r for r in items if not r['due_at'] or datetime.fromisoformat(r['due_at']).date() <= end]
    lines = [{'task': 'Личные задачи', 'idea': 'Банк идей', 'note': 'Заметки',
              'reminder': 'Личные напоминания'}[category] + ':']
    for r in items[-limit:]:
        project = labels.get(assigned.get(r['id'], {}).get('project_id'), 'Не распределён')
        when = ' · ' + r['due_at'] if r['due_at'] else ' · без срока'
        title = r['title'][:140] + ('…' if len(r['title']) > 140 else '')
        lines.append(f"• №{r['id'].rsplit(':', 1)[1]} {title} · {project} · {STATES[r['status']]}{when}")
    if not items:
        lines.append('Пока нет записей.')
    if len(items) > limit:
        lines.append(f'Показаны последние {limit} записей.')
    return '\n'.join(lines)[:3800]


def handle_locked(bridge, session, iid, value, *, received_at=None):
    from .assistant_policy import assistant_only
    if not assistant_only():
        return False
    intent = parse(value)
    if intent is None:
        return False
    if intent['action'] == 'list':
        bridge.finish(session, iid, render(bridge, session, intent['category']))
        return True
    control = session.get(Control, 1)
    if control.halted or control.recovery:
        bridge.finish(session, iid, 'Изменение личных записей на паузе. Снять остановку: /resume.')
        return True
    if intent['action'] == 'invalid_reminder':
        bridge.finish(session, iid, 'Напоминание не создано: нужны точная дата, время и текст. '
                      'Например: «Напомни завтра в 11:00 позвонить поставщику».')
        return True
    row = session.get(TelegramInbox, iid)
    all_records = records(bridge, session)
    if intent['action'] in {'status', 'category'}:
        rid = bridge.profile + ':' + intent['number']
        item = all_records.get(rid)
        if not item:
            bridge.finish(session, iid, 'Личная запись с таким номером не найдена. Покажите «мои задачи» или «мои идеи».')
            return True
        if intent['action'] == 'status' and item['category'] not in {'task', 'reminder'}:
            bridge.finish(session, iid, 'Это идея или заметка. Для превращения в задачу напишите '
                          f'«Это задача №{intent["number"]}».')
            return True
        document = {k: item[k] for k in ('title', 'category', 'status', 'due_at')}
        if intent['action'] == 'category':
            document.update(category=intent['category'], status='active', due_at=None)
        else:
            document['status'] = intent['status']
        if document == {k: item[k] for k in document}:
            bridge.finish(session, iid, 'Запись уже в этом состоянии. Ничего не изменено.')
            return True
        source = session.get(TelegramInbox, rid)
        bridge.store.audit(session, CHANGED, 'owner', profile=bridge.profile, request_id=rid,
            request_fingerprint=source.fingerprint, version=item['version'] + 1,
            document=document, document_hash=digest(document), source_iid=iid)
        bridge.finish(session, iid, f"№{intent['number']}: {LABELS[document['category']]} · {STATES[document['status']]}. "
                      'Обновлена личная запись; внешние действия не выполнялись.')
        return True
    if len(all_records) >= MAX_RECORDS:
        raise Denied('personal_inbox_capacity')
    title = intent['title'].strip()
    if not 1 <= len(title) <= 500:
        bridge.finish(session, iid, 'Запись не сохранена: нужен текст длиной до 500 символов.')
        return True
    due = None
    if intent['category'] == 'reminder':
        from .attention_schedule import current
        schedule = current(session)
        if not schedule.get('configured'):
            bridge.finish(session, iid, 'Напоминание не создано: сначала нужно настроить часовой пояс владельца.')
            return True
        try:
            due = due_at(intent, received_at or row.created_at, schedule['timezone'], bridge.store.now(session))
        except (ValueError, KeyError):
            bridge.finish(session, iid, 'Напоминание не создано: дата или время некорректны либо уже прошли. '
                          'Укажите будущую дату, время и текст поручения.')
            return True
    row.state = 'NEEDS_PLANNING'
    document = {'title': title, 'category': intent['category'], 'status': 'active', 'due_at': due}
    bridge.store.audit(session, CREATED, 'owner', profile=bridge.profile, request_id=iid,
        request_fingerprint=row.fingerprint, version=1, document=document, document_hash=digest(document))
    from .project_inbox import classify_locked, PROJECTS
    project = project_hint(title)
    if project:
        classify_locked(bridge.store, session, 'owner', iid, project, 0,
                        str(uuid5(NAMESPACE_URL, 'personal-project:' + iid)))
    number = iid.rsplit(':', 1)[1]
    from .telegram_project_picker import keyboard, issue
    when = '\nНапомню: ' + due + ' в Telegram. В Google событие не создавалось.' if due else '\nСрок не назначен.'
    saved = 'сохранено' if intent['category'] == 'reminder' else 'сохранена'
    label = dict(PROJECTS).get(project, 'Не распределён')
    text = f"{LABELS[document['category']]} {saved}: №{number}.\n{title}\nРаздел: {label}.{when}"
    if intent['category'] == 'task':
        text += f'\nЗавершить: «Готово №{number}». Само поручение ещё не выполнено.'
    else:
        text += f'\nИсправить тип: «Это задача №{number}» или «Это идея №{number}».'
    delivery = bridge.enqueue(session, iid + ':reply', text, keyboard(number, 1 if project else 0))
    issue(bridge, session, delivery, number, 1 if project else 0)
    return True


def collect_reminders(bridge, session):
    control = session.get(Control, 1)
    if control.halted or control.recovery:
        return []
    queued = []
    now = bridge.store.now(session)
    already = select(Audit.event['request_id'].as_string()).where(
        Audit.event['kind'].as_string() == REMINDER, Audit.event['profile'].as_string() == bridge.profile)
    # Most polls have no due reminders. Avoid walking all saved tasks/ideas on every poll.
    due_ids = list(session.scalars(select(Audit.event['request_id'].as_string()).join(TelegramInbox,
        TelegramInbox.id == Audit.event['request_id'].as_string()).where(
        Audit.event['kind'].as_string() == CREATED, Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['document']['category'].as_string() == 'reminder', TelegramInbox.state == 'NEEDS_PLANNING',
        cast(Audit.event['document']['due_at'].as_string(), DateTime(timezone=True)) <= now,
        Audit.event['request_id'].as_string().not_in(already)).limit(MAX_RECORDS + 1)))
    if len(due_ids) > MAX_RECORDS:
        raise Denied('personal_inbox_capacity')
    for r in records(bridge, session, due_ids).values():
        if r['category'] != 'reminder' or r['status'] != 'active' or not r['due_at']:
            continue
        if datetime.fromisoformat(r['due_at']) > now:
            continue
        text = f"Напоминание №{r['id'].rsplit(':', 1)[1]}: {r['title']}\nНазначено: {r['due_at']}"
        delivery = bridge.enqueue(session, f"personal-reminder:{r['id']}", text)
        bridge.store.audit(session, REMINDER, 'system', profile=bridge.profile, request_id=r['id'],
            version=r['version'], document_hash=digest({k: r[k] for k in ('title', 'category', 'status', 'due_at')}),
            delivery_id=delivery, due_at=r['due_at'])
        queued.append(delivery)
    return queued


def delivery_allowed(bridge, session, delivery):
    """Recheck a due notification before HTTP; never retry an uncertain send."""
    anchor = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == REMINDER,
        Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['delivery_id'].as_string() == delivery.id).limit(1))
    if not anchor:
        return True
    control = session.get(Control, 1)
    event = anchor.event
    item = records(bridge, session, [event['request_id']]).get(event['request_id'])
    valid = (not control.halted and not control.recovery and item is not None
             and item['category'] == 'reminder' and item['status'] == 'active'
             and item['version'] == event['version']
             and digest({k: item[k] for k in ('title', 'category', 'status', 'due_at')}) == event['document_hash'])
    if not valid:
        delivery.state = 'CANCELLED'
        bridge.store.audit(session, 'personal_inbox_reminder_suppressed', 'system', profile=bridge.profile,
            request_id=event['request_id'], delivery_id=delivery.id, reason='stopped_or_record_changed')
    return valid
