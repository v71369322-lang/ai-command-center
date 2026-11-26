"""Owner-reviewed source spans; each saved item requires a real Telegram update."""
from datetime import datetime, timedelta
import re
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from .models import Audit, Control, TelegramDelivery, TelegramInbox
from .store import Denied, canonical, digest

PROPOSED = 'personal_mixed_review_proposed'
ACCEPTED = 'personal_mixed_item_accepted'


def parse_callback(value):
    if not isinstance(value, str):
        raise Denied('mixed_review_callback_invalid')
    match = re.fullmatch(r'mi:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}):([1-8r])', value)
    if not match:
        raise Denied('mixed_review_callback_invalid')
    if match[2] == 'r':
        return {'kind': 'mixed_refresh', 'proposal_id': match[1]}
    return {'kind': 'mixed_confirm', 'proposal_id': match[1], 'item': int(match[2])}


def keyboard(proposal_id, items):
    from .personal_inbox import LABELS
    rows = [[{'text': f"Сохранить {i}: {LABELS[item['document']['category']]}",
        'callback_data': f'mi:{proposal_id}:{i}'}] for i, item in enumerate(items, 1) if item['document']]
    return {'inline_keyboard': rows + [[{'text': 'Обновить разбор', 'callback_data': f'mi:{proposal_id}:r'}]]}


def allowed_markup(value):
    from .personal_inbox import LABELS
    try:
        rows = value['inline_keyboard']
        if not isinstance(rows, list) or not 2 <= len(rows) <= 9:
            return False
        items = [{'document': None} for _ in range(8)]
        proposal_id, previous = None, 0
        for row in rows[:-1]:
            if len(row) != 1:
                return False
            intent = parse_callback(row[0]['callback_data'])
            if intent['item'] <= previous or (proposal_id and proposal_id != intent['proposal_id']):
                return False
            proposal_id, previous = intent['proposal_id'], intent['item']
            category = next(k for k, label in LABELS.items() if row[0]['text'] == f'Сохранить {previous}: {label}')
            items[previous - 1] = {'document': {'category': category}}
        return canonical(value) == canonical(keyboard(proposal_id, items))
    except (KeyError, TypeError, StopIteration, Denied):
        return False


def source_time(session, source):
    if source.intent['kind'] == 'capture':
        return source.created_at
    if source.intent['kind'] != 'voice_confirm':
        raise Denied('mixed_review_source_invalid')
    from .telegram_voice_transcripts import ACCEPTED as VOICE_ACCEPTED, PROPOSED as RAW, CORRECTED
    accepted = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == VOICE_ACCEPTED,
        Audit.event['request_id'].as_string() == source.id))
    proposal = accepted and session.scalar(select(Audit).where(
        Audit.event['kind'].as_string().in_([RAW, CORRECTED]),
        Audit.event['profile'].as_string() == source.profile,
        Audit.event['proposal_id'].as_string() == accepted.event['proposal_id']))
    original = proposal and session.get(TelegramInbox, proposal.event['voice_inbox_id'])
    if not original or original.profile != source.profile or original.intent['kind'] != 'voice_request':
        raise Denied('mixed_review_source_invalid')
    return original.created_at


def schedule_pin(session):
    from .attention_schedule import current
    schedule = current(session)
    return {'configured': schedule.get('configured', False), 'timezone': schedule.get('timezone', 'Europe/Moscow')}


def items_for(value, received, schedule, now):
    from .mixed_inbox import request_markers
    from .personal_inbox import parse, due_at, project_hint
    positions = request_markers(value)
    if len(positions) < 2 or len(positions) > 8:
        return []
    if value[:positions[0]].strip():
        positions.insert(0, 0)
    else:
        positions[0] = 0
    if len(positions) > 8:
        return []
    items = []
    for start, end in zip(positions, positions[1:] + [len(value)]):
        span = value[start:end]
        intent = parse(span)
        document, project = None, None
        if intent and intent.get('action') == 'create' and 1 <= len(intent['title'].strip()) <= 500:
            due = None
            supported = True
            if intent['category'] == 'reminder':
                # Do not turn following sentences/corrections into a scheduled title.
                supported = (schedule['configured'] and not re.search(r'[.!?;\n]|\b(?:не|на переноси|если|пятниц\w*|суббот\w*)\b',
                    intent['title'].rstrip('.!?'), re.I))
                if supported:
                    try:
                        due = due_at(intent, received, schedule['timezone'], now)
                    except (ValueError, KeyError):
                        supported = False
            if supported:
                document = {'category': intent['category'], 'title': intent['title'].strip(),
                            'status': intent.get('status', 'active'), 'due_at': due}
                project = project_hint(document['title'])
        items.append({'start': start, 'end': end, 'document': document, 'project_id': project})
    return items


