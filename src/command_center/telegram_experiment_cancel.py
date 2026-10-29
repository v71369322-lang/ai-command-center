"""Receipt-bound shortcut to the existing locked F1 cancellation action."""
from datetime import datetime, timedelta

from sqlalchemy import select

from .models import Audit, TelegramInbox
from .store import Denied, TERMINAL, digest
from .telegram_experiment import task_record

INTENT = {'kind': 'cancel_experiment'}


def bind(bridge, session):
    task, _ = task_record(bridge, session)
    if task is None:
        return None
    bridge.store.check_task_revision(session, task)
    return {'task_id': task.id, 'payload_hash': task.payload_hash}


def apply(bridge, inbox_id):
    with bridge.store.transaction() as session:
        bridge.guard()
        bridge.store.check_audit(session)
        row = session.get(TelegramInbox, inbox_id)
        if row and row.state == 'DONE':
            return
        received = session.scalar(select(Audit).where(
            Audit.event['kind'].as_string() == 'telegram_update_received',
            Audit.event['actor'].as_string() == 'owner', Audit.event['profile'].as_string() == bridge.profile,
            Audit.event['update_id'].as_string() == inbox_id.removeprefix(bridge.profile + ':'),
            Audit.event['intent_hash'].as_string() == digest(INTENT),
            Audit.event['revision'].as_string() == bridge.store.settings.source_revision)
            .order_by(Audit.sequence).limit(1))
        if (not row or row.profile != bridge.profile or row.state != 'RECEIVED' or row.intent != INTENT
                or row.task_id is not None or row.fingerprint != digest(INTENT) or not received
                or 'experiment_cancel_binding' not in received.event):
            raise Denied('experiment_cancel_receipt_invalid')
        try:
            issued = datetime.fromisoformat(received.event['time'])
            now = bridge.store.now(session)
            if issued.tzinfo is None or not issued <= now < issued + timedelta(seconds=120):
                raise ValueError()
        except (KeyError, ValueError, TypeError):
            raise Denied('experiment_cancel_expired') from None
        binding = received.event['experiment_cancel_binding']
        if binding is None:
            bridge.finish(session, inbox_id, 'При получении команды первый AI-эксперимент ещё не был создан. '
                          'Ничего не отменено; команда не переносится на будущую задачу.')
            return
        if not isinstance(binding, dict) or set(binding) != {'task_id', 'payload_hash'}:
            raise Denied('experiment_cancel_binding_invalid')
        task, _ = task_record(bridge, session)
        if task is None or binding != {'task_id': task.id, 'payload_hash': task.payload_hash}:
            raise Denied('experiment_cancel_binding_changed')
        bridge.store.check_task_revision(session, task)
        if task.state in TERMINAL:
            bridge.finish(session, inbox_id, 'Задача уже завершена или заблокирована. Её результат и учёт не изменены. '
                          'Текущий снимок: /experiment.')
            return
        bridge.store._cancel_locked(session, 'owner', task.id)
        bridge.store.audit(session, 'telegram_experiment_cancel_applied', 'owner', task.id,
                           profile=bridge.profile, inbox_id=inbox_id, payload_hash=task.payload_hash)
        bridge.finish(session, inbox_id, 'Намерение отмены первого AI-эксперимента сохранено. '
                      'Новые действия задачи блокируются; фактическая остановка ещё проверяется. '
                      'Выполненные вызовы, учтённые расходы и спорные резервы сохраняются. '
                      'Отмена не означает возврат денег и не разрешает повтор. Состояние: /experiment.')
