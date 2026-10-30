"""Owner-private editing of advisory setup drafts, using the existing F1 lock."""
import re
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from .models import Audit, TelegramInbox
from .project_inbox import IDS, PROJECTS
from .project_setup import Draft, MAX_EVENTS, patch, read_locked, restore
from .store import Denied, canonical, digest

COMMANDS = {'/setup', '/setup_set', '/setup_clear', '/setup_history', '/setup_restore'}
FIELDS = {'revision': 'repository_revision', 'verification': 'verification_kind',
          'delivery': 'delivery_kind', 'target': 'deployment_target', 'acceptance': 'acceptance'}
VERIFICATION = {'not_selected': 'не выбран', 'python': 'Python', 'node': 'Node.js', 'python_node': 'Python и Node.js'}
DELIVERY = {'not_selected': 'не выбран', 'manual_review': 'ручная проверка', 'pipeline_review': 'проверка существующего канала'}


def number(value):
    if not re.fullmatch(r'0|[1-9][0-9]{0,2}', value) or int(value) > MAX_EVENTS:
        raise Denied('telegram_project_setup_version_invalid')
    return int(value)


def parse(value):
    parts = value.split()
    command = parts[0]
    if command == '/setup' and len(parts) == 1:
        return {'kind': 'project_setup', 'project_id': None, 'selected': None}
    if len(parts) < 2 or parts[1] not in IDS:
        raise Denied('telegram_project_setup_arguments_invalid')
    pid = parts[1]
    if command == '/setup' and len(parts) in {2, 3}:
        return {'kind': 'project_setup', 'project_id': pid, 'selected': number(parts[2]) if len(parts) == 3 else None}
    if command == '/setup_history' and len(parts) == 2:
        return {'kind': 'project_setup_history', 'project_id': pid}
    if command == '/setup_restore' and len(parts) == 4:
        return {'kind': 'project_setup_change', 'action': 'restore', 'project_id': pid,
                'expected_version': number(parts[2]), 'target_version': number(parts[3])}
    if command == '/setup_clear' and len(parts) == 4 and parts[3] in FIELDS:
        return {'kind': 'project_setup_change', 'action': 'clear', 'project_id': pid,
                'expected_version': number(parts[2]), 'field': FIELDS[parts[3]], 'value': None}
    if command == '/setup_set':
        tokens = value.split(maxsplit=4)
        if len(tokens) == 5 and tokens[3] in FIELDS:
            field, raw = FIELDS[tokens[3]], tokens[4]
            data = [line.strip() for line in raw.splitlines() if line.strip()] if field == 'acceptance' else raw
            try:
                draft = Draft.model_validate({field: data})
            except ValueError:
                raise Denied('telegram_project_setup_value_invalid') from None
            return {'kind': 'project_setup_change', 'action': 'patch', 'project_id': pid,
                    'expected_version': number(tokens[2]), 'field': field, 'value': draft.model_dump()[field]}
    raise Denied('telegram_project_setup_arguments_invalid')


def _bound(bridge, session, iid, intent):
    bridge.guard()
    row = session.get(TelegramInbox, iid)
    anchor = session.scalar(select(Audit).where(
        Audit.event['kind'].as_string() == 'telegram_update_received',
        Audit.event['actor'].as_string() == 'owner', Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['update_id'].as_string() == iid.rsplit(':', 1)[1],
        Audit.event['intent_hash'].as_string() == digest(intent),
        Audit.event['revision'].as_string() == bridge.store.settings.source_revision))
    if (not row or row.profile != bridge.profile or row.state not in {'RECEIVED', 'DONE'}
            or row.intent != intent or row.fingerprint != digest(intent) or not anchor):
        raise Denied('telegram_project_setup_intent_changed')
    return row