def issue_locked(bridge, session, source, value, *, operation_id=None):
    from .personal_inbox import LABELS
    from .project_inbox import PROJECTS
    control = session.get(Control, 1)
    if control.halted or control.recovery:
        return False
    schedule = schedule_pin(session)
    received, now = source_time(session, source), bridge.store.now(session)
    items = items_for(value, received, schedule, now)
    if not items or not any(item['document'] for item in items):
        return False
    operation_id = operation_id or source.id
    proposal_id = str(uuid5(NAMESPACE_URL, 'acc:mixed-review:' + source.id + ':' + operation_id))
    lines = ['Выделены пункты — проверьте каждый. Пока ничего отдельно не сохранено.',
             'Кнопка сохранит только выбранный пункт; напоминание запланирует в Telegram.',
             'Встречи в Google здесь не создаются. Проверьте отрицания, имена, даты и время.']
    for i, item in enumerate(items, 1):
        doc = item['document']
        lines += [f'\n{i}. ' + (LABELS[doc['category']] if doc else 'Нужно уточнить'), value[item['start']:item['end']]]
        if doc:
            lines.append('Раздел: ' + dict(PROJECTS).get(item['project_id'], 'Не распределён') +
                         ('; напомню: ' + doc['due_at'] if doc['due_at'] else '; без срока.'))
    lines += [f'\nВесь исходный текст: /request {source.id.rsplit(":", 1)[1]}',
              'Карточка действует 10 минут; затем нажмите «Обновить разбор». '
              'Если пункт неверный, не сохраняйте его — пришлите исправленный пункт отдельным сообщением.']
    text = '\n'.join(lines)
    markup = keyboard(proposal_id, items)
    body = {'chat_id': bridge.owner, 'text': text, 'reply_markup': markup}
    if len(text) > 3800 or len(canonical(body).encode()) > 8192:
        return False
    delivery = bridge.enqueue(session, operation_id + ':reply', text, markup)
    bridge.store.audit(session, PROPOSED, 'owner', profile=bridge.profile, proposal_id=proposal_id,
        source_id=source.id, source_fingerprint=source.fingerprint, source_hash=digest(value),
        received_at=received.isoformat(), schedule=schedule, items=items, items_hash=digest(items),
        epoch=control.epoch, expires_at=(now + timedelta(minutes=10)).isoformat(), delivery_id=delivery)
    return True


def proposal(session, profile, proposal_id):
    event = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == PROPOSED,
        Audit.event['profile'].as_string() == profile, Audit.event['proposal_id'].as_string() == proposal_id))
    if not event or event.event['items_hash'] != digest(event.event['items']):
        raise Denied('mixed_review_proposal_invalid')
    return event.event


def source_text(session, profile, event, *, active=False):
    from .telegram_requests import captured_text
    source = session.get(TelegramInbox, event['source_id'])
    if (not source or source.profile != profile or source.fingerprint != event['source_fingerprint']
            or source.intent['kind'] not in {'capture', 'voice_confirm'}):
        raise Denied('mixed_review_source_invalid')
    value = captured_text(session, source, states=frozenset({'NEEDS_PLANNING'} if active else {'NEEDS_PLANNING', 'ARCHIVED'}))
    if digest(value) != event['source_hash']:
        raise Denied('mixed_review_source_invalid')
    return source, value


def accepted_text(session, row):
    accepted = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == ACCEPTED,
        Audit.event['actor'].as_string() == 'owner', Audit.event['profile'].as_string() == row.profile,
        Audit.event['request_id'].as_string() == row.id,
        Audit.event['request_fingerprint'].as_string() == row.fingerprint))
    if not accepted:
        raise Denied('mixed_review_acceptance_invalid')
    event = proposal(session, row.profile, row.intent['proposal_id'])
    _, value = source_text(session, row.profile, event)
    if type(row.intent.get('item')) is not int or not 1 <= row.intent['item'] <= len(event['items']):
        raise Denied('mixed_review_acceptance_invalid')
    item = event['items'][row.intent['item'] - 1]
    text = value[item['start']:item['end']]
    if (not item['document'] or accepted.event['text'] != text
            or accepted.event['text_hash'] != digest(text) or accepted.event['item'] != row.intent['item']
            or accepted.event['proposal_id'] != row.intent['proposal_id']
            or accepted.event['source_id'] != event['source_id']
            or accepted.event['span_hash'] != digest({'start': item['start'], 'end': item['end']})):
        raise Denied('mixed_review_acceptance_invalid')
    return text


