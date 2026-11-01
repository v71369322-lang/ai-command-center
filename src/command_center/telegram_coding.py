"""Fixed F2 mock exercise over existing F1 authority, never an AI gateway."""
from datetime import datetime
import re

from sqlalchemy import select

from .coding.contract import CodingRequest, payload
from .coding.spec import BASE_SHA, OBJECTIVE, PLAN, REPOSITORY
from .models import Audit
from .store import digest


def exercise():
    return payload(CodingRequest(repository=REPOSITORY, objective=OBJECTIVE, base_sha=BASE_SHA,
        provider='mock', experiment_id=None, max_iterations=2, max_units=2,
        max_tokens=2048, max_seconds=15, scenario='normal'))


def plan():
    return ('Тестовый разработчик (mock): исправить сумму положительных чисел.\n'
            'Только f2-synthetic-sum, файл calculator.py; фиксированная Git-ревизия.\n'
            + '\n'.join(f'{i}. {step}' for i, step in enumerate(PLAN, 1))
            + '\nДо 2 итераций, 2048 синтетических токенов, 15 секунд, 2 тестовые единицы. '
              'Это не деньги и не платный API. Провайдер детерминированный, настоящего AI нет. '
              'PR только mock, публикации в GitHub нет.\n'
              'Для запуска фиксированного упражнения: /coding_demo. '
              'Обычные запросы и CRM эта команда не выполняет.')


def accepted(bridge, session, iid, task):
    from .models import Control, TelegramInbox
    from .store import Denied
    bridge.guard()
    bridge.store.check_task_revision(session, task)
    row = session.get(TelegramInbox, iid)
    if row.state == 'DONE' and row.task_id == task.id:
        return
    received = session.execute(select(Audit).where(
        Audit.event['kind'].as_string() == 'telegram_update_received',
        Audit.event['actor'].as_string() == 'owner',
        Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['update_id'].as_string() == iid.rsplit(':', 1)[1],
        Audit.event['intent_hash'].as_string() == row.fingerprint,
        Audit.event['revision'].as_string() == bridge.store.settings.source_revision)
        .order_by(Audit.sequence).limit(1)).scalar_one_or_none()
    if not received or received.event.get('admission_epoch') != session.get(Control, 1).epoch:
        raise Denied('telegram_coding_admission_expired')
    try:
        expires = datetime.fromisoformat(received.event['expires_at'])
        if expires.tzinfo is None or expires <= bridge.store.now(session):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise Denied('telegram_coding_admission_expired') from None
    if (row.state != 'RECEIVED' or row.profile != bridge.profile or row.intent != {'kind': 'coding_demo'}
            or row.fingerprint != digest(row.intent) or task.payload != exercise()
            or task.payload_hash != digest(exercise()) or task.request_key != 'owner:tg:' + iid):
        raise Denied('telegram_coding_scope_changed')
    row.task_id = task.id
    bridge.store.audit(session, 'telegram_coding_accepted', 'owner', task.id,
                       profile=bridge.profile, inbox_id=iid, request_fingerprint=row.fingerprint,
                       payload_hash=task.payload_hash)
    bridge.finish(session, iid,
        f'Тестовый разработчик (mock) принят: {task.id}.\n'
        'Только фиксированная функция calculator.py; до 2 итераций. '
        'Настоящий AI, оплата, CRM и публикация PR не включены.\n'
        f'Статус: /status {task.id}\nОтмена: /cancel {task.id}')


def summary(bridge, session, task, *, compact=False):
    if not bridge.confirmed_result(session, task):
        return 'Успех тестового разработчика не подтверждён; нужна сверка.'
    data = task.coding_evidence
    anchor = session.execute(select(Audit).where(
        Audit.event['kind'].as_string() == 'coding_complete',
        Audit.event['actor'].as_string() == 'coding_pipeline',
        Audit.event['task_id'].as_string() == task.id,
        Audit.event['fence'].as_integer() == task.fence,
        Audit.event['revision'].as_string() == bridge.store.settings.source_revision,
        Audit.event['evidence_hash'].as_string() == digest(data))).first()
    pr = data.get('pr') if isinstance(data, dict) else None
    if (not anchor or data.get('stage') != 'complete' or not isinstance(pr, dict)
            or pr.get('mode') != 'mock' or pr.get('published') is not False or pr.get('url') is not None
            or pr.get('task_id') != task.id
            or not re.fullmatch('[a-f0-9]{64}', str(data.get('verification_digest')))):
        return 'Доказательства coding-проверки не подтверждены; нужна сверка. PR не публикуется.'
    runs = data.get('test_runs')
    if (not isinstance(runs, list) or len(runs) != 2
            or any(not isinstance(r, dict) or not isinstance(r.get('checks'), dict) for r in runs)
            or any(type(r['checks'].get('passed')) is not bool for r in runs)
            or [r['checks'].get('passed') for r in runs] != [False, True]):
        return 'История тестов не подтверждена; нужна сверка.'
    if compact:
        return 'Результат независимо проверен; PR mock, не опубликован. SHA-256 ' + task.artifact_hash
    return ('Проверка 1: найдена ошибка. Проверка 2: пройдена после исправления.\n'
            'Результат независимо проверен; SHA-256 ' + task.artifact_hash
            + '\nPR подготовлен в mock-режиме, не опубликован. Настоящий AI не подключён.')
