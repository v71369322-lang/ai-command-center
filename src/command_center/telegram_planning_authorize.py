"""Observed owner review cards composed with existing Telegram delivery and F1 authority."""
from datetime import datetime, timezone
import hashlib
import re
import secrets

from sqlalchemy import select

from .models import Audit, Task, TelegramDelivery, TelegramInbox
from .planning_admission import PlanningQuote, prepare_review
from .planning_approval import CONFIRMATION, PlanningApproval
from .planning_profile import load
from .planning_task import check_context, request_key
from .project_inbox import check_content
from .request_planning import _context
from .store import Denied, canonical, digest
from .telegram_experiment import rub

ISSUED = 'telegram_planning_approval_issued'
CONSUMED = 'telegram_planning_approval_consumed'
LABEL = 'Подтвердить один AI-план'


def parse_callback(value):
    if not isinstance(value, str) or not re.fullmatch(r'pa:[A-Za-z0-9_-]{32}', value):
        raise Denied('planning_approval_callback_invalid')
    return {'kind': 'plan_authorize_confirm', 'card': hashlib.sha256(value[3:].encode()).hexdigest()}


def keyboard(token):
    return {'inline_keyboard': [[{'text': LABEL, 'callback_data': 'pa:' + token}]]}


def allowed_markup(value):
    try:
        token = value['inline_keyboard'][0][0]['callback_data']
        parse_callback(token)
        return canonical(value) == canonical(keyboard(token[3:]))
    except (Denied, KeyError, TypeError, IndexError):
        return False


def receipt(bridge, session, iid, kind):
    row = session.get(TelegramInbox, iid)
    if (not row or row.profile != bridge.profile or row.state != 'RECEIVED' or not isinstance(row.intent, dict)
            or row.intent.get('kind') != kind or row.fingerprint != digest(row.intent) or row.task_id is not None):
        raise Denied('planning_approval_receipt_invalid')
    anchor = session.scalar(select(Audit).where(
        Audit.event['kind'].as_string() == 'telegram_update_received',
        Audit.event['actor'].as_string() == 'owner', Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['update_id'].as_string() == iid.removeprefix(bridge.profile + ':'),
        Audit.event['intent_hash'].as_string() == row.fingerprint,
        Audit.event['revision'].as_string() == bridge.store.settings.source_revision).limit(1))
    if not anchor:
        raise Denied('planning_approval_receipt_invalid')
    return row, anchor


def issue(bridge, session, iid):
    row, received = receipt(bridge, session, iid, 'plan_authorize_request')
    now = int(bridge.store.now(session).timestamp())
    issued = int(datetime.fromisoformat(received.event['time']).timestamp())
    try:
        profile = load()
        if profile is None or not issued <= now < issued + 120:
            raise Denied('planning_review_unavailable')
        rid = bridge.profile + ':' + row.intent['number']
        snapshot = _context(bridge.store, session, rid)
        task = session.scalar(select(Task).where(Task.request_key == 'owner:' + request_key(snapshot)))
        if task is None or task.state != 'WAITING_APPROVAL':
            raise Denied('planning_task_not_waiting')
        bridge.store.check_task_revision(session, task)
        snapshot = check_context(bridge.store, session, task.payload)
        quote = prepare_review('owner', profile, snapshot, task_id=task.id,
            task_version=task.version, now=issued, seconds=120)
    except Denied:
        return bridge.finish(session, iid,
            'Карточка AI-плана недоступна: нужны подготовленная задача, открытый приём и '
            'проверенный профиль модели, тарифа и бюджета. Разрешение не выдано; AI не вызывался. '
            'Подготовка: /plan_prepare номер.')
    token = secrets.token_urlsafe(24)
    expires = datetime.fromtimestamp(quote.expires_at, timezone.utc).isoformat()
    body = (f'Один платный AI-план №{row.intent["number"]} (AI Commander).\n'
        f'Запрос: {snapshot.text}\nМодель: {quote.model}. Резерв: {rub(quote.maximum_nano_rub)}.\n'
        f'Задача: {task.id}; версия {task.version}.\nКонтекст: {quote.context_digest}.\n'
        f'Source: {quote.source_revision}.\nДо {expires} (UTC); срок не продлевается.\n'
        f'1 вызов; неизвестный итог — без повтора. Только черновик /plan {row.intent["number"]}, '
        'без выполнения и публикации. Сумма — расчёт по тарифу, не лимит списаний провайдера. '
        'AI сейчас не вызывается.')
    check_content(bridge.store, body)
    sensitive = getattr(bridge.client, 'sensitive', lambda value: False)
    if sensitive(body) or len(body) > 4096 or len(canonical({'chat_id': bridge.owner, 'text': body,
                                                          'reply_markup': keyboard(token)}).encode()) > 8192:
        return bridge.finish(session, iid, 'Карточка не помещается в безопасный формат. Разрешение не выдано.')
    delivery = bridge.finish(session, iid, body, keyboard(token))
    bridge.store.audit(session, ISSUED, 'owner', task.id, profile=bridge.profile, delivery_id=delivery,
        card=hashlib.sha256(token.encode()).hexdigest(), review=quote.model_dump(), review_digest=digest(quote.model_dump()),
        owner_id=bridge.owner,
        connection_digest=getattr(bridge.client, 'approved', bridge.profile))


