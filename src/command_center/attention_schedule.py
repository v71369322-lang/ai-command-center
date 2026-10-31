"""Versioned owner reminder schedule and durable Telegram summary collection."""
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from .attention import build
from .models import Audit, TelegramDelivery
from .store import Denied, digest

EVENT = 'owner_attention_schedule_changed'
NOTICE = 'owner_attention_report_queued'
SUPPRESSED = 'owner_attention_report_suppressed'
OBSERVED = 'owner_attention_observed'
CRITICAL = 'owner_attention_critical_queued'
MAX_CHANGES = 1000
MAX_ACTIVITY = 20


def _events(session):
    rows = session.scalars(select(Audit).where(
        Audit.event['kind'].as_string() == EVENT,
        Audit.event['actor'].as_string() == 'owner').order_by(Audit.sequence).limit(MAX_CHANGES + 1)).all()
    if len(rows) > MAX_CHANGES:
        raise Denied('attention_schedule_history_limit')
    return rows


def _validate(document):
    if (set(document) != {'enabled', 'timezone', 'report_times', 'quiet_start', 'quiet_end'}
            or type(document['enabled']) is not bool
            or not isinstance(document['timezone'], str) or len(document['timezone']) > 64
            or not isinstance(document['report_times'], list)
            or not 1 <= len(document['report_times']) <= 3
            or len(set(document['report_times'])) != len(document['report_times'])
            or document['report_times'] != sorted(document['report_times'])
            or any(not isinstance(value, str) or not re.fullmatch(r'[0-2][0-9]:[0-5][0-9]', value)
                   or value[:2] > '23' for value in document['report_times'])
            or any(not isinstance(document[key], str)
                   or not re.fullmatch(r'[0-2][0-9]:[0-5][0-9]', document[key])
                   or document[key][:2] > '23' for key in ('quiet_start', 'quiet_end'))
            or document['quiet_start'] == document['quiet_end']):
        raise Denied('attention_schedule_invalid')
    try:
        ZoneInfo(document['timezone'])
    except ZoneInfoNotFoundError:
        raise Denied('attention_timezone_invalid') from None
    return document


def current(session):
    rows = _events(session)
    if not rows:
        return {'version': 0, 'configured': False, 'enabled': False}
    latest = rows[-1].event
    document = _validate(latest['schedule'])
    if latest.get('version') != len(rows) or latest.get('schedule_hash') != digest(document):
        raise Denied('attention_schedule_history_invalid')
    return {'version': latest['version'], 'configured': True, **document}


def telegram_reply(session):
    """Return schedule status without exposing an update or authority path."""
    schedule = current(session)
    recent = activity(session, 1)
    last = ''
    if recent:
        item = recent[0]
        outcome = ('отправлена' if item['outcome'] == 'queued' else
                   'критическое изменение отправлено' if item['outcome'] == 'critical' else
                   'подавлена как неизменная')
        if item['delivery_state'] in {'UNCERTAIN', 'CANCELLED'}:
            outcome = 'результат доставки неизвестен'
        last = f"\nПоследняя сводка ({item['slot']}): {outcome}."
    if not schedule['configured']:
        return ('Напоминания центра внимания ещё не настроены.\n\n'
                'Настройка доступна владельцу в веб-интерфейсе Commander. '
                'Просмотр ничего не меняет; выполнение не запускалось.' + last)
    state = 'включены' if schedule['enabled'] else 'выключены'
    return (f'Напоминания центра внимания: {state}.\n'
            f"Часовой пояс: {schedule['timezone']}.\n"
            f"Время сводок: {', '.join(schedule['report_times'])}.\n"
            f"Тихие часы: {schedule['quiet_start']}–{schedule['quiet_end']}.\n"
            f"Версия настройки: {schedule['version']}."
            f"{last}\n\nПросмотр ничего не меняет; выполнение не запускалось.")


