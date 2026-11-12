"""Observed, bounded content confirmation. Never execution or spending authority."""
from datetime import datetime, timezone
import hashlib
import re
import secrets

from sqlalchemy import select

from .models import Audit, TelegramDelivery, TelegramInbox
from .plan_acceptance import AcceptanceRequest, accept_locked, preview_locked
from .store import Denied, canonical, digest
from .telegram_planning_authorize import done, receipt

ISSUED = 'telegram_plan_content_card_issued'
CONSUMED = 'telegram_plan_content_card_consumed'
LABEL = 'Принять только содержание плана'
SECONDS = 300


def parse_callback(value):
    if not isinstance(value, str) or not re.fullmatch(r'pc:[A-Za-z0-9_-]{32}', value):
        raise Denied('plan_content_callback_invalid')
    return {'kind': 'plan_accept_confirm', 'card': hashlib.sha256(value[3:].encode()).hexdigest()}


def keyboard(token):
    return {'inline_keyboard': [[{'text': LABEL, 'callback_data': 'pc:' + token}]]}


def allowed_markup(value):
    try:
        token = value['inline_keyboard'][0][0]['callback_data']
        parse_callback(token)
        return canonical(value) == canonical(keyboard(token[3:]))
    except (Denied, KeyError, TypeError, IndexError):
        return False


def pages(bridge, view):
    ref, plan = view['reference'], view['proposal']
    number = ref['request_id'].rsplit(':', 1)[1]
    header = (f'Содержание плана №{number}, версия {ref["plan_version"]}.\n'
              f'Снимок: {view["snapshot_digest"]}.\n'
              + ('Источник: ручной черновик владельца.\n' if ref['origin'] == 'owner_authored' else
                 'Источник AI-ответа не подтверждён.\n')
              + 'Это предложение; выполнение не разрешено.\n')
    lines = [f'Кратко: {plan["summary"]}']
    for i, step in enumerate(plan['steps'], 1):
        lines.append(f'{i}. {step["description"]}')
        lines.extend('Критерий: ' + value for value in step['acceptance'])
    result, current = [], []
    def body(content, index):
        return header + f'Часть {index}.\n' + '\n'.join(content)
    def fits(text):
        return (len(text.encode()) <= 2000 and len(text) <= 4096
                and len(canonical({'chat_id': bridge.owner, 'text': text}).encode()) <= 8192)
    for line in lines:
        bridge.check_text(line)
        if not fits(body([*current, line], len(result) + 1)):
            if not current or not fits(body([line], len(result) + 2)):
                raise Denied('plan_content_page_size')
            result.append(body(current, len(result) + 1))
            current = []
        current.append(line)
    if current:
        result.append(body(current, len(result) + 1))
    if not 1 <= len(result) <= 50:
        raise Denied('plan_content_page_size')
    return result


def card_text(view, expires):
    ref = view['reference']
    return (f'Принять содержание плана №{ref["request_id"].rsplit(":", 1)[1]}, версия {ref["plan_version"]}?\n'
            f'Снимок: {view["snapshot_digest"]}.\nSource: {ref["source_revision"]}.\n'
            f'AI Commander; настройки {ref["setup_version"]}; объявленная ревизия репозитория '
            f'{ref["declared_repository_revision"]} (доступ не проверен).\n'
            f'До {datetime.fromtimestamp(expires, timezone.utc).isoformat()} (UTC).\n'
            'Все части плана выше должны быть доставлены. Принятие фиксирует содержание; '
            'оно не разрешает AI-расходы, запуск кода, доступы, merge или deployment.')


