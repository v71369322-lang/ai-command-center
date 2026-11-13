"""Observed private-owner review composes atomically with the existing F1 approval."""
from datetime import datetime, timezone
import hashlib
import json
import re
import secrets
from uuid import UUID

from sqlalchemy import select

from .isolated_coding import KIND, report, validate_payload
from .models import Approval, Audit, Control, Task, TelegramInbox
from .store import Denied, canonical, digest
from .telegram_plan_acceptance import observed
from .telegram_planning_authorize import done, receipt

ISSUED = 'telegram_coding_approval_issued'
CONSUMED = 'telegram_coding_approval_consumed'
LABEL = 'Разрешить один offline coding-запуск'
SECONDS = 300


def parse(value):
    parts = value.split()
    try:
        if (len(parts) != 2 or parts[0] not in {'/coding_authorize', '/coding_status'}
                or str(UUID(parts[1])) != parts[1]):
            raise ValueError()
    except ValueError:
        raise Denied('coding_approval_task_id_required') from None
    return {'kind': 'coding_authorize_request' if parts[0] == '/coding_authorize' else 'coding_status', 'task': parts[1]}


def parse_callback(value):
    if not isinstance(value, str) or not re.fullmatch(r'ca:[A-Za-z0-9_-]{32}', value):
        raise Denied('coding_approval_callback_invalid')
    return {'kind': 'coding_authorize_confirm', 'card': hashlib.sha256(value[3:].encode()).hexdigest()}


def keyboard(token):
    return {'inline_keyboard': [[{'text': LABEL, 'callback_data': 'ca:' + token}]]}


def allowed_markup(value):
    try:
        token = value['inline_keyboard'][0][0]['callback_data']
        parse_callback(token)
        return canonical(value) == canonical(keyboard(token[3:]))
    except (Denied, KeyError, TypeError, IndexError):
        return False


def binding(bridge, session, task_id):
    task = session.get(Task, task_id)
    control = session.get(Control, 1)
    if (not task or task.owner_role != 'owner' or task.payload.get('kind') != KIND
            or task.state != 'WAITING_APPROVAL' or task.epoch != control.epoch
            or control.halted or control.recovery):
        return None
    try:
        bridge.store.check_task_revision(session, task)
    except Denied as error:
        if str(error) not in {'coding_binding_stale', 'stale_task_revision'}:
            raise
        return None
    ref = task.payload['specification']['acceptance_reference']
    if not ref['request_id'].startswith(bridge.profile + ':'):
        return None
    return {'task_id': task.id, 'task_version': task.version, 'payload_hash': task.payload_hash,
            'epoch': task.epoch, 'source_revision': bridge.store.settings.source_revision,
            'request_id': ref['request_id'], 'spec_digest': task.payload['spec_digest']}


def pages(bridge, task, pin):
    files, patch = validate_payload(task.payload)
    spec = task.payload['specification']
    content = ('Точный offline coding-запуск. Состав: существующие исходные файлы и неизменяемые тесты, '
        'затем diff заданных замен. Это не AI-генерация.\n'
        'Объявленный Git commit: ' + spec['acceptance_reference']['declared_repository_revision'] + '\n'
        'Git-хэши проверены; принадлежность удалённому репозиторию и доступ не проверены.\n'
        'Scope: ' + canonical(spec['scope']) + '\nПроверки: ' + canonical(spec['verification_commands'])
        + '\nИзоляция: ' + canonical(spec['isolation']) + '\n')
    for path, source in sorted(files.items()):
        content += '\nИсходный файл: ' + path + '\n' + source + '\nКонец файла: ' + path + '\n'
    content += '\nПолный diff замен:\n' + patch + '\nКонец diff.\n'
    if getattr(bridge.client, 'sensitive', lambda text: False)(content):
        raise Denied('telegram_secret_content_forbidden')
    # Preserve every codepoint, including long lines; no truncated preview can authorize.
    chunks, current, size = [], '', 0
    for character in content:
        count = len(character.encode())
        if size + count > 1000:
            chunks.append(current)
            current, size = '', 0
        current += character
        size += count
    if current:
        chunks.append(current)
    if not 1 <= len(chunks) <= 50:
        raise Denied('coding_approval_review_size')
    result = []
    for i, chunk in enumerate(chunks, 1):
        text = (f'Coding {task.id}, версия {pin["task_version"]}.\nPayload: {pin["payload_hash"]}.\n'
                f'Часть {i}/{len(chunks)}.\n' + chunk)
        bridge.check_text(text)
        if len(canonical({'chat_id': bridge.owner, 'text': text}).encode()) > 8192:
            raise Denied('coding_approval_review_size')
        result.append(text)
    return result


