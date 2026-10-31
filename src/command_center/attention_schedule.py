"""Versioned owner reminder schedule and durable Telegram summary collection."""
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from .attention import build
from .models import Audit
from .store import Denied, digest

EVENT = 'owner_attention_schedule_changed'
NOTICE = 'owner_attention_report_queued'
SUPPRESSED = 'owner_attention_report_suppressed'
MAX_CHANGES = 1000


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
    if not schedule['configured']:
        return ('Напоминания центра внимания ещё не настроены.\n\n'
                'Настройка доступна владельцу в веб-интерфейсе Commander. '
                'Просмотр ничего не меняет; выполнение не запускалось.')
    state = 'включены' if schedule['enabled'] else 'выключены'
    return (f'Напоминания центра внимания: {state}.\n'
            f"Часовой пояс: {schedule['timezone']}.\n"
            f"Время сводок: {', '.join(schedule['report_times'])}.\n"
            f"Тихие часы: {schedule['quiet_start']}–{schedule['quiet_end']}.\n"
            f"Версия настройки: {schedule['version']}.\n\n"
            'Просмотр ничего не меняет; выполнение не запускалось.')


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
    clock = now.strftime('%H:%M')
    due = [value for value in schedule['report_times'] if value <= clock]
    if not due:
        return None
    snapshot = build(bridge.store, session)
    critical = snapshot['highest_level'] == 'critical'
    if _quiet(clock, schedule['quiet_start'], schedule['quiet_end']) and not critical:
        return None
    slot = now.date().isoformat() + 'T' + due[-1]
    existing = session.scalar(select(Audit).where(
        Audit.event['kind'].as_string().in_((NOTICE, SUPPRESSED)),
        Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['slot'].as_string() == slot).limit(1))
    if existing:
        if existing.event['kind'] == SUPPRESSED:
            return None
        delivery = existing.event.get('delivery_id')
        if not isinstance(delivery, str) or not re.fullmatch(r'[a-f0-9]{64}', delivery):
            raise Denied('attention_notice_history_invalid')
        return delivery
    latest = session.scalar(select(Audit).where(
        Audit.event['kind'].as_string() == NOTICE,
        Audit.event['profile'].as_string() == bridge.profile,
    ).order_by(Audit.sequence.desc()).limit(1))
    summary_hash = snapshot['attention_hash']
    if (latest and latest.event.get('summary_hash') == summary_hash
            and latest.event.get('schedule_version') == schedule['version']):
        bridge.store.audit(session, SUPPRESSED, 'system', profile=bridge.profile, slot=slot,
                           schedule_version=schedule['version'], summary_hash=summary_hash,
                           reason='unchanged')
        return None
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
