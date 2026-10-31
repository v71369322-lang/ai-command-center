"""Read-only owner attention summary; no scheduling, execution or provider calls."""
from sqlalchemy import func, select

from .models import Control, Task, TelegramInbox
from .project_inbox import PROJECTS, history
from .store import Denied


def build(store, session):
    control = session.get(Control, 1)
    task_counts = dict(session.execute(
        select(Task.state, func.count()).group_by(Task.state)).all())
    assignments, _ = history(session)
    rows = session.execute(select(TelegramInbox.id).where(
        TelegramInbox.state == 'NEEDS_PLANNING').limit(1001)).all()
    if len(rows) > 1000:
        raise Denied('attention_request_capacity')
    project_counts = dict.fromkeys(['unassigned', *[key for key, _ in PROJECTS]], 0)
    for row in rows:
        assigned = assignments.get(row.id)
        project_counts[assigned['project_id'] if assigned and assigned['project_id'] else 'unassigned'] += 1

    items = []
    if control.recovery:
        items.append({'code': 'CONTROL_RECOVERY', 'level': 'critical',
                      'count': 1, 'label': 'Требуется сверка восстановления'})
    elif control.halted:
        items.append({'code': 'CONTROL_HALTED', 'level': 'warning',
                      'count': 1, 'label': 'Новые запуски остановлены'})
    for state, code, level, label in (
        ('RECONCILING', 'TASK_RECONCILING', 'critical', 'Исполнения требуют сверки'),
        ('CANCEL_REQUESTED', 'TASK_CANCELLING', 'warning', 'Отмена ещё не подтверждена'),
        ('WAITING_APPROVAL', 'TASK_APPROVAL', 'warning', 'Задачи ожидают решения владельца'),
        ('FAILED', 'TASK_FAILED', 'info', 'Завершившиеся ошибкой задачи'),
    ):
        count = int(task_counts.get(state, 0))
        if count:
            items.append({'code': code, 'level': level, 'count': count, 'label': label})
    if project_counts['unassigned']:
        items.append({'code': 'REQUEST_UNASSIGNED', 'level': 'warning',
                      'count': project_counts['unassigned'],
                      'label': 'Запросы ещё не распределены по проектам'})
    if rows:
        items.append({'code': 'REQUEST_NEEDS_PLANNING', 'level': 'info',
                      'count': len(rows), 'label': 'Запросы ожидают планирования'})
    return {'schema': 1, 'items': items, 'task_counts': task_counts,
            'project_counts': project_counts, 'total_pending_requests': len(rows),
            'task_admission_halted': bool(control.halted), 'recovery': bool(control.recovery),
            'ai_planning_connected': False, 'reminders_connected': False,
            'execution_started': False}


def summary(store, role):
    if role != 'owner':
        raise Denied('owner_required')
    with store.transaction() as session:
        store.check_audit(session)
        result = build(store, session)
        from .attention_schedule import current
        result['reminders_connected'] = bool(current(session).get('enabled'))
        return result