def activity(session, limit=5):
    """Return bounded delivery metadata without message bodies or profile identifiers."""
    if type(limit) is not int or not 1 <= limit <= MAX_ACTIVITY:
        raise Denied('attention_activity_limit_invalid')
    rows = session.scalars(select(Audit).where(
        Audit.event['kind'].as_string().in_((NOTICE, SUPPRESSED, CRITICAL)),
    ).order_by(Audit.sequence.desc()).limit(limit)).all()
    result = []
    for row in rows:
        event = row.event
        slot, version, summary_hash = (event.get('slot'), event.get('schedule_version'),
                                       event.get('summary_hash'))
        if (not isinstance(slot, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-2][0-9]:[0-5][0-9]', slot)
                or type(version) is not int or version < 1
                or not isinstance(summary_hash, str) or not re.fullmatch(r'[a-f0-9]{64}', summary_hash)):
            raise Denied('attention_activity_history_invalid')
        delivery_state = None
        critical_bypass = False
        outcome = 'suppressed'
        if event['kind'] in {NOTICE, CRITICAL}:
            delivery_id = event.get('delivery_id')
            delivery = session.get(TelegramDelivery, delivery_id) if isinstance(delivery_id, str) else None
            if (not delivery or delivery.profile != event.get('profile')
                    or delivery.state not in {'NEW', 'SENDING', 'SENT', 'UNCERTAIN', 'CANCELLED'}):
                raise Denied('attention_activity_delivery_invalid')
            outcome = 'critical' if event['kind'] == CRITICAL else 'queued'
            delivery_state = delivery.state
            critical_bypass = event.get('critical_quiet_bypass') is True
        elif event.get('reason') != 'unchanged':
            raise Denied('attention_activity_history_invalid')
        result.append({'sequence': row.sequence, 'slot': slot, 'outcome': outcome,
                       'delivery_state': delivery_state, 'schedule_version': version,
                       'critical_quiet_bypass': critical_bypass})
    return result


def delivery_health(session):
    """Summarize the latest durable delivery receipt without probing Telegram."""
    recent = activity(session, 1)
    if not recent:
        return {'state': 'never', 'action_required': False, 'last_slot': None}
    latest = recent[0]
    delivery_state = latest['delivery_state']
    if latest['outcome'] == 'suppressed':
        state = 'suppressed'
    elif delivery_state == 'SENT':
        state = 'confirmed'
    elif delivery_state in {'NEW', 'SENDING'}:
        state = 'pending'
    else:
        state = 'uncertain'
    return {'state': state, 'action_required': state == 'uncertain',
            'last_slot': latest['slot']}


def _observe(bridge, session, snapshot, now, schedule):
    latest = session.scalar(select(Audit).where(
        Audit.event['kind'].as_string() == OBSERVED,
        Audit.event['profile'].as_string() == bridge.profile,
    ).order_by(Audit.sequence.desc()).limit(1))
    summary_hash = snapshot['attention_hash']
    critical = snapshot['highest_level'] == 'critical'
    if latest and latest.event.get('summary_hash') == summary_hash:
        return None
    bridge.store.audit(session, OBSERVED, 'system', profile=bridge.profile,
                       summary_hash=summary_hash, critical=critical,
                       schedule_version=schedule['version'])
    observation = session.scalar(select(Audit).order_by(Audit.sequence.desc()).limit(1))
    if not critical:
        return None
    lines = [f"{item['count']} · {item['label']}" for item in snapshot['items']
             if item['level'] == 'critical']
    text = ('Критическое изменение AI Commander\n' + '\n'.join(lines)
            + '\n\nУведомление ничего не запускает. Откройте /attention для общей сводки.')
    delivery = bridge.enqueue(session, f'attention-critical:{observation.sequence}:{summary_hash}', text)
    quiet = _quiet(now.strftime('%H:%M'), schedule['quiet_start'], schedule['quiet_end'])
    bridge.store.audit(session, CRITICAL, 'system', profile=bridge.profile,
                       slot=now.strftime('%Y-%m-%dT%H:%M'), delivery_id=delivery,
                       schedule_version=schedule['version'], summary_hash=summary_hash,
                       observation_sequence=observation.sequence, critical_quiet_bypass=quiet)
    return delivery