def decide(bridge, iid, intent):
    from .assistant_policy import assistant_only
    from .personal_inbox import handle_locked, records
    with bridge.store.transaction() as session:
        bridge.guard()
        bridge.store.check_audit(session)
        row = session.get(TelegramInbox, iid)
        if row.state in {'DONE', 'NEEDS_PLANNING', 'ARCHIVED'}:
            return
        if not assistant_only() or row.state != 'RECEIVED' or row.intent != intent:
            raise Denied('mixed_review_not_pending')
        event = proposal(session, bridge.profile, intent['proposal_id'])
        delivery = session.get(TelegramDelivery, event['delivery_id'])
        observed = delivery and session.scalar(select(Audit).where(
            Audit.event['kind'].as_string() == 'telegram_delivery_observed',
            Audit.event['delivery_id'].as_string() == delivery.id,
            Audit.event['message_id'].as_integer() == intent['message_id'],
            Audit.event['state'].as_string() == 'SENT'))
        if (not delivery or delivery.profile != bridge.profile or delivery.state != 'SENT' or not observed
                or delivery.message_id != intent['message_id']
                or canonical(delivery.body.get('reply_markup')) != canonical(keyboard(intent['proposal_id'], event['items']))):
            raise Denied('mixed_review_card_invalid')
        control = session.get(Control, 1)
        if intent['kind'] == 'mixed_refresh':
            if control.halted or control.recovery or event['revision'] != bridge.store.settings.source_revision:
                bridge.finish(session, iid, 'Приём остановлен или версия изменилась. Пункты не сохранены.')
                return
            source, value = source_text(session, bridge.profile, event, active=True)
            if issue_locked(bridge, session, source, value, operation_id=iid):
                row.state = 'DONE'
            else:
                bridge.finish(session, iid, 'Пункты требуют уточнения; исходный текст остаётся во входящих. Ничего отдельно не сохранено.')
            return
        if not 1 <= intent['item'] <= len(event['items']):
            raise Denied('mixed_review_item_invalid')
        selected = event['items'][intent['item'] - 1]
        span_hash = digest({'start': selected['start'], 'end': selected['end']})
        previous = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == ACCEPTED,
            Audit.event['profile'].as_string() == bridge.profile,
            Audit.event['source_id'].as_string() == event['source_id'],
            Audit.event['span_hash'].as_string() == span_hash))
        if previous:
            bridge.finish(session, iid, 'Этот пункт уже сохранён: №' + previous.event['request_id'].rsplit(':', 1)[1] + '. Дубль не создан.')
            return
        now = bridge.store.now(session)
        latest = session.scalar(select(Audit.event['proposal_id'].as_string()).where(
            Audit.event['kind'].as_string() == PROPOSED, Audit.event['profile'].as_string() == bridge.profile,
            Audit.event['source_id'].as_string() == event['source_id']).order_by(Audit.sequence.desc()).limit(1))
        if (event['revision'] != bridge.store.settings.source_revision or control.halted or control.recovery
                or control.epoch != event['epoch'] or now >= datetime.fromisoformat(event['expires_at'])
                or schedule_pin(session) != event['schedule'] or latest != intent['proposal_id']):
            bridge.finish(session, iid, 'Карточка устарела или приём остановлен. Пункт не сохранён; исходный текст остаётся во входящих.')
            return
        source, value = source_text(session, bridge.profile, event, active=True)
        items = items_for(value, source_time(session, source), event['schedule'], now)
        if items != event['items'] or not 1 <= intent['item'] <= len(items) or not items[intent['item'] - 1]['document']:
            bridge.finish(session, iid, 'Данные пункта требуют уточнения. Запись не создана; исходный текст сохранён.')
            return
        item = items[intent['item'] - 1]
        text = value[item['start']:item['end']]
        row.state = 'NEEDS_PLANNING'
        bridge.store.audit(session, ACCEPTED, 'owner', profile=bridge.profile,
            proposal_id=intent['proposal_id'], item=intent['item'], request_id=iid,
            request_fingerprint=row.fingerprint, text=text, text_hash=digest(text),
            source_id=source.id, span_hash=span_hash)
        if not handle_locked(bridge, session, iid, text, received_at=source_time(session, source)):
            raise Denied('mixed_review_personal_not_created')
        # The stored record must match exactly what the owner saw before clicking.
        saved = records(bridge, session, [iid]).get(iid)
        if not saved or {k: saved[k] for k in item['document']} != item['document']:
            raise Denied('mixed_review_personal_mismatch')
