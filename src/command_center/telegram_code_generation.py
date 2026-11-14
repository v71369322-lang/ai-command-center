"""Observed, purpose-specific consent for one code proposal; never execution consent."""
from datetime import datetime
import hashlib
import re
import secrets
from uuid import UUID

from sqlalchemy import select

from .code_generation import authorize_locked, configured, quote
from .code_workspace import KIND
from .models import Audit, Task, TelegramDelivery, TelegramInbox
from .store import Denied, canonical, digest
from .telegram_experiment import rub
from .telegram_plan_acceptance import observed
from .telegram_planning_authorize import done, receipt

ISSUED = 'telegram_code_generation_issued'
CONSUMED = 'telegram_code_generation_consumed'
LABEL = 'Разрешить один AI-запрос кода'


def parse(value):
    parts = value.split()
    try:
        if len(parts) != 2 or str(UUID(parts[1])) != parts[1]:
            raise ValueError()
    except ValueError:
        raise Denied('code_generation_task_id_required') from None
    return {'kind': 'code_authorize_request', 'task': parts[1]}


def parse_callback(value):
    if not isinstance(value, str) or not re.fullmatch(r'cg:[A-Za-z0-9_-]{32}', value):
        raise Denied('code_generation_callback_invalid')
    return {'kind': 'code_authorize_confirm', 'card': hashlib.sha256(value[3:].encode()).hexdigest()}


def keyboard(token):
    return {'inline_keyboard': [[{'text': LABEL, 'callback_data': 'cg:' + token}]]}


def allowed_markup(value):
    try:
        token = value['inline_keyboard'][0][0]['callback_data']
        parse_callback(token)
        return canonical(value) == canonical(keyboard(token[3:]))
    except (Denied, KeyError, TypeError, IndexError):
        return False


def binding(bridge, session, tid):
    task = session.get(Task, tid)
    if not task or task.payload.get('kind') != KIND or task.state != 'WAITING_APPROVAL':
        return None
    if not task.payload['workspace']['context']['request_id'].startswith(bridge.profile + ':'):
        return None
    bridge.store.check_task_revision(session, task)
    _, profile_digest = configured(bridge.store, session)
    return {'profile_digest': profile_digest, 'task_id': tid, 'task_version': task.version, 'payload_hash': task.payload_hash,
            'workspace_digest': task.payload['workspace_digest']}


def issue(bridge, session, iid):
    row, anchor = receipt(bridge, session, iid, 'code_authorize_request')
    task = session.get(Task, row.intent['task'])
    pin = anchor.event.get('code_review_pin')
    try:
        if not pin or pin != binding(bridge, session, row.intent['task']):
            raise Denied('code_review_changed')
        profile, _ = configured(bridge.store, session)
        issued = int(datetime.fromisoformat(anchor.event['time']).timestamp())
        review = quote(bridge.store, session, task, profile, issued, issued + 120)
    except Denied:
        return bridge.finish(session, iid, 'AI-подготовка кода закрыта: нужен свежий отдельный профиль '
            'модели, тарифа, бюджета и передачи исходников. AI не вызывался; расходы и выполнение не разрешены.')
    token = secrets.token_urlsafe(24)
    seed = task.payload['workspace']
    text = ('Один AI-запрос для подготовки кода. ' + ('HTTP mock: деньги не расходуются.\n'
        if profile.mode == 'http_mock' else 'Платный API-запрос.\n')
        + f'Задача: {task.id}; версия {task.version}.\nМодель: {review["model"]}. '
        + f'Максимальный резерв по тарифу: {rub(review["maximum_nano_rub"])}.\n'
        + 'Передаются текст поручения, принятый план и точные исходники/тесты: '
        + ', '.join(sorted(set(seed['specification']['scope']['allowed_files'])
                            | set(seed['specification']['scope']['test_files'])))
        + f'\nКапсула: {review["workspace_digest"]}.\nЗапрос API: {review["provider_request_digest"]}.\n'
        + f'Действует до {review["expires_at"]} UTC Unix; 1 вызов, неизвестный итог — без повтора. '
        + 'Это расчёт резерва, не ограничение списаний провайдера. '
        + 'Результат — отдельная задача с просмотром diff и новым подтверждением. '
        + 'Запуск кода, публикация и установка не разрешаются.')
    if len(text) > 4096 or len(canonical({'chat_id': bridge.owner, 'text': text,
                                         'reply_markup': keyboard(token)}).encode()) > 8192:
        raise Denied('code_review_size')
    delivery = bridge.finish(session, iid, text, keyboard(token))
    bridge.store.audit(session, ISSUED, 'owner', task.id, profile=bridge.profile,
        owner_id=bridge.owner, connection_digest=getattr(bridge.client, 'approved', bridge.profile),
        origin=iid, origin_pin=pin, delivery_id=delivery,
        request_hash=digest(session.get(TelegramDelivery, delivery).body),
        card=hashlib.sha256(token.encode()).hexdigest(), review=review, review_digest=digest(review))