def issue(bridge, session, iid):
    row, received = receipt(bridge, session, iid, 'plan_accept_request')
    issued = int(datetime.fromisoformat(received.event['time']).timestamp())
    now = int(bridge.store.now(session).timestamp())
    if not issued <= now < issued + SECONDS:
        return bridge.finish(session, iid, 'Запрос подтверждения устарел. Повторите /plan_accept номер.')
    rid = bridge.profile + ':' + row.intent['number']
    try:
        view = preview_locked(bridge.store, session, rid)
    except Denied as error:
        if str(error) not in {'plan_acceptance_not_ready', 'plan_acceptance_command_center_only', 'saved_request_not_found'}:
            raise
        return bridge.finish(session, iid, 'Принятие недоступно: нужен текущий план AI Commander без вопросов '
            'и заполненные настройки проекта. Задача не создана.')
    page_receipts = []
    for index, text in enumerate(pages(bridge, view), 1):
        bridge.check_text(text)
        oid = bridge.enqueue(session, iid + ':plan-page:' + str(index), text)
        page_receipts.append({'delivery_id': oid, 'request_hash': digest({'chat_id': bridge.owner, 'text': text})})
    token = secrets.token_urlsafe(24)
    text = card_text(view, issued + SECONDS)
    bridge.check_text(text)
    oid = bridge.finish(session, iid, text, keyboard(token))
    body = {'chat_id': bridge.owner, 'text': text, 'reply_markup': keyboard(token)}
    if len(canonical(body).encode()) > 8192:
        raise Denied('plan_content_card_size')
    bridge.store.audit(session, ISSUED, 'owner', profile=bridge.profile, inbox_id=iid,
        request_id=rid, snapshot_digest=view['snapshot_digest'], pages=page_receipts,
        delivery_id=oid, request_hash=digest(body), card=hashlib.sha256(token.encode()).hexdigest(),
        owner_id=bridge.owner, connection_digest=getattr(bridge.client, 'approved', bridge.profile),
        issued_at=issued, expires_at=issued + SECONDS)


def observed(session, oid, expected, profile, owner, revision, message_id=None):
    row = session.get(TelegramDelivery, oid)
    if (not row or row.profile != profile or row.state != 'SENT'
            or type(row.message_id) is not int or row.message_id <= 0
            or message_id is not None and row.message_id != message_id
            or row.body.get('chat_id') != owner or digest(row.body) != expected
            or not session.scalar(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_delivery_queued',
                Audit.event['actor'].as_string() == 'system', Audit.event['revision'].as_string() == revision,
                Audit.event['delivery_id'].as_string() == oid,
                Audit.event['request_hash'].as_string() == expected).limit(1))
            or not session.scalar(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_delivery_observed',
                Audit.event['actor'].as_string() == 'system', Audit.event['revision'].as_string() == revision,
                Audit.event['delivery_id'].as_string() == oid,
                Audit.event['message_id'].as_integer() == row.message_id,
                Audit.event['state'].as_string() == 'SENT').limit(1))):
        raise Denied('plan_content_delivery_not_observed')
    return row