def card(bridge, session, iid, intent):
    row, _ = receipt(bridge, session, iid, 'plan_authorize_confirm')
    if row.intent != intent:
        raise Denied('planning_approval_receipt_invalid')
    issued = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == ISSUED,
        Audit.event['actor'].as_string() == 'owner', Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['card'].as_string() == intent['card']).limit(1))
    if issued is None:
        raise Denied('planning_approval_card_unknown')
    event = issued.event
    try:
        quote = PlanningQuote.model_validate(event['review'])
        if (digest(quote.model_dump()) != event['review_digest'] or event['task_id'] != quote.task_id
                or event['revision'] != bridge.store.settings.source_revision
                or event['owner_id'] != bridge.owner
                or event['connection_digest'] != getattr(bridge.client, 'approved', bridge.profile)
                or not quote.request_id.startswith(bridge.profile + ':')):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise Denied('planning_approval_binding_invalid') from None
    observed_delivery(session, event, intent, bridge.profile, bridge.owner)
    used = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == CONSUMED,
        Audit.event['profile'].as_string() == bridge.profile, Audit.event['card'].as_string() == intent['card']).limit(1))
    return event, quote, used


def observed_delivery(session, event, intent, profile, owner):
    """Shared read-only proof of the exact display; also checked at live admission."""
    delivery = session.get(TelegramDelivery, event.get('delivery_id'))
    if (not delivery or delivery.profile != profile or delivery.state != 'SENT'
            or delivery.message_id != intent['message_id'] or delivery.body.get('chat_id') != owner
            or not allowed_markup(delivery.body.get('reply_markup'))
            or parse_callback(delivery.body['reply_markup']['inline_keyboard'][0][0]['callback_data'])['card'] != intent['card']
            or not session.scalar(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_delivery_queued',
                Audit.event['delivery_id'].as_string() == delivery.id,
                Audit.event['request_hash'].as_string() == digest(delivery.body)).limit(1))
            or not session.scalar(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_delivery_observed',
                Audit.event['delivery_id'].as_string() == delivery.id,
                Audit.event['message_id'].as_integer() == intent['message_id'],
                Audit.event['state'].as_string() == 'SENT').limit(1))):
        raise Denied('planning_approval_card_not_observed')


def done(bridge, session, iid, intent):
    row = session.get(TelegramInbox, iid)
    return (row is not None and row.profile == bridge.profile and row.state == 'DONE'
            and row.intent == intent and row.fingerprint == digest(intent))


def confirm(bridge, iid, intent):
    with bridge.store.transaction() as session:
        bridge.guard()
        bridge.store.check_audit(session)
        if done(bridge, session, iid, intent):
            return
        event, quote, used = card(bridge, session, iid, intent)
        if used:
            return bridge.finish(session, iid, 'Подтверждение уже использовано. Новый вызов не разрешён.')
    profile = load()
    if profile is None:
        raise Denied('planning_profile_not_connected')

    def consume(session, task):
        bridge.guard()
        actual, current, used = card(bridge, session, iid, intent)
        if used or actual != event or current != quote or task.id != quote.task_id:
            raise Denied('planning_approval_card_used_or_changed')
        current_profile = load()
        if current_profile is None or digest(current_profile.model_dump()) != quote.profile_digest:
            raise Denied('planning_approval_profile_changed')
        bridge.store.audit(session, CONSUMED, 'owner', task.id, profile=bridge.profile,
                           inbox_id=iid, card=intent['card'], review_digest=event['review_digest'])
        bridge.finish(session, iid, 'Точное разрешение на один AI-план сохранено. '
            f'Максимальный резерв: {rub(quote.maximum_nano_rub)}. '
            'AI этой командой не вызывался; результат ещё не получен. '
            'Изменения кода и публикация не разрешены.')
        bridge.guard()
        current_profile = load()
        if current_profile is None or digest(current_profile.model_dump()) != quote.profile_digest:
            raise Denied('planning_approval_profile_changed')

    try:
        return PlanningApproval(bridge.store, profile).authorize('owner', quote,
            expected_quote_digest=event['review_digest'], confirmation=CONFIRMATION, _scope_installer=consume)
    except Denied:
        with bridge.store.transaction() as session:
            bridge.guard()
            bridge.store.check_audit(session)
            if done(bridge, session, iid, intent):
                return
            _, _, used = card(bridge, session, iid, intent)
            if used:
                return bridge.finish(session, iid, 'Подтверждение уже использовано. Новый вызов не разрешён.')
        raise
