"""Owner preparation of one exact saved-request planning task; no provider I/O."""

from .models import Control, TelegramInbox
from .planning_task import create_task
from .project_inbox import PROJECTS
from .request_planning import context
from .store import Denied, digest


def prepare(bridge, iid, intent):
    """Create only the F1 waiting task, then return its immutable scope."""
    bridge.guard()
    rid = bridge.profile + ':' + intent['number']
    with bridge.store.transaction() as session:
        bridge.store.check_audit(session)
        command = session.get(TelegramInbox, iid)
        if command.state == 'DONE':
            return
        if (command.state != 'RECEIVED' or command.intent != intent
                or command.fingerprint != digest(intent)):
            raise Denied('telegram_plan_preparation_command_invalid')
        request = session.get(TelegramInbox, rid)
        if request is None or request.profile != bridge.profile:
            return bridge.finish(session, iid,
                'Запрос не найден в этом Telegram-подключении. Задача не создана.')
        control = session.get(Control, 1)
        if control.halted or control.recovery:
            return bridge.finish(session, iid,
                'Задача планирования не создана: новые запуски остановлены. '
                'Сначала снимите обычную остановку через /resume, затем повторите команду новым сообщением. '
                'AI и платные вызовы не выполнялись.')

    snapshot = context(bridge.store, 'owner', rid)
    task = create_task(bridge.store, 'owner', snapshot)
    project = dict(PROJECTS).get(snapshot.project_id, 'Не распределён')
    with bridge.store.transaction() as session:
        bridge.store.check_audit(session)
        command = session.get(TelegramInbox, iid)
        if command.state == 'DONE':
            return
        if (command.state != 'RECEIVED' or command.intent != intent
                or command.fingerprint != digest(intent)):
            raise Denied('telegram_plan_preparation_command_invalid')
        command.task_id = task['id']
        bridge.finish(session, iid,
            f'Задача планирования запроса №{intent["number"]} подготовлена.\n'
            f'Проект: {project}.\nЗадача: {task["id"]}. Версия: {task["version"]}.\n'
            f'Состояние: {task["state"]}.\n'
            'Текст запроса, проект, версия назначения, эпоха управления и source revision закреплены. '
            'AI ещё не вызывался; разрешение на расходы и выполнение не выдавалось. '
            f'Черновик после отдельного AI-разрешения: /plan {intent["number"]}.')