def confirm(bridge, iid, intent):
    with bridge.store.transaction() as session:
        bridge.guard()
        bridge.store.check_audit(session)
        if done(bridge, session, iid, intent):
            return
        row, _ = receipt(bridge, session, iid, 'plan_accept_confirm')
        if row.intent != intent:
            raise Denied('plan_content_receipt_invalid')
        issued = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == ISSUED,
            Audit.event['actor'].as_string() == 'owner', Audit.event['profile'].as_string() == bridge.profile,
            Audit.event['card'].as_string() == intent['card']).limit(1))
        if issued is None:
            raise Denied('plan_content_card_unknown')
        e = issued.event
        try:
            if not all(isinstance(e.get(k), str) for k in ('inbox_id', 'request_id', 'snapshot_digest',
                    'delivery_id', 'request_hash', 'card', 'connection_digest', 'revision', 'profile', 'time')):
                raise ValueError()
            origin = session.get(TelegramInbox, e['inbox_id'])
            if (set(e) != {'kind', 'actor', 'task_id', 'time', 'revision', 'profile', 'inbox_id', 'request_id',
                           'snapshot_digest', 'pages', 'delivery_id', 'request_hash', 'card', 'owner_id',
                           'connection_digest', 'issued_at', 'expires_at'}
                    or e['task_id'] is not None or datetime.fromisoformat(e['time']).tzinfo is None
                    or e['revision'] != bridge.store.settings.source_revision
                    or e['owner_id'] != bridge.owner or type(e['owner_id']) is not int
                    or e['connection_digest'] != getattr(bridge.client, 'approved', bridge.profile)
                    or not e['request_id'].startswith(bridge.profile + ':')
                    or type(e['issued_at']) is not int or type(e['expires_at']) is not int
                    or e['expires_at'] != e['issued_at'] + SECONDS
                    or e['delivery_id'] != digest({'profile': bridge.profile, 'event': e['inbox_id'] + ':reply'})
                    or not origin or origin.profile != bridge.profile or origin.state != 'DONE'
                    or origin.task_id is not None or origin.fingerprint != digest(origin.intent)
                    or origin.intent != {'kind': 'plan_accept_request', 'number': e['request_id'].rsplit(':', 1)[1]}):
                raise ValueError()
            anchor = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_update_received',
                Audit.event['actor'].as_string() == 'owner', Audit.event['profile'].as_string() == bridge.profile,
                Audit.event['update_id'].as_string() == e['inbox_id'].removeprefix(bridge.profile + ':'),
                Audit.event['intent_hash'].as_string() == origin.fingerprint,
                Audit.event['revision'].as_string() == e['revision']).limit(1))
            if not anchor or int(datetime.fromisoformat(anchor.event['time']).timestamp()) != e['issued_at']:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise Denied('plan_content_card_binding_invalid') from None
        used = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == CONSUMED,
            Audit.event['profile'].as_string() == bridge.profile, Audit.event['card'].as_string() == intent['card']).limit(1))
        if used:
            return bridge.finish(session, iid, 'Это подтверждение содержания уже использовано. Новый запуск не создан.')
        now = int(bridge.store.now(session).timestamp())
        if not e['issued_at'] <= now < e['expires_at']:
            return bridge.finish(session, iid, 'Карточка принятия устарела. Повторите /plan_accept номер.')
        try:
            view = preview_locked(bridge.store, session, e['request_id'])
        except Denied as error:
            if str(error) not in {'plan_acceptance_not_ready', 'plan_acceptance_command_center_only'}:
                raise
            return bridge.finish(session, iid, 'План или его условия изменились. Принятие не сохранено. '
                'Подготовьте текущий план и запросите новую карточку: /plan_accept номер.')
        if view['snapshot_digest'] != e['snapshot_digest']:
            return bridge.finish(session, iid, 'Снимок плана изменился. Принятие не сохранено. '
                'Запросите новую карточку: /plan_accept номер.')
        content = pages(bridge, view)
        expected_pages = [{'delivery_id': digest({'profile': bridge.profile,
            'event': e['inbox_id'] + ':plan-page:' + str(i)}),
            'request_hash': digest({'chat_id': bridge.owner, 'text': text})} for i, text in enumerate(content, 1)]
        if canonical(expected_pages) != canonical(e['pages']):
            raise Denied('plan_content_page_binding_invalid')
        try:
            for page in expected_pages:
                observed(session, page['delivery_id'], page['request_hash'], bridge.profile, bridge.owner, e['revision'])
            delivery = observed(session, e['delivery_id'], e['request_hash'], bridge.profile, bridge.owner,
                                e['revision'], intent['message_id'])
        except Denied:
            return bridge.finish(session, iid, 'Доставка всех частей этой карточки не подтверждена. '
                'Принятие не сохранено. Запросите новую карточку: /plan_accept номер.')
        if (not allowed_markup(delivery.body.get('reply_markup'))
                or parse_callback(delivery.body['reply_markup']['inline_keyboard'][0][0]['callback_data'])['card'] != intent['card']
                or delivery.body['text'] != card_text(view, e['expires_at'])):
            raise Denied('plan_content_card_binding_invalid')
        accepted = accept_locked(bridge.store, session, AcceptanceRequest(request_id=e['request_id'],
            expected_snapshot_digest=e['snapshot_digest']))
        if not e['issued_at'] <= int(bridge.store.now(session).timestamp()) < e['expires_at']:
            raise Denied('plan_content_card_expired')
        bridge.store.audit(session, CONSUMED, 'owner', profile=bridge.profile, card=intent['card'],
                           inbox_id=iid, snapshot_digest=accepted['snapshot_digest'])
        bridge.finish(session, iid, 'Содержание точной версии плана принято. Выполнение и расходы не разрешены. '
            f'Подготовка coding-спецификации: /coding_prepare {e["request_id"].rsplit(":", 1)[1]}.')
        bridge.guard()
        if not e['issued_at'] <= int(bridge.store.now(session).timestamp()) < e['expires_at']:
            raise Denied('plan_content_card_expired')