def card_text(pin, expires):
    return (f'Разрешить один offline coding-запуск №{pin["request_id"].rsplit(":", 1)[1]}?\n'
        f'Задача: {pin["task_id"]}; версия {pin["task_version"]}; эпоха {pin["epoch"]}.\n'
        f'Payload: {pin["payload_hash"]}.\nСпецификация: {pin["spec_digest"]}.\n'
        f'Source: {pin["source_revision"]}.\n'
        f'Карточка до {datetime.fromtimestamp(expires, timezone.utc).isoformat()} (UTC).\n'
        'Подтверждение разрешит выполнение показанного кода и проверок в изоляции через F1. '
        'Срок F1-разрешения — не более 120 секунд и не позднее срока карточки. '
        'Все части выше должны быть доставлены. Сеть и credentials запрещены. '
        'AI-вызовы, расходы API, remote-доступ, публикация, merge и deployment не разрешаются. '
        'Rootless runtime проверяется broker перед запуском; эта карточка не доказывает его готовность.')


def issue(bridge, session, iid):
    row, received = receipt(bridge, session, iid, 'coding_authorize_request')
    issued = int(datetime.fromisoformat(received.event['time']).timestamp())
    pin = binding(bridge, session, row.intent['task'])
    if (pin is None or canonical(pin) != canonical(received.event.get('coding_task_review_pin'))
            or not issued <= int(bridge.store.now(session).timestamp()) < issued + SECONDS):
        return bridge.finish(session, iid, 'Текущая ожидающая coding-задача недоступна или команда устарела. '
            'Разрешение не выдано. Нужны точный UUID задачи, текущий принятый план и открытый приём. '
            'Повторите /coding_authorize UUID после подготовки задачи.')
    task = session.get(Task, pin['task_id'])
    parts = [{'delivery_id': bridge.enqueue(session, iid + ':coding-page:' + str(i), text),
              'request_hash': digest({'chat_id': bridge.owner, 'text': text})}
             for i, text in enumerate(pages(bridge, task, pin), 1)]
    token = secrets.token_urlsafe(24)
    text = card_text(pin, issued + SECONDS)
    bridge.check_text(text)
    body = {'chat_id': bridge.owner, 'text': text, 'reply_markup': keyboard(token)}
    if len(canonical(body).encode()) > 8192:
        raise Denied('coding_approval_review_size')
    oid = bridge.finish(session, iid, text, keyboard(token))
    bridge.store.audit(session, ISSUED, 'owner', task.id, profile=bridge.profile,
        inbox_id=iid, pin=pin, pages=parts, issued_at=issued, expires_at=issued + SECONDS,
        owner_id=bridge.owner, connection_digest=getattr(bridge.client, 'approved', bridge.profile),
        delivery_id=oid, request_hash=digest(body), card=hashlib.sha256(token.encode()).hexdigest())


