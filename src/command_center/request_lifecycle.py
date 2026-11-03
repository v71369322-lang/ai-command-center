"""Reversible owner archive for unplanned Telegram requests; no deletion or execution."""
import re

from sqlalchemy import select

from .models import Audit, Task, TelegramInbox
from .request_plan_store import EVENT as PLAN_EVENT
from .store import Denied, digest
from .telegram_requests import captured_text

EVENT = 'saved_request_lifecycle_changed'
STATES = {'ARCHIVED', 'NEEDS_PLANNING'}
MAX_CHANGES = 2000


def _history(session):
    rows = session.scalars(select(Audit).where(
        Audit.event['kind'].as_string() == EVENT).order_by(Audit.sequence).limit(MAX_CHANGES + 1)).all()
    if len(rows) > MAX_CHANGES:
        raise Denied('request_lifecycle_history_limit')
    latest, operations = {}, set()
    for row in rows:
        event = row.event
        request_id, operation_id = event.get('request_id'), event.get('operation_id')
        previous = latest.get(request_id)
        expected = (previous['version'] if previous else 0) + 1
        source = {'request_id': request_id, 'request_fingerprint': event.get('request_fingerprint'),
                  'state': event.get('state'), 'version': event.get('version')}
        if (event.get('actor') != 'owner' or not isinstance(request_id, str)
                or not re.fullmatch(r'[a-f0-9]{64}:(0|[1-9][0-9]{0,15})', request_id)
                or event.get('state') not in STATES or type(event.get('version')) is not int
                or event['version'] != expected or not isinstance(operation_id, str)
                or not re.fullmatch(r'[a-f0-9]{64}:(0|[1-9][0-9]{0,15})', operation_id)
                or operation_id in operations or event.get('input_hash') != digest(source)
                or not re.fullmatch(r'[a-f0-9]{64}', str(event.get('request_fingerprint')))):
            raise Denied('request_lifecycle_history_invalid')
        latest[request_id], operations = event, operations | {operation_id}
    return latest


def apply(bridge, session, iid, intent):
    target_id = bridge.profile + ':' + intent['number']
    desired = 'ARCHIVED' if intent['kind'] == 'archive_request' else 'NEEDS_PLANNING'
    bridge.guard()
    bridge.store.check_audit(session)
    command = session.get(TelegramInbox, iid)
    if command.state == 'DONE':
        return
    if command.state != 'RECEIVED' or command.intent != intent or command.fingerprint != digest(intent):
        raise Denied('request_lifecycle_command_invalid')
    target = session.get(TelegramInbox, target_id)
    if target is None or target.profile != bridge.profile or target.task_id is not None:
        return bridge.finish(session, iid, 'Запрос не найден в очереди этого Telegram-подключения.')
    latest = _history(session).get(target_id)
    current = latest['state'] if latest else 'NEEDS_PLANNING'
    if target.state != current:
        raise Denied('request_lifecycle_state_invalid')
    captured_text(session, target, states=frozenset(STATES))
    if current == desired:
        action = 'уже архивирован' if desired == 'ARCHIVED' else 'уже возвращён в очередь'
        return bridge.finish(session, iid, f'Запрос №{intent["number"]} {action}.')
    if session.scalar(select(Task.id).where(
            Task.payload['kind'].as_string() == 'saved_request_plan',
            Task.payload['planning']['request_id'].as_string() == target_id).limit(1)):
        raise Denied('request_lifecycle_task_exists')
    if session.scalar(select(Audit.sequence).where(
            Audit.event['kind'].as_string() == PLAN_EVENT,
            Audit.event['request_id'].as_string() == target_id).limit(1)):
        raise Denied('request_lifecycle_plan_exists')
    version = (latest['version'] if latest else 0) + 1
    source = {'request_id': target_id, 'request_fingerprint': target.fingerprint,
              'state': desired, 'version': version}
    bridge.store.audit(session, EVENT, 'owner', operation_id=iid, **source, input_hash=digest(source))
    target.state = desired
    if desired == 'ARCHIVED':
        text = (f'Запрос №{intent["number"]} архивирован. Он удалён из очереди планирования, '
                f'но сохранён в журнале. Вернуть: /restore_request {intent["number"]}.')
    else:
        text = (f'Запрос №{intent["number"]} возвращён в очередь планирования. '
                f'Открыть: /request {intent["number"]}.')
    bridge.finish(session, iid, text)
