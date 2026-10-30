"""Owner notification consent and delivery reuse the existing durable audit/outbox."""
import re
from uuid import UUID

from sqlalchemy import select

from .coding.first_experiment import task_payload
from .models import Audit, TelegramDelivery, TelegramInbox
from .store import Denied, digest
from .telegram_experiment import snapshot
from .telegram_experiment_scope import experiment_id, key as scope_key

WATCH = 'telegram_experiment_watch_changed'
NOTICE = 'telegram_experiment_notice_queued'
TERMINAL = {'SUCCEEDED', 'FAILED', 'CANCELLED', 'RECONCILING', 'SECURITY_BLOCKED'}


def receipt(bridge, session, inbox_id, enabled, revision):
    intent = {'kind': scope_key(bridge, 'watch_experiment' if enabled else 'unwatch_experiment')}
    row = session.get(TelegramInbox, inbox_id)
    received = session.scalar(select(Audit).where(
        Audit.event['kind'].as_string() == 'telegram_update_received',
        Audit.event['actor'].as_string() == 'owner', Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['revision'].as_string() == revision,
        Audit.event['update_id'].as_string() == inbox_id.removeprefix(bridge.profile + ':'),
        Audit.event['intent_hash'].as_string() == digest(intent)).order_by(Audit.sequence).limit(1))
    if (not row or row.profile != bridge.profile or row.intent != intent or row.fingerprint != digest(intent)
            or row.task_id is not None or row.state not in {'RECEIVED', 'DONE'} or not received):
        raise Denied('experiment_watch_receipt_invalid')
    return row, received


def current(bridge, session):
    anchor = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == scope_key(bridge, WATCH),
        Audit.event['actor'].as_string() == 'owner', Audit.event['profile'].as_string() == bridge.profile)
        .order_by(Audit.sequence.desc()).limit(1))
    if not anchor:
        return None
    event = anchor.event
    if (type(event.get('enabled')) is not bool
            or not re.fullmatch('[a-f0-9]{64}', str(event.get('payload_hash')))
            or not isinstance(event.get('inbox_id'), str) or not isinstance(event.get('task_id'), str)):
        raise Denied('experiment_watch_binding_invalid')
    try:
        if str(UUID(event['task_id'])) != event['task_id']:
            raise ValueError()
    except ValueError:
        raise Denied('experiment_watch_binding_invalid') from None
    row, received = receipt(bridge, session, event['inbox_id'], event['enabled'], event['revision'])
    if row.state != 'DONE' or received.sequence >= anchor.sequence:
        raise Denied('experiment_watch_receipt_invalid')
    return anchor


def notice_key(task_id, fingerprint):
    return f'experiment:{task_id}:{fingerprint}'


def suppress_pending(bridge, session, task_id):
    # Revoke only known, unsent experiment notices. Replies and uncertain sends
    # retain their own durable records and are never converted into a retry.
    anchors = session.scalars(select(Audit).where(Audit.event['kind'].as_string() == scope_key(bridge, NOTICE),
        Audit.event['profile'].as_string() == bridge.profile, Audit.event['task_id'].as_string() == task_id)).all()
    for anchor in anchors:
        event = anchor.event
        if not re.fullmatch('[a-f0-9]{64}', str(event.get('fingerprint'))):
            raise Denied('experiment_notice_binding_invalid')
        expected = digest({'profile': bridge.profile, 'event': notice_key(task_id, event['fingerprint'])})
        if expected != event.get('delivery_id'):
            raise Denied('experiment_notice_binding_invalid')
        delivery = session.get(TelegramDelivery, expected)
        if delivery and delivery.profile == bridge.profile and delivery.state == 'NEW':
            delivery.state = 'CANCELLED'
            bridge.store.audit(session, 'telegram_experiment_notice_cancelled', 'owner', task_id,
                               profile=bridge.profile, delivery_id=expected)


def change(bridge, session, inbox_id, enabled):
    if type(enabled) is not bool:
        raise Denied('experiment_watch_binding_invalid')
    revision = bridge.store.settings.source_revision
    row, _ = receipt(bridge, session, inbox_id, enabled, revision)
    if row.state != 'RECEIVED':
        raise Denied('experiment_watch_not_pending')
    previous = current(bridge, session)
    if not enabled:
        if previous:
            task_id = previous.event['task_id']
            suppress_pending(bridge, session, task_id)
            bridge.store.audit(session, scope_key(bridge, WATCH), 'owner', task_id, profile=bridge.profile,
                               inbox_id=inbox_id, enabled=False, payload_hash=digest(task_payload(experiment_id(bridge))))
        return 'Будущие уведомления первого AI-эксперимента отключены. Текущий снимок: /experiment.'
    task, _ = snapshot(bridge, session, include_time=False)
    if task is None:
        return 'Первый AI-эксперимент ещё не создан. Подписка не включена. Условия: /readiness.'
    bridge.store.check_task_revision(session, task)
    if (not previous or not previous.event['enabled'] or previous.event['task_id'] != task.id
            or previous.event['revision'] != revision):
        bridge.store.audit(session, scope_key(bridge, WATCH), 'owner', task.id, profile=bridge.profile,
                           inbox_id=inbox_id, enabled=True, payload_hash=task.payload_hash)
    return ('Уведомления первого AI-эксперимента включены для этого чата. '
            'Уже отправленные, отменённые и неопределённые отправки не повторяются.\n'
            'Текущий снимок: /experiment. Отключить: /unwatch_experiment.\n'
            'Подписка не запускает задачу и не выдаёт разрешение на расходы.')


def collect(bridge, session):
    watch = current(bridge, session)
    if (not watch or not watch.event['enabled']
            or watch.event['revision'] != bridge.store.settings.source_revision):
        return
    task, body = snapshot(bridge, session, include_time=False)
    if task is None or task.id != watch.event['task_id'] or task.payload_hash != watch.event['payload_hash']:
        raise Denied('experiment_watch_task_changed')
    bridge.store.check_task_revision(session, task)
    if task.state not in TERMINAL:
        return
    fingerprint = digest({'revision': bridge.store.settings.source_revision, 'body': body})
    key = notice_key(task.id, fingerprint)
    expected = digest({'profile': bridge.profile, 'event': key})
    if session.get(TelegramDelivery, expected):
        return
    text = ('Уведомление первого AI-эксперимента\nСнимок UTC: '
            + bridge.store.now(session).isoformat() + '\n\n' + body + '\n\nПодробнее: /experiment.')
    delivery_id = bridge.enqueue(session, key, text)
    bridge.store.audit(session, scope_key(bridge, NOTICE), 'system', task.id, profile=bridge.profile,
                       delivery_id=delivery_id, fingerprint=fingerprint, watch_sequence=watch.sequence)
