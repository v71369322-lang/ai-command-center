"""One fixed owner experiment snapshot; no Gateway/client or credential construction."""
from decimal import Decimal
import re

from sqlalchemy import select

from .coding.first_experiment import CAP, EXPERIMENT_ID, REQUEST_KEY, task_payload
from .coding.gateway import Gateway, UNRESOLVED_ACTION_STATES
from .coding.financial_types import NANO_RUB
from .coding.spec import BASE_SHA, branch_name
from .models import Audit, ExternalAction, ExternalGrant, Task
from .store import Denied, digest


STATES = {
    'WAITING_APPROVAL': 'Ожидает отдельного разрешения. Запуск этой командой не выполняется.',
    'READY': 'Ожидает исполнителя.',
    'RUNNING': 'Выполняется.',
    'VERIFYING': 'Результат проверяется.',
    'CANCEL_REQUESTED': 'Запрошена отмена; остановка ещё не подтверждена.',
    'CANCELLED': 'В записи задачи: отменена.',
    'RECONCILING': 'Результат неопределён; нужна сверка. Повторный запуск не разрешён.',
    'SECURITY_BLOCKED': 'Выполнение заблокировано проверкой безопасности.',
    'FAILED': 'Эксперимент не завершился успешно.',
}


def rub(value):
    return format(Decimal(value) / NANO_RUB, '.9f').rstrip('0').rstrip('.') + ' ₽'


def reply(bridge, session):
    task = session.scalar(select(Task).where(Task.request_key == 'owner:' + REQUEST_KEY))
    if task is None:
        return ('Первый AI-эксперимент ещё не создан. Условия: /readiness.\n'
                'Просмотр не создаёт задачу и не разрешает расходы.')
    fixed = task_payload()
    created = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == 'task_created',
        Audit.event['task_id'].as_string() == task.id).order_by(Audit.sequence).limit(1))
    if (task.owner_role != 'owner' or task.payload != fixed or task.payload_hash != digest(fixed)
            or task.payload_hash != digest(task.payload)
            or not created or created.event.get('actor') != 'owner'
            or created.event.get('payload_hash') != task.payload_hash):
        raise Denied('first_experiment_task_integrity')
    if created.event.get('revision') != bridge.store.settings.source_revision:
        return 'Первый AI-эксперимент создан другой версией приложения. Нужна сверка; повтор не выполняется.'
    actions = session.scalars(select(ExternalAction).where(ExternalAction.task_id == task.id)).all()
    Gateway.check_ledger(session, actions)
    grant = session.get(ExternalGrant, task.id)
    mode = None
    if grant:
        doc = grant.document
        if (digest(doc) != grant.digest or doc.get('payload_hash') != task.payload_hash
                or doc.get('revision') != bridge.store.settings.source_revision
                or doc.get('experiment_id') != EXPERIMENT_ID or doc.get('base_sha') != BASE_SHA
                or doc.get('mode') not in {'live', 'http_mock'}
                or type(doc.get('budget')) is not int or not 0 < doc['budget'] <= CAP
                or doc['mode'] == 'live' and doc.get('final_confirmation') is not True
                or not session.scalar(select(Audit).where(
                    Audit.event['kind'].as_string() == 'external_scope_approved',
                    Audit.event['actor'].as_string() == 'owner', Audit.event['task_id'].as_string() == task.id,
                    Audit.event['grant_digest'].as_string() == grant.digest))):
            raise Denied('first_experiment_grant_integrity')
        mode = doc['mode']
    if actions and not grant:
        raise Denied('first_experiment_grant_integrity')
    uncertain = any(a.state in UNRESOLVED_ACTION_STATES for a in actions)
    lines = ['Первый AI-эксперимент', f'Снимок UTC: {bridge.store.now(session).isoformat()}', f'Задача: {task.id}',
             {'live': 'Режим по разрешению: live.', 'http_mock': 'Режим по разрешению: HTTP-моки; настоящего AI нет.'}
             .get(mode, 'Отдельное разрешение AI-вызовов не зафиксировано.'),
             STATES.get(task.state, 'Успех пока не подтверждён; нужна сверка.')]
    if task.state == 'RUNNING' and (task.lease_until is None or task.lease_until <= bridge.store.now(session)):
        lines[-1] = 'Срок полномочий исполнителя истёк; текущее выполнение не подтверждено.'
    lines += [f'Операций OpenAI по журналу: {sum(a.kind == "openai" for a in actions)}.',
              f'Учтённый расход по журналу шлюза: {rub(sum(a.actual for a in actions))}.',
              f'Спорный резерв по журналу: {rub(sum(a.reserved for a in actions))}.',
              f'Потолок первого эксперимента: {rub(CAP)}.']
    if grant:
        lines += ['Лимит задачи по разрешению: ' + rub(doc['budget']) + '.']
    if uncertain:
        lines += ['Внешняя операция не сверена; повтор, списание резерва и успех не подтверждаются этой командой.']
    elif task.state == 'SUCCEEDED':
        data = task.coding_evidence
        anchored = isinstance(data, dict) and session.scalar(select(Audit).where(
            Audit.event['kind'].as_string() == 'coding_complete', Audit.event['actor'].as_string() == 'coding_pipeline',
            Audit.event['task_id'].as_string() == task.id, Audit.event['fence'].as_integer() == task.fence,
            Audit.event['revision'].as_string() == bridge.store.settings.source_revision,
            Audit.event['evidence_hash'].as_string() == digest(data)))
        pr = data.get('pr') if isinstance(data, dict) else None
        if (bridge.confirmed_result(session, task) and anchored and mode and data.get('stage') == 'complete'
                and re.fullmatch('[a-f0-9]{64}', str(data.get('independent_proof')))
                and re.fullmatch('[a-f0-9]{40}', str(data.get('final_sha')))
                and isinstance(pr, dict) and pr.get('task_id') == task.id and pr.get('base_sha') == BASE_SHA
                and pr.get('head_sha') == data['final_sha'] and pr.get('head_branch') == branch_name(task.id, task.fence)):
            if mode == 'http_mock' and pr.get('mode') == 'http_mock' and pr.get('published') is False:
                lines[4] = 'Результат независимо проверен в HTTP-моках; реальный PR не опубликован.'
            elif (mode == 'live' and pr.get('mode') == 'github' and pr.get('published') is True
                    and type(pr.get('remote_number')) is int and pr['remote_number'] > 0
                    and re.fullmatch(r'[A-Za-z0-9_-]+/acc-f2-synthetic-[A-Za-z0-9_-]+', str(doc.get('repository')))
                    and len(doc['repository']) <= 140
                    and pr.get('url') == f'https://github.com/{doc["repository"]}/pull/{pr["remote_number"]}'):
                lines[4] = 'Результат независимо проверен.'
                lines += ['Зафиксирован Draft PR: ' + pr['url']]
            else:
                lines += ['Публикация не подтверждена; нужна сверка.']
    lines += ['Это локальный журнал, не проверка баланса или текущего состояния OpenAI/GitHub.\n'
              'Просмотр не запускает задачу, не выдаёт разрешение и не меняет расходы или резервы.']
    return '\n\n'.join(lines)
