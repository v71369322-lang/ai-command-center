"""Owner-confirmed normal resume, composed with the existing locked F1 action."""
from datetime import datetime, timedelta
import hashlib
import re
import secrets

from sqlalchemy import select

from .models import Audit, Control, TelegramDelivery
from .store import Denied, canonical, digest

ISSUED = 'telegram_resume_card_issued'
CONSUMED = 'telegram_resume_card_consumed'
LABEL = 'Подтвердить снятие обычной остановки'
# Checkpoint projection tolerates only transport bookkeeping. Unknown events,
# tasks, permissions, budgets, control, security and project changes invalidate it.
TRANSPORT_EVENTS = {
    'telegram_update_received', 'telegram_update_rejected', 'telegram_pending_rejected',
    'telegram_delivery_queued', 'telegram_delivery_intent', 'telegram_delivery_observed',
    'telegram_delivery_uncertain', 'telegram_delivery_recovery_uncertain',
    'telegram_callback_ack_intent', 'telegram_callback_ack_result',
    'telegram_service_heartbeat', 'telegram_service_started', 'telegram_service_stopped',
    'telegram_poll_failed', ISSUED,
}


def parse_callback(value):
    if not isinstance(value, str) or not re.fullmatch(r'rs:[A-Za-z0-9_-]{32}', value):
        raise Denied('telegram_resume_callback_invalid')
    return {'kind': 'resume_confirm', 'card': hashlib.sha256(value[3:].encode()).hexdigest()}


def keyboard(token):
    return {'inline_keyboard': [[{'text': LABEL, 'callback_data': 'rs:' + token}]]}


def allowed_markup(value):
    try:
        data = value['inline_keyboard'][0][0]['callback_data']
        parse_callback(data)
        return canonical(value) == canonical(keyboard(data[3:]))
    except (Denied, KeyError, IndexError, TypeError):
        return False


def issue(bridge, session, iid):
    control = session.get(Control, 1)
    if control.recovery:
        return bridge.finish(session, iid, 'Остановка связана с восстановлением или безопасностью. '
                             'Снять её через Telegram нельзя; нужна отдельная сверка.')
    if not control.halted:
        return bridge.finish(session, iid, 'Обычная остановка уже снята. Ничего не изменено.')
    received = session.execute(select(Audit).where(
        Audit.event['kind'].as_string() == 'telegram_update_received',
        Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['update_id'].as_string() == iid.rsplit(':', 1)[1],
        Audit.event['intent_hash'].as_string() == digest({'kind': 'resume_request'}),
        Audit.event['revision'].as_string() == bridge.store.settings.source_revision)).scalar_one()
    expires = datetime.fromisoformat(received.event['time']) + timedelta(seconds=120)
    now = bridge.store.now(session)
    if not expires - timedelta(seconds=120) <= now < expires:
        return bridge.finish(session, iid, 'Запрос подтверждения истёк. Отправьте /resume заново.')
    head = session.execute(select(Audit).order_by(Audit.sequence.desc()).limit(1)).scalar_one()
    token = secrets.token_urlsafe(24)
    text = ('Снять обычную остановку для новых задач? Старые отменённые задачи не возобновятся. '
            'Это не разрешение платных AI-вызовов, CRM или публикации. '
            f'Эпоха {control.epoch}. Подтверждение действует до {expires.isoformat()}.')
    delivery = bridge.finish(session, iid, text, keyboard(token))
    bridge.store.audit(session, ISSUED, 'owner', profile=bridge.profile, delivery_id=delivery,
                       card=hashlib.sha256(token.encode()).hexdigest(), epoch=control.epoch,
                       connection_digest=getattr(bridge.client, 'approved', bridge.profile),
                       checkpoint={'sequence': head.sequence, 'digest': head.digest},
                       expires_at=expires.isoformat())
    return delivery