def proof(store, session, task, review, card, *, callback=None):
    try:
        rows = session.scalars(select(Audit).where(Audit.event['kind'].as_string() == ISSUED,
            Audit.event['card'].as_string() == card)).all()
        if len(rows) != 1:
            raise ValueError()
        event = rows[0].event
        profile = event['profile']
        if (event['actor'] != 'owner' or event['task_id'] != task.id or event['review'] != review
                or event['review_digest'] != digest(review) or event['revision'] != store.settings.source_revision
                or not task.payload['workspace']['context']['request_id'].startswith(profile + ':')):
            raise ValueError()
        origin = session.get(TelegramInbox, event['origin'])
        pin = {'profile_digest': review['profile_digest'], 'task_id': task.id, 'task_version': task.version, 'payload_hash': task.payload_hash,
               'workspace_digest': task.payload['workspace_digest']}
        expected = {'kind': 'code_authorize_request', 'task': task.id}
        anchor = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_update_received',
            Audit.event['profile'].as_string() == profile,
            Audit.event['update_id'].as_string() == event['origin'].removeprefix(profile + ':'),
            Audit.event['intent_hash'].as_string() == digest(expected)).limit(1))
        if (not origin or origin.profile != profile or origin.state != 'DONE' or origin.intent != expected
                or origin.fingerprint != digest(expected) or event['origin_pin'] != pin or not anchor
                or anchor.event.get('code_review_pin') != pin or anchor.event['actor'] != 'owner'
                or anchor.event['revision'] != store.settings.source_revision
                or int(datetime.fromisoformat(anchor.event['time']).timestamp()) != review['issued_at']):
            raise ValueError()
        delivery = session.get(TelegramDelivery, event['delivery_id'])
        if not delivery or not allowed_markup(delivery.body.get('reply_markup')):
            raise ValueError()
        token = delivery.body['reply_markup']['inline_keyboard'][0][0]['callback_data']
        if parse_callback(token)['card'] != card:
            raise ValueError()
        observed(session, delivery.id, event['request_hash'], profile, event['owner_id'], event['revision'])
        used = session.scalars(select(Audit).where(Audit.event['kind'].as_string() == CONSUMED,
            Audit.event['card'].as_string() == card)).all()
        if callback is None:
            if len(used) != 1:
                raise ValueError()
            consumed = used[0].event
            if (consumed['actor'] != 'owner' or consumed['task_id'] != task.id
                    or consumed['profile'] != profile or consumed['revision'] != event['revision']
                    or consumed['review_digest'] != digest(review)):
                raise ValueError()
            callback = session.get(TelegramInbox, consumed['inbox_id'])
            if not callback or callback.state != 'DONE':
                raise ValueError()
        expected = {'kind': 'code_authorize_confirm', 'card': card, 'message_id': delivery.message_id}
        if 'callback_query_id' in callback.intent:
            value = callback.intent['callback_query_id']
            if not isinstance(value, str) or not 1 <= len(value) <= 128:
                raise ValueError()
            expected['callback_query_id'] = value
        if (callback.profile != profile or callback.intent != expected or callback.fingerprint != digest(expected)
                or callback.task_id is not None):
            raise ValueError()
        anchor = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_update_received',
            Audit.event['profile'].as_string() == profile,
            Audit.event['update_id'].as_string() == callback.id.removeprefix(profile + ':'),
            Audit.event['intent_hash'].as_string() == callback.fingerprint).limit(1))
        if not anchor or anchor.event['actor'] != 'owner' or anchor.event['revision'] != event['revision']:
            raise ValueError()
        return event, bool(used)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise Denied('code_observed_consent_required') from None


def consent_proof(store, session, task, review, card):
    return proof(store, session, task, review, card)


def confirm(bridge, iid, intent):
    with bridge.store.transaction() as session:
        bridge.guard()
        bridge.store.check_audit(session)
        if done(bridge, session, iid, intent):
            return
        row, _ = receipt(bridge, session, iid, 'code_authorize_confirm')
        issued = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == ISSUED,
            Audit.event['card'].as_string() == intent['card']).limit(1))
        if not issued or issued.event['profile'] != bridge.profile:
            raise Denied('code_card_unknown')
        event = issued.event
        if (event['owner_id'] != bridge.owner
                or event['connection_digest'] != getattr(bridge.client, 'approved', bridge.profile)):
            raise Denied('code_connection_changed')
        task = session.get(Task, event['task_id'])
        _, used = proof(bridge.store, session, task, event['review'], intent['card'], callback=row)
        if used:
            return bridge.finish(session, iid, 'Подтверждение уже использовано. Новый AI-вызов не разрешён.')
        bridge.store.audit(session, CONSUMED, 'owner', task.id, profile=bridge.profile, inbox_id=iid,
                           card=intent['card'], review_digest=event['review_digest'])
        bridge.finish(session, iid, 'Разрешён один запрос подготовки кода. AI этой командой не вызывался. '
            'Исполнение и публикация не разрешены. Статус: /develop '
            + task.payload['workspace']['context']['request_id'].removeprefix(bridge.profile + ':'))
        authorize_locked(bridge.store, session, task, event['review'], intent['card'])
        bridge.guard()
        p, _ = configured(bridge.store, session)
        quote(bridge.store, session, task, p, event['review']['issued_at'], event['review']['expires_at'])
