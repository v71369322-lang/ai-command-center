"""Create the existing fixed waiting task, never an execution or spending grant."""
from datetime import datetime, timedelta

from sqlalchemy import select

from .coding.first_experiment import create_task
from .models import Audit, Control, TelegramInbox
from .store import Denied, digest
from .telegram_experiment import task_record

INTENT = {'kind': 'prepare_experiment'}


def bind(bridge, session):
    task, _ = task_record(bridge, session)
    if task is None:
        control = session.get(Control, 1)
        if control.halted or control.recovery:
            raise Denied('control_blocked')
        return None
    bridge.store.check_task_revision(session, task)
    return {'task_id': task.id, 'payload_hash': task.payload_hash}


def accepted(bridge, session, inbox_id, task):
    bridge.guard()
    bridge.store.check_audit(session)
    bridge.store.check_task_revision(session, task)
    row = session.get(TelegramInbox, inbox_id)
    received = session.scalar(select(Audit).where(
        Audit.event['kind'].as_string() == 'telegram_update_received',
        Audit.event['actor'].as_string() == 'owner', Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['update_id'].as_string() == inbox_id.removeprefix(bridge.profile + ':'),
        Audit.event['intent_hash'].as_string() == digest(INTENT),
        Audit.event['revision'].as_string() == bridge.store.settings.source_revision)
        .order_by(Audit.sequence).limit(1))
    fixed, _ = task_record(bridge, session)
    if (not row or row.profile != bridge.profile or row.intent != INTENT or row.fingerprint != digest(INTENT)
            or row.state not in {'RECEIVED', 'DONE'} or not received or fixed is None or fixed.id != task.id
            or 'experiment_prepare_binding' not in received.event):
        raise Denied('experiment_prepare_receipt_invalid')
    if row.state == 'DONE':
        if row.task_id != task.id:
            raise Denied('experiment_prepare_binding_changed')
        return
    if row.task_id is not None:
        raise Denied('experiment_prepare_receipt_invalid')
    control = session.get(Control, 1)
    try:
        issued = datetime.fromisoformat(received.event['time'])
        now = bridge.store.now(session)
        if (issued.tzinfo is None or not issued <= now < issued + timedelta(seconds=120)
                or type(received.event.get('admission_epoch')) is not int
                or received.event['admission_epoch'] != control.epoch):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise Denied('experiment_prepare_admission_expired') from None
    binding = received.event['experiment_prepare_binding']
    if binding is None:
        if (control.halted or control.recovery or task.state != 'WAITING_APPROVAL'
                or task.created_at < issued):
            raise Denied('experiment_prepare_admission_changed')
    elif (not isinstance(binding, dict) or set(binding) != {'task_id', 'payload_hash'}
            or binding != {'task_id': task.id, 'payload_hash': task.payload_hash}):
        raise Denied('experiment_prepare_binding_changed')
    row.task_id = task.id
    bridge.store.audit(session, 'telegram_experiment_prepared', 'owner', task.id,
                       profile=bridge.profile, inbox_id=inbox_id, payload_hash=task.payload_hash)
    title = ('Первый AI-эксперимент подготовлен; ожидает отдельного разрешения.' if binding is None
             else 'Первый AI-эксперимент уже существует. Новая задача и повторный запуск не создаются.')
    bridge.finish(session, inbox_id, title + f'\nЗадача: {task.id}.\n'
                  'Фиксированная задача: сумма положительных чисел в calculator.py, до двух AI-вызовов. '
                  'Эта команда не разрешает расходы, не включает AI и не выполняет обычные запросы или CRM.\n'
                  'Состояние: /experiment. Условия запуска: /readiness. '
                  'Уведомления: /watch_experiment. Отмена: /cancel_experiment.')


def apply(bridge, inbox_id):
    return create_task(bridge.store, 'owner',
                       _scope_installer=lambda session, task: accepted(bridge, session, inbox_id, task))