def apply(bridge, iid, intent):
    with bridge.store.transaction() as session:
        bridge.store.check_audit(session)
        if _bound(bridge, session, iid, intent).state == 'DONE':
            return
        target = read_locked(bridge.store, session, intent['project_id'], selected=intent['target_version']) if intent['action'] == 'restore' else None
    def finish(session, receipt):
        if _bound(bridge, session, iid, intent).state != 'DONE':
            bridge.finish(session, iid, f'Черновик {receipt["project_id"]} сохранён: версия {receipt["version"]}. '
                          'Подключения, запуск задач и расходы не включены. '
                          f'Проверить: /setup {receipt["project_id"]}.')
    operation = str(uuid5(NAMESPACE_URL, 'acc:telegram-project-setup:' + iid))
    try:
        if intent['action'] == 'restore':
            restore(bridge.store, 'owner', intent['project_id'], intent['expected_version'], intent['target_version'],
                    target['draft_digest'], operation, _scope_installer=finish)
        else:
            patch(bridge.store, 'owner', intent['project_id'], intent['expected_version'], intent['field'], intent['value'],
                  operation, clear=intent['action'] == 'clear', _scope_installer=finish)
    except Denied as error:
        if str(error) not in {'project_setup_stale_version', 'project_setup_restore_target_changed'}:
            raise
        with bridge.store.transaction() as session:
            bridge.store.check_audit(session)
            if _bound(bridge, session, iid, intent).state != 'DONE':
                bridge.finish(session, iid, 'Черновик не изменён: версия устарела или цель восстановления изменилась. '
                              f'Откройте /setup {intent["project_id"]} перед новой записью.')


def reply(bridge, session, intent, suffix):
    if intent['project_id'] is None:
        return ('Черновики подключения проектов.\n' + '\n'.join(f'{label}: /setup {pid}' for pid, label in PROJECTS)
                + '\nОтправляйте команды целиком с ID проекта. Черновик не выдаёт доступ и не включает выполнение.')
    view = read_locked(bridge.store, session, intent['project_id'], selected=intent.get('selected'))
    pid, v, d = view['project_id'], view['latest_version'], view['draft']
    for value in [d['repository_revision'], d['deployment_target'], *d['acceptance']]:
        if value:
            bridge.check_text(value)
    if intent['kind'] == 'project_setup_history':
        return (f'История черновика: {view["label"]}. Текущая версия {v}.\n' +
                '\n'.join(f'Версия {r["version"]}: /setup {pid} {r["version"]}' for r in view['history'][:5]) +
                f'\nВосстановление: /setup_restore {pid} {v} номер-версии. '
                'Будет создан новый черновик; подключения не включаются.')
    for width in (60, 30, 0):
        criteria = '\n'.join('• ' + text[:width] + ('…' if len(text) > width else '') for text in d['acceptance']) or 'не заданы'
        text = (f'Черновик подключения: {view["label"]}.\nВерсия {view["version"]}; текущая сохранённая {v}.\n'
                f'Ожидаемый репозиторий: {view["expected_repository"]}.\n'
                f'Версия кода: {d["repository_revision"] or "не задана"}.\n'
                f'Среда проверки: {VERIFICATION[d["verification_kind"]]}.\n'
                f'Доставка: {DELIVERY[d["delivery_kind"]]}. Метка сервера: {d["deployment_target"] or "не задана"}.\n'
                f'Заполнено {view["review"]["filled"]} из 5. '
                'Внешние проверки репозитория, изоляции, доставки и разрешения задачи обязательны.\n'
                f'Критерии (текст, не команды; краткий просмотр):\n{criteria}\n\n'
                f'Изменить одно поле: /setup_set {pid} {v} поле значение\n'
                'Поля: revision (SHA), verification (python/node/python_node), delivery (manual_review/pipeline_review), '
                'target (метка), acceptance (до 8 строк).\n'
                f'Очистить поле: /setup_clear {pid} {v} поле\nИстория: /setup_history {pid}\n'
                'Черновик не подключает проект, не запускает задачи и не разрешает расходы.')
        if len(text + suffix) <= 4096 and len(canonical({'chat_id': bridge.owner, 'text': text + suffix}).encode()) <= 8192:
            return text
    raise Denied('telegram_project_setup_reply_size')
