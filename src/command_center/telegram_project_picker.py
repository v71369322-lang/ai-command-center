"""Issued project buttons label saved requests; they never grant execution."""
import re

from sqlalchemy import select

from .models import Audit, TelegramDelivery, TelegramInbox
from .project_inbox import IDS, PROJECTS, history
from .store import Denied, canonical, digest
from .telegram_requests import captured_text

EVENT = 'telegram_project_picker_issued'


def parse_callback(value):
    match = re.fullmatch(r'pj:(0|[1-9][0-9]{0,15}):(0|[1-9][0-9]{0,3}):([a-z-]+)', value) if isinstance(value, str) else None
    if (not match or len(value.encode()) > 64 or int(match[1]) >= 2**53
            or int(match[2]) > 1000 or match[3] not in IDS | {'none'}):
        raise Denied('telegram_project_picker_invalid')
    return {'kind': 'assign', 'number': match[1], 'version': int(match[2]),
            'project_id': None if match[3] == 'none' else match[3], 'picker_callback': value}


def keyboard(number, version):
    return {'inline_keyboard': [[{'text': label, 'callback_data': f'pj:{number}:{version}:{pid}'}]
                               for pid, label in (*PROJECTS, ('none', 'Не распределён'))]}


def allowed_markup(value):
    try:
        intent = parse_callback(value['inline_keyboard'][0][0]['callback_data'])
        return canonical(value) == canonical(keyboard(intent['number'], intent['version']))
    except (Denied, KeyError, IndexError, TypeError):
        return False


def saved_version(bridge, session, number):
    row = session.get(TelegramInbox, bridge.profile + ':' + number)
    if row is None or row.state != 'NEEDS_PLANNING':
        return None
    bridge.check_text(captured_text(session, row))
    latest, _ = history(session)
    assignment = latest.get(row.id)
    if assignment and assignment['request_fingerprint'] != row.fingerprint:
        raise Denied('project_request_binding_changed')
    return assignment['version'] if assignment else 0


def issue(bridge, session, delivery_id, number, version):
    row = session.get(TelegramInbox, bridge.profile + ':' + number)
    delivery = session.get(TelegramDelivery, delivery_id)
    if (saved_version(bridge, session, number) != version or delivery is None
            or delivery.profile != bridge.profile or delivery.body.get('chat_id') != bridge.owner
            or canonical(delivery.body.get('reply_markup')) != canonical(keyboard(number, version))):
        raise Denied('telegram_project_picker_issue_binding_changed')
    bridge.store.audit(session, EVENT, 'owner', profile=bridge.profile, request_id=row.id,
                       request_fingerprint=row.fingerprint, version=version, delivery_id=delivery_id,
                       request_hash=digest(delivery.body))


def verify(bridge, session, intent):
    """Require this exact profile/request/version/card to have been really sent."""
    rows = session.execute(select(TelegramDelivery).where(TelegramDelivery.profile == bridge.profile,
        TelegramDelivery.state == 'SENT', TelegramDelivery.message_id == intent['message_id']).limit(2)).scalars().all()
    row = session.get(TelegramInbox, bridge.profile + ':' + intent['number'])
    if len(rows) != 1 or row is None:
        raise Denied('telegram_project_picker_not_issued')
    delivery = rows[0]
    body = delivery.body
    bridge.check_text(captured_text(session, row))
    if (body.get('chat_id') != bridge.owner
            or canonical(body.get('reply_markup')) != canonical(keyboard(intent['number'], intent['version']))):
        raise Denied('telegram_project_picker_not_issued')
    expected = {'profile': bridge.profile, 'request_id': row.id, 'request_fingerprint': row.fingerprint,
                'delivery_id': delivery.id, 'request_hash': digest(body),
                'revision': bridge.store.settings.source_revision, 'actor': 'owner'}
    anchored = session.execute(select(Audit).where(Audit.event['kind'].as_string() == EVENT,
        Audit.event['version'].as_integer() == intent['version'],
        *[Audit.event[key].as_string() == value for key, value in expected.items()])).first()
    queued = session.execute(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_delivery_queued',
        Audit.event['delivery_id'].as_string() == delivery.id,
        Audit.event['request_hash'].as_string() == digest(body))).first()
    observed = session.execute(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_delivery_observed',
        Audit.event['delivery_id'].as_string() == delivery.id,
        Audit.event['message_id'].as_integer() == intent['message_id'], Audit.event['state'].as_string() == 'SENT')).first()
    if not anchored or not queued or not observed:
        raise Denied('telegram_project_picker_not_issued')
