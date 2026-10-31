"""Read-only owner attention summary; no scheduling, execution or provider calls."""
from sqlalchemy import func, select

from .models import Control, Task, TelegramInbox
from .project_inbox import PROJECTS, history
from .store import Denied, digest


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
    for item in items:
        item['urgency'] = {'critical': 'immediate', 'warning': 'soon', 'info': 'normal'}[item['level']]
        item['confidence'] = 'authoritative'
        item['impact'] = 'execution' if item['code'].startswith(('CONTROL_', 'TASK_')) else 'planning'
        item['target'] = ('control-center' if item['code'].startswith('CONTROL_') else
                          'task-results' if item['code'].startswith('TASK_') else
                          'projects-heading')
    highest = next((level for level in ('critical', 'warning', 'info')
                    if any(item['level'] == level for item in items)), None)
    return {'schema': 1, 'items': items, 'task_counts': task_counts,
            'project_counts': project_counts, 'total_pending_requests': len(rows),
            'highest_level': highest, 'attention_hash': digest(items),
            'task_admission_halted': bool(control.halted), 'recovery': bool(control.recovery),
            'ai_planning_connected': False, 'reminders_connected': False,
            'execution_started': False}


def summary(store, role):
    if role != 'owner':
        raise Denied('owner_required')
    with store.transaction() as session:
        store.check_audit(session)
        result = build(store, session)
        from .attention_schedule import activity, current, delivery_health
        schedule = current(session)
        result['reminders_connected'] = bool(schedule.get('enabled'))
        result['reminder_schedule_state'] = ('not_configured' if not schedule['configured'] else
                                             'active' if schedule['enabled'] else 'disabled')
        result['reminder_activity'] = activity(session)
        result['reminder_delivery_health'] = delivery_health(session, store.now(session))
        return result


def telegram_reply(store, session):
    """Format the same bounded owner snapshot used by the web attention center."""
    result = build(store, session)
    from .attention_schedule import current, delivery_health
    schedule = current(session)
    health = delivery_health(session, store.now(session))
    lines = ['Центр внимания AI Commander']
    if result['items']:
        lines.extend(f"{item['count']} · {item['label']}" for item in result['items'])
    else:
        lines.append('Пунктов, требующих внимания, нет.')
    lines.extend((
        '',
        f"Запросов без проекта: {result['project_counts']['unassigned']}.",
        f"Запросов, ожидающих планирования: {result['total_pending_requests']}.",
        ('Напоминания: включены.' if schedule.get('enabled') else
         'Напоминания: расписание настроено, но выключено.' if schedule.get('configured') else
         'Напоминания: расписание ещё не настроено.'),
        ('Доставка напоминаний требует проверки.' if health['action_required'] else
         'Доставка напоминаний: подтверждена.' if health['state'] == 'confirmed' else
         'Доставка напоминаний: ожидает подтверждения.' if health['state'] == 'pending' else
         'Доставка напоминаний: повтор не требовался.' if health['state'] == 'suppressed' else
         'Доставка напоминаний ещё не выполнялась.'),
        '',
        'Просмотр ничего не меняет: выполнение не запускалось, остановка не снималась.',
    ))
    return '\n'.join(lines)