def confirm(bridge, session, iid, intent):
    card = session.execute(select(Audit).where(
        Audit.event['kind'].as_string() == ISSUED, Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['card'].as_string() == intent['card'])).scalar_one_or_none()
    if card is None:
        raise Denied('telegram_resume_card_not_issued')
    event = card.event
    delivery = session.get(TelegramDelivery, event['delivery_id'])
    if delivery is None:
        raise Denied('telegram_resume_card_not_observed')
    queued = session.execute(select(Audit).where(
        Audit.event['kind'].as_string() == 'telegram_delivery_queued',
        Audit.event['delivery_id'].as_string() == event['delivery_id'],
        Audit.event['request_hash'].as_string() == digest(delivery.body))).first()
    observed = session.execute(select(Audit).where(
        Audit.event['kind'].as_string() == 'telegram_delivery_observed',
        Audit.event['delivery_id'].as_string() == event['delivery_id'],
        Audit.event['message_id'].as_integer() == intent['message_id'],
        Audit.event['state'].as_string() == 'SENT')).first()
    if (delivery is None or delivery.profile != bridge.profile or delivery.state != 'SENT'
            or delivery.message_id != intent['message_id'] or delivery.body.get('chat_id') != bridge.owner
            or not queued or not observed or not allowed_markup(delivery.body.get('reply_markup'))
            or parse_callback(delivery.body['reply_markup']['inline_keyboard'][0][0]['callback_data'])['card'] != intent['card']):
        raise Denied('telegram_resume_card_not_observed')
    consumed = session.execute(select(Audit).where(
        Audit.event['kind'].as_string() == CONSUMED, Audit.event['card'].as_string() == intent['card'])).first()
    if consumed:
        return bridge.finish(session, iid, 'Это подтверждение уже использовано. Ничего не изменено.')
    # Source/card TTL and checkpoint are server evidence, never callback input.
    anchor = event['checkpoint']
    expires = datetime.fromisoformat(event['expires_at'])
    bridge.store.check_audit(session, anchor)
    later = session.execute(select(Audit).where(Audit.sequence > anchor['sequence']).order_by(Audit.sequence)).scalars().all()
    if (event['revision'] != bridge.store.settings.source_revision
            or event['connection_digest'] != getattr(bridge.client, 'approved', bridge.profile)
            or not expires - timedelta(seconds=120) <= bridge.store.now(session) < expires
            or any(row.event['kind'] not in TRANSPORT_EVENTS
                   or row.event['revision'] != bridge.store.settings.source_revision for row in later)):
        return bridge.finish(session, iid, 'Подтверждение устарело или состояние изменилось. '
                             'Остановка не снята этой командой. Отправьте /resume заново.')
    bridge.guard()
    head = session.execute(select(Audit).order_by(Audit.sequence.desc()).limit(1)).scalar_one()
    try:
        # Same exact F1 checks as HTTP resume, in this existing global lock.
        # Only the transport-only chain above is projected to the current head.
        bridge.store._resume_locked(session, 'owner', event['epoch'], head.digest)
    except Denied as error:
        if str(error) not in {'stale_or_recovery_resume', 'unreconciled_resume'}:
            raise
        return bridge.finish(session, iid, 'Снять остановку нельзя: нужна сверка состояния или завершение '
                             'восстановления. Выполнение не возобновлено этой командой.')
    # A slow guard/DB operation must not carry a confirmation past its window.
    # Raising here rolls the F1 mutation back, together with its audit event.
    if not expires - timedelta(seconds=120) <= bridge.store.now(session) < expires:
        raise Denied('telegram_resume_expired_during_commit')
    bridge.store.audit(session, CONSUMED, 'owner', profile=bridge.profile, card=intent['card'],
                       inbox_id=iid, checkpoint=anchor, epoch=event['epoch'])
    return bridge.finish(session, iid, 'Обычная остановка снята для новых разрешённых задач. '
                         'Старые задачи не перезапущены; платные вызовы и дополнительные права не разрешены.')