def confirm(bridge, iid, intent):
    with bridge.store.transaction() as session:
        bridge.guard()
        bridge.store.check_audit(session)
        if done(bridge, session, iid, intent):
            return
        row, _ = receipt(bridge, session, iid, 'coding_authorize_confirm')
        if row.intent != intent:
            raise Denied('coding_approval_receipt_invalid')
        issued = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == ISSUED,
            Audit.event['actor'].as_string() == 'owner', Audit.event['profile'].as_string() == bridge.profile,
            Audit.event['card'].as_string() == intent['card']).limit(1))
        if issued is None:
            raise Denied('coding_approval_card_unknown')
        e = issued.event
        try:
            pin = e['pin']
            origin = session.get(TelegramInbox, e['inbox_id'])
            if (set(e) != {'kind', 'actor', 'task_id', 'time', 'revision', 'profile', 'inbox_id', 'pin',
                          'pages', 'issued_at', 'expires_at', 'owner_id', 'connection_digest',
                          'delivery_id', 'request_hash', 'card'}
                    or e['revision'] != bridge.store.settings.source_revision
                    or datetime.fromisoformat(e['time']).tzinfo is None
                    or pin['source_revision'] != e['revision'] or e['task_id'] != pin['task_id']
                    or type(e['owner_id']) is not int or e['owner_id'] != bridge.owner
                    or e['connection_digest'] != getattr(bridge.client, 'approved', bridge.profile)
                    or not pin['request_id'].startswith(bridge.profile + ':')
                    or type(e['issued_at']) is not int or type(e['expires_at']) is not int
                    or e['expires_at'] != e['issued_at'] + SECONDS
                    or e['delivery_id'] != digest({'profile': bridge.profile, 'event': e['inbox_id'] + ':reply'})
                    or not origin or origin.profile != bridge.profile or origin.state != 'DONE'
                    or origin.task_id is not None or origin.fingerprint != digest(origin.intent)
                    or origin.intent != {'kind': 'coding_authorize_request', 'task': pin['task_id']}):
                raise ValueError()
            anchor = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_update_received',
                Audit.event['actor'].as_string() == 'owner', Audit.event['profile'].as_string() == bridge.profile,
                Audit.event['update_id'].as_string() == e['inbox_id'].removeprefix(bridge.profile + ':'),
                Audit.event['intent_hash'].as_string() == origin.fingerprint,
                Audit.event['revision'].as_string() == e['revision']).limit(1))
            if (not anchor or int(datetime.fromisoformat(anchor.event['time']).timestamp()) != e['issued_at']
                    or canonical(anchor.event.get('coding_task_review_pin')) != canonical(pin)):
                raise ValueError()
        except (ValueError, KeyError, TypeError, AttributeError):
            raise Denied('coding_approval_card_binding_invalid') from None
        used = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == CONSUMED,
            Audit.event['profile'].as_string() == bridge.profile, Audit.event['card'].as_string() == intent['card']).limit(1))
        if used:
            return bridge.finish(session, iid, 'Это подтверждение уже использовано. Повторный запуск не разрешён.')
        if not e['issued_at'] <= int(bridge.store.now(session).timestamp()) < e['expires_at']:
            return bridge.finish(session, iid, 'Карточка устарела. Разрешение не выдано. Повторите /coding_authorize UUID.')
        current = binding(bridge, session, pin['task_id'])
        if canonical(current) != canonical(pin):
            return bridge.finish(session, iid, 'Задача или принятый план изменились; либо приём остановлен. '
                'Разрешение не выдано. Нужна новая карточка текущей задачи.')
        task = session.get(Task, pin['task_id'])
        texts = pages(bridge, task, pin)
        expected = [{'delivery_id': digest({'profile': bridge.profile,
            'event': e['inbox_id'] + ':coding-page:' + str(i)}),
            'request_hash': digest({'chat_id': bridge.owner, 'text': text})} for i, text in enumerate(texts, 1)]
        if canonical(expected) != canonical(e['pages']):
            raise Denied('coding_approval_page_binding_invalid')
        try:
            for part in expected:
                observed(session, part['delivery_id'], part['request_hash'], bridge.profile, bridge.owner, e['revision'])
            delivery = observed(session, e['delivery_id'], e['request_hash'], bridge.profile, bridge.owner,
                                e['revision'], intent['message_id'])
        except Denied:
            return bridge.finish(session, iid, 'Доставка всех частей не подтверждена. Разрешение не выдано. '
                'Новая карточка: /coding_authorize UUID.')
        if (not allowed_markup(delivery.body.get('reply_markup'))
                or parse_callback(delivery.body['reply_markup']['inline_keyboard'][0][0]['callback_data'])['card'] != intent['card']
                or delivery.body['text'] != card_text(pin, e['expires_at'])):
            raise Denied('coding_approval_card_binding_invalid')
        deadline = datetime.fromtimestamp(e['expires_at'], timezone.utc)
        bridge.store._approve_locked(session, 'owner', task.id, pin['task_version'], _deadline=deadline)
        bridge.store.audit(session, CONSUMED, 'owner', task.id, profile=bridge.profile, card=intent['card'],
                           inbox_id=iid, payload_hash=pin['payload_hash'])
        bridge.finish(session, iid, 'F1-разрешение одного offline coding-запуска сохранено. '
            f'Задача: {task.id}. Выполнение ещё не подтверждено; состояние: /coding_status {task.id}. '
            f'Отмена: /cancel {task.id}. AI-расходы и публикация не разрешены.')
        bridge.guard()
        if not e['issued_at'] <= int(bridge.store.now(session).timestamp()) < e['expires_at']:
            raise Denied('coding_approval_card_expired')
        if session.get(Approval, task.id).expires_at <= bridge.store.now(session):
            raise Denied('coding_approval_deadline_expired')


def status(bridge, session, iid, task_id):
    task = session.get(Task, task_id)
    created = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == 'task_created',
        Audit.event['actor'].as_string() == 'owner', Audit.event['task_id'].as_string() == task_id).limit(1))
    if (not task or task.owner_role != 'owner' or task.payload.get('kind') != KIND or not created
            or created.event.get('revision') != bridge.store.settings.source_revision
            or created.event.get('payload_hash') != task.payload_hash or digest(task.payload) != task.payload_hash
            or created.event.get('isolated_spec_digest') != task.payload.get('spec_digest')):
        return bridge.finish(session, iid, 'Coding-задача этого подключения и source revision не найдена или не подтверждена.')
    validate_payload(task.payload)
    if not task.payload['specification']['acceptance_reference']['request_id'].startswith(bridge.profile + ':'):
        return bridge.finish(session, iid, 'Coding-задача этого подключения не найдена.')
    verified = False
    if bridge.confirmed_result(session, task):
        expected = {**report(task.payload), 'checks': [{'command': c, 'passed': True}
            for c in task.payload['specification']['verification_commands']],
            'passed': True, 'independent_verification': True}
        try:
            verified = canonical(json.loads(task.artifact)) == canonical(expected)
        except (ValueError, TypeError):
            pass
    text = (f'Offline coding-задача {task.id}; версия {task.version}.\nСостояние F1: {task.state}.\n'
            + ('Результат независимо проверен: ' + task.artifact_hash + '.\n' if verified else
               'Подтверждённого результата пока нет; состояние F1 само по себе не доказывает исполнение или остановку.\n')
            + f'Отмена: /cancel {task.id}.\nAI-вызовы и публикация этим заданием не разрешены.')
    return bridge.finish(session, iid, text)