def configure(store, role, document, expected_version, operation_id):
    if role != 'owner':
        raise Denied('owner_required')
    document = _validate(document)
    if (type(expected_version) is not int or expected_version < 0 or expected_version > 1000
            or not isinstance(operation_id, str)
            or not re.fullmatch(r'[a-f0-9-]{36}', operation_id)):
        raise Denied('attention_schedule_request_invalid')
    fingerprint = digest({'schedule': document, 'expected_version': expected_version})
    with store.transaction() as session:
        store.check_audit(session)
        rows = _events(session)
        duplicate = next((row for row in rows if row.event.get('operation_id') == operation_id), None)
        if duplicate:
            if duplicate.event.get('input_hash') != fingerprint:
                raise Denied('attention_schedule_idempotency_conflict')
            return current(session)
        state = current(session)
        if state['version'] != expected_version:
            raise Denied('attention_schedule_stale_version')
        if len(rows) >= MAX_CHANGES:
            raise Denied('attention_schedule_history_limit')
        store.audit(session, EVENT, 'owner', version=expected_version + 1, schedule=document,
                    schedule_hash=digest(document), operation_id=operation_id, input_hash=fingerprint)
        return {'version': expected_version + 1, 'configured': True, **document}


def _quiet(value, start, end):
    return start <= value < end if start < end else value >= start or value < end


def collect(bridge, session):
    schedule = current(session)
    if not schedule.get('enabled'):
        return None
    now = bridge.store.now(session).astimezone(ZoneInfo(schedule['timezone']))
    snapshot = build(bridge.store, session)
    proactive = _observe(bridge, session, snapshot, now, schedule)
    clock = now.strftime('%H:%M')
    due = [value for value in schedule['report_times'] if value <= clock]
    if not due:
        return proactive
    critical = snapshot['highest_level'] == 'critical'
    if _quiet(clock, schedule['quiet_start'], schedule['quiet_end']) and not critical:
        return proactive
    slot = now.date().isoformat() + 'T' + due[-1]
    existing = session.scalar(select(Audit).where(
        Audit.event['kind'].as_string().in_((NOTICE, SUPPRESSED)),
        Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['slot'].as_string() == slot).limit(1))
    if existing:
        if existing.event['kind'] == SUPPRESSED:
            return proactive
        delivery = existing.event.get('delivery_id')
        if not isinstance(delivery, str) or not re.fullmatch(r'[a-f0-9]{64}', delivery):
            raise Denied('attention_notice_history_invalid')
        return delivery
    latest = session.scalar(select(Audit).where(
        Audit.event['kind'].as_string().in_((NOTICE, CRITICAL)),
        Audit.event['profile'].as_string() == bridge.profile,
    ).order_by(Audit.sequence.desc()).limit(1))
    summary_hash = snapshot['attention_hash']
    if (latest and latest.event.get('summary_hash') == summary_hash
            and latest.event.get('schedule_version') == schedule['version']):
        bridge.store.audit(session, SUPPRESSED, 'system', profile=bridge.profile, slot=slot,
                           schedule_version=schedule['version'], summary_hash=summary_hash,
                           reason='unchanged')
        return proactive
    lines = [f"{item['count']} · {item['label']}" for item in snapshot['items']]
    heading = 'Критическая сводка AI Commander' if critical else 'Сводка AI Commander'
    text = (heading + '\n' + ('\n'.join(lines) if lines else 'Пунктов, требующих внимания, нет.')
            + '\n\nПросмотр ничего не запускает. Откройте центр для подробностей.')
    key = 'attention:' + slot + ':' + digest(snapshot)
    delivery = bridge.enqueue(session, key, text)
    bridge.store.audit(session, NOTICE, 'system', profile=bridge.profile, slot=slot,
                       delivery_id=delivery, schedule_version=schedule['version'],
                       summary_hash=summary_hash, critical_quiet_bypass=bool(
                           critical and _quiet(clock, schedule['quiet_start'], schedule['quiet_end'])))
    return delivery
