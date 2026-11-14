"""One request-oriented route over the existing plan, proposal and execution states."""
from sqlalchemy import select

from . import code_workspace
from .code_generation import BOUND, PURPOSE, decode
from .coding.gateway import Gateway
from .models import Audit, ExternalAction, Task, TelegramInbox
from .store import Denied, digest
from .telegram_coding_approval import status


def result(bridge, session, parent, event):
    """Readback checks settled provider bytes, original task pins and child linkage."""
    import json
    from .isolated_coding import validate_payload
    try:
        child = session.get(Task, event['execution_task_id'])
        action = session.get(ExternalAction, event['action_id'])
        created = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == 'task_created',
            Audit.event['task_id'].as_string() == parent.id).limit(1))
        if (event['actor'] != 'gateway' or event['revision'] != bridge.store.settings.source_revision
                or event['task_id'] != parent.id or parent.payload.get('kind') != code_workspace.KIND
                or parent.payload_hash != digest(parent.payload) or not created
                or created.event.get('payload_hash') != parent.payload_hash
                or created.event.get('revision') != event['revision']
                or created.event.get('code_workspace_digest') != parent.payload['workspace_digest']
                or not bridge.confirmed_result(session, parent)
                or event['request_id'] != parent.payload['workspace']['context']['request_id']
                or not event['request_id'].startswith(bridge.profile + ':')
                or not child or child.payload_hash != event['execution_payload_hash']
                or digest(child.payload) != child.payload_hash or not action or action.task_id != parent.id
                or action.state != 'COMPLETE' or action.kind != 'openai'
                or child.payload['spec_digest'] != parent.payload['workspace']['spec_digest']):
            raise ValueError()
        Gateway.check_ledger(session, [action])
        validate_payload(child.payload)
        expected = {'purpose': PURPOSE, 'workspace_digest': parent.payload['workspace_digest'],
                    'execution_authorized': False}
        if json.loads(parent.artifact) != expected:
            raise ValueError()
        # Use the immutable grant's reviewed tariff profile even if it has since expired/revoked.
        # This is readback only; current admission still requires fresh configured authority.
        from .code_generation import CONFIG, CodeProfile
        from .models import ExternalGrant
        grant = session.get(ExternalGrant, parent.id)
        profile_event = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == CONFIG,
            Audit.event['profile_digest'].as_string() == grant.document['config_hash']).limit(1)) if grant else None
        if not profile_event or digest(grant.document) != grant.digest:
            raise ValueError()
        profile = CodeProfile.model_validate(profile_event.event['profile'])
        if (digest(profile.model_dump()) != grant.document['config_hash'] or profile.mode != event['mode']
                or decode(action.evidence['response'], parent.payload['workspace'], profile.tariff) != child.payload):
            raise ValueError()
        return child
    except (ValueError, KeyError, TypeError, AttributeError):
        raise Denied('code_result_binding_changed') from None


def intake(bridge, session, number):
    rid = bridge.profile + ':' + number
    records = code_workspace.history(bridge.store, session)
    pins = [pin for pin, seed in records.items() if seed['context']['request_id'] == rid]
    return pins[-1] if pins else None


def apply(bridge, session, iid, number):
    from .coding_preparation import read_locked
    from .plan_acceptance import read_locked as acceptance
    from .request_planning import _context
    from .telegram_planning_authorize import receipt
    _, origin = receipt(bridge, session, iid, 'develop')
    rid = bridge.profile + ':' + number
    if session.get(TelegramInbox, rid) is None:
        return bridge.finish(session, iid, 'Запрос не найден в этом подключении.')
    context = _context(bridge.store, session, rid)
    if context.project_id != 'command-center':
        return bridge.finish(session, iid, f'Для этого сценария выберите AI Commander: /request {number}.')
    if context.halted or context.recovery:
        return bridge.finish(session, iid, 'Приём закрыт. Новая задача не создана.')
    accepted = acceptance(bridge.store, session, rid)
    if accepted['state'] != 'CURRENT':
        return bridge.finish(session, iid, f'Нужен актуальный принятый план. Подготовка: /plan_prepare {number}; '
            f'просмотр: /plan {number}; принятие: /plan_accept {number}. AI этой командой не вызывается.')
    preparation = read_locked(bridge.store, session, rid)
    if preparation['state'] != 'PREPARED_NOT_RUNNABLE':
        return bridge.finish(session, iid, f'План принят. Задайте файлы и тесты: /coding_prepare {number}.')
    pin = origin.event.get('code_workspace_pin')
    if pin is None:
        return bridge.finish(session, iid, 'Нужна проверенная локальная Git-капсула выбранных файлов и тестов. '
            f'После её подготовки повторите /develop {number}. AI и выполнение не запускались.')
    try:
        task = code_workspace.create_locked(bridge.store, session, rid, pin)
    except Denied as error:
        if str(error) not in {'code_workspace_stale', 'code_workspace_review_changed'}:
            raise
        return bridge.finish(session, iid, 'Контекст, план или Git-капсула изменились. Нужна новая подготовка '
            f'для /develop {number}. AI и выполнение не запускались.')
    if task['state'] == 'SUCCEEDED':
        events = session.scalars(select(Audit).where(Audit.event['kind'].as_string() == BOUND,
            Audit.event['task_id'].as_string() == task['id'])).all()
        if len(events) != 1:
            raise Denied('code_result_binding_missing')
        e = events[0].event
        child = result(bridge, session, session.get(Task, task['id']), e)
        if child.state == 'WAITING_APPROVAL':
            return bridge.finish(session, iid, 'Код подготовлен. Просмотрите исходники, тесты и полный diff: '
                f'/coding_authorize {child.id}. Для запуска нужно отдельное подтверждение. '
                + ('AI-ответ был тестовым HTTP mock.' if e['mode'] == 'http_mock' else ''))
        return status(bridge, session, iid, child.id)
    if task['state'] == 'WAITING_APPROVAL':
        return bridge.finish(session, iid, 'Задача подготовки кода создана. Один AI-запрос требует отдельного '
            f'разрешения: /code_authorize {task["id"]}. Платный вызов ещё не запускался.')
    return bridge.finish(session, iid, f'Подготовка кода: {task["state"]}. Повторная проверка: /develop {number}. '
        'Новый AI-вызов этой командой не запускается.')


def collect(bridge, session):
    rows = session.scalars(select(Audit).where(Audit.event['kind'].as_string() == BOUND,
        Audit.event['revision'].as_string() == bridge.store.settings.source_revision,
        Audit.event['request_id'].as_string().startswith(bridge.profile + ':')).limit(101)).all()
    if len(rows) > 100:
        raise Denied('code_notification_capacity')
    for row in rows:
        e = row.event
        parent = session.get(Task, e['task_id'])
        child = result(bridge, session, parent, e)
        number = e['request_id'].removeprefix(bridge.profile + ':')
        text = (f'Код для поручения №{number} подготовлен. '
            + ('Тестовый HTTP mock; реальный AI не вызывался. ' if e['mode'] == 'http_mock' else '')
            + f'Просмотр diff и отдельное разрешение запуска: /coding_authorize {child.id}. '
            'Код ещё не запускался; публикация не разрешена.')
        bridge.enqueue(session, 'code-prepared:' + parent.id, text)
        if child.state in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'RECONCILING', 'SECURITY_BLOCKED'}:
            # Use exactly the same verified report and profile checks as the on-demand status.
            key = 'code-result:' + child.id + ':' + child.state
            from .telegram_coding_approval import status_text
            bridge.enqueue(session, key, status_text(bridge, session, child.id))
