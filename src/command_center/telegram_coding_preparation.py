"""Explicit owner file/test scope to a non-runnable specification. No execution."""
import json
import re
from datetime import datetime

from .coding_preparation import CodingScope, CodingPreparationRequest, CodingPreparationSave
from .coding_preparation import preview_locked, prepare_locked, read_locked
from .plan_acceptance import read_locked as accepted_read
from .request_planning import _unique
from .store import Denied
from .telegram_planning_authorize import receipt


def parse(value):
    parts = value.split(maxsplit=2)
    if (len(parts) < 2 or not re.fullmatch(r'0|[1-9][0-9]{0,15}', parts[1]) or int(parts[1]) >= 2**53):
        raise Denied('coding_preparation_command_invalid')
    try:
        scope = CodingScope.model_validate(json.loads(parts[2], object_pairs_hook=_unique)).model_dump() if len(parts) == 3 else None
    except (ValueError, TypeError, RecursionError):
        raise Denied('coding_preparation_scope_invalid') from None
    return {'kind': 'coding_prepare', 'number': parts[1], 'scope': scope}


def reply(bridge, session, iid, intent):
    rid = bridge.profile + ':' + intent['number']
    if intent['scope'] is None:
        current = read_locked(bridge.store, session, rid)
        if current['state'] == 'PREPARED_NOT_RUNNABLE':
            return bridge.finish(session, iid, 'Coding-спецификация подготовлена, запуск недоступен.\n'
                f'Hash: {current["preparation"]["spec_digest"]}.\n'
                'Доступ к репозиторию, runtime и F1-разрешение выполнения ещё нужны. Код и AI не запускались.')
        return bridge.finish(session, iid, 'Нужен принятый текущий план и явные файлы/тесты владельца. '
            'Формат: /coding_prepare номер {"allowed_files":["src/command_center/example.py"],'
            '"test_files":["tests/test_example.py"]}. Это пример формата, не выбранные файлы. '
            'Подготовка сохраняет только спецификацию; выполнение не разрешается.')
    accepted = accepted_read(bridge.store, session, rid)
    _, received = receipt(bridge, session, iid, 'coding_prepare')
    if (accepted['state'] != 'CURRENT'
            or received.event.get('coding_acceptance_digest') != accepted['receipt']['snapshot_digest']
            or datetime.fromisoformat(accepted['receipt']['accepted_at']) > datetime.fromisoformat(received.event['time'])):
        return bridge.finish(session, iid, 'Сначала примите текущую версию плана: /plan_accept номер. '
            'Затем отправьте новую команду подготовки; прежняя команда не переназначается на другой план. '
            'Coding-задача не создана.')
    request = CodingPreparationRequest(request_id=rid,
        expected_acceptance_digest=accepted['receipt']['snapshot_digest'], scope=CodingScope.model_validate(intent['scope']))
    value = preview_locked(bridge.store, session, request)
    saved = prepare_locked(bridge.store, session, CodingPreparationSave(**request.model_dump(),
        expected_spec_digest=value['spec_digest']))
    bridge.guard()
    bridge.finish(session, iid, 'Coding-спецификация подготовлена: PREPARED_NOT_RUNNABLE.\n'
        f'Hash: {saved["spec_digest"]}.\n'
        'Файлы: ' + ', '.join(request.scope.allowed_files) + '\nТесты: ' + ', '.join(request.scope.test_files) + '\n'
        'Сеть и credentials в спецификации запрещены. Доступ к репозиторию и реальная изоляция ещё не проверены. '
        'Task, AI-вызов, запуск кода и публикация не создавались.')
