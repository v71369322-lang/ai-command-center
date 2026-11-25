"""Owner readback and confirmation for trusted voice transcripts."""

import re
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from .models import Audit, Control, TelegramDelivery, TelegramInbox
from .store import Denied, canonical, digest
from .telegram_requests import capture_receipt
from .telegram_voice_requests import INTAKE, verify_transcript

PROPOSED = 'telegram_voice_transcript_proposed'
ACCEPTED = 'telegram_voice_transcript_accepted'
DECIDED = 'telegram_voice_transcript_decided'
CORRECTED = 'telegram_voice_transcript_corrected'
TITLE = 'Расшифровка голосового поручения:'
EDIT_TITLE = 'Текст с вашей правкой:'
LABEL_ACCEPT = 'Сохранить запрос'
LABEL_REJECT = 'Удалить расшифровку'


def parse_edit(message):
    """Reply metadata only routes the message; observed delivery grants binding."""
    reply = message.get('reply_to_message')
    if not isinstance(reply, dict) or not isinstance(reply.get('text'), str):
        return None
    if reply['text'].split('\n', 1)[0] not in {TITLE, EDIT_TITLE}:
        return None
    if (type(reply.get('message_id')) is not int or reply['message_id'] <= 0
            or not isinstance(message.get('text'), str) or not message['text'].strip()):
        raise Denied('telegram_voice_edit_invalid')
    return {'kind': 'voice_edit', 'reply_message_id': reply['message_id'], 'text': message['text']}


def preview(value, *, corrected=False):
    return ((EDIT_TITLE if corrected else TITLE) + '\n\n' + value
            + '\n\nЧтобы исправить, ответьте на это сообщение полным правильным текстом.'
            '\nПроверьте имена, дату, время и место. Кнопка сохранит только запрос;'
            ' событие календаря, AI и выполнение не запускаются.')


def keyboard(proposal_id):
    return {'inline_keyboard': [[
        {'text': LABEL_ACCEPT, 'callback_data': f'vr:{proposal_id}:y'},
        {'text': LABEL_REJECT, 'callback_data': f'vr:{proposal_id}:n'},
    ]]}


def parse_callback(value):
    match = re.fullmatch(r'vr:([0-9a-f-]{36}):([yn])', value) if isinstance(value, str) else None
    if not match or len(value.encode()) > 64:
        raise Denied('telegram_voice_callback_invalid')
    return {'kind': 'voice_confirm', 'proposal_id': match[1], 'confirm': match[2] == 'y',
            'voice_callback': value}


def allowed_markup(value):
    try:
        intent = parse_callback(value['inline_keyboard'][0][0]['callback_data'])
        return canonical(value) == canonical(keyboard(intent['proposal_id']))
    except (Denied, KeyError, IndexError, TypeError):
        return False


def propose(bridge, voice_inbox_id, response, request, *, expected_epoch=None):
    """Import a verified transcript from a future trusted worker; no provider call."""
    transcript = verify_transcript(response, request)
    bridge.check_text(transcript['text'])
    proposal_id = str(uuid5(NAMESPACE_URL, 'acc:voice-transcript:' + voice_inbox_id))
    with bridge.store.transaction() as session:
        bridge.store.check_audit(session)
        if expected_epoch is not None:
            control = session.get(Control, 1)
            if control.halted or control.recovery or control.epoch != expected_epoch:
                raise Denied('control_blocked')
        source = session.get(TelegramInbox, voice_inbox_id)
        intake = session.execute(select(Audit).where(
            Audit.event['kind'].as_string() == INTAKE,
            Audit.event['profile'].as_string() == bridge.profile,
            Audit.event['inbox_id'].as_string() == voice_inbox_id)).first()
        if (not source or source.profile != bridge.profile or source.state != 'DONE'
                or source.intent.get('kind') != 'voice_request' or not intake
                or request.get('audio_sha256') != transcript['audio_sha256']):
            raise Denied('telegram_voice_transcript_source_invalid')
        existing = session.execute(select(Audit).where(
            Audit.event['kind'].as_string() == PROPOSED,
            Audit.event['profile'].as_string() == bridge.profile,
            Audit.event['proposal_id'].as_string() == proposal_id)).scalar_one_or_none()
        event = {'profile': bridge.profile, 'proposal_id': proposal_id, 'voice_inbox_id': voice_inbox_id,
                 'voice_fingerprint': source.fingerprint, 'audio_sha256': transcript['audio_sha256'],
                 'text': transcript['text'], 'text_hash': digest(transcript['text'])}
        if existing:
            if any(existing.event.get(key) != value for key, value in event.items()):
                raise Denied('telegram_voice_transcript_conflict')
            return {'proposal_id': proposal_id, 'delivery_id': existing.event['delivery_id']}
        text = preview(transcript['text'])
        delivery = bridge.enqueue(session, f'voice-transcript:{proposal_id}', text, keyboard(proposal_id))
        bridge.store.audit(session, PROPOSED, 'transcriber', **event, delivery_id=delivery,
                           confirmed=False, task_created=False, project_selected=False)
        return {'proposal_id': proposal_id, 'delivery_id': delivery}


def _proposal(bridge, session, intent):
    record = session.execute(select(Audit).where(
        Audit.event['kind'].as_string().in_((PROPOSED, CORRECTED)),
        Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['proposal_id'].as_string() == intent['proposal_id'])).scalar_one_or_none()
    if not record:
        raise Denied('telegram_voice_transcript_unknown')
    event = record.event
    delivery = session.get(TelegramDelivery, event.get('delivery_id'))
    observed = delivery and session.execute(select(Audit).where(
        Audit.event['kind'].as_string() == 'telegram_delivery_observed',
        Audit.event['delivery_id'].as_string() == delivery.id,
        Audit.event['message_id'].as_integer() == intent['message_id'],
        Audit.event['state'].as_string() == 'SENT')).first()
    source = session.get(TelegramInbox, event.get('voice_inbox_id'))
    if (not delivery or delivery.profile != bridge.profile or delivery.state != 'SENT'
            or delivery.message_id != intent['message_id'] or not observed
            or canonical(delivery.body.get('reply_markup')) != canonical(keyboard(intent['proposal_id']))
            or not source or source.profile != bridge.profile or source.intent.get('kind') != 'voice_request'
            or source.fingerprint != digest(source.intent) or source.fingerprint != event.get('voice_fingerprint')
            or event.get('text_hash') != digest(event.get('text'))):
        raise Denied('telegram_voice_transcript_card_invalid')
    if event['kind'] == CORRECTED:
        edited = session.get(TelegramInbox, event.get('owner_inbox_id'))
        anchored = edited and session.scalar(select(Audit.sequence).where(
            Audit.event['kind'].as_string() == 'telegram_update_received',
            Audit.event['actor'].as_string() == 'owner',
            Audit.event['profile'].as_string() == bridge.profile,
            Audit.event['update_id'].as_string() == edited.id.removeprefix(bridge.profile + ':'),
            Audit.event['intent_hash'].as_string() == edited.fingerprint).limit(1))
        if (event.get('actor') != 'owner' or not edited or not anchored or edited.state != 'DONE'
                or edited.profile != bridge.profile or edited.fingerprint != digest(edited.intent)
                or edited.fingerprint != event.get('owner_fingerprint')
                or edited.intent.get('kind') != 'voice_edit' or edited.intent.get('text') != event['text']):
            raise Denied('telegram_voice_correction_integrity')
    bridge.check_text(event['text'])
    return event


def _family(session, profile, proposal):
    return select(Audit.event['proposal_id'].as_string()).where(
        Audit.event['kind'].as_string().in_((PROPOSED, CORRECTED)),
        Audit.event['profile'].as_string() == profile,
        Audit.event['voice_inbox_id'].as_string() == proposal['voice_inbox_id'])


def _closed_or_stale(bridge, session, iid, proposal):
    family = _family(session, bridge.profile, proposal)
    previous = session.scalar(select(Audit.sequence).where(
        Audit.event['kind'].as_string().in_((DECIDED, ACCEPTED)),
        Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['proposal_id'].as_string().in_(family)).limit(1))
    if previous is not None:
        bridge.finish(session, iid, 'Эта расшифровка уже обработана. Повторный запрос не создан.')
        return True
    latest = session.scalar(select(Audit.event['proposal_id'].as_string()).where(
        Audit.event['kind'].as_string().in_((PROPOSED, CORRECTED)),
        Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['voice_inbox_id'].as_string() == proposal['voice_inbox_id'])
        .order_by(Audit.sequence.desc()).limit(1))
    if latest != proposal['proposal_id']:
        bridge.finish(session, iid, 'Текст уже исправлен. Используйте последнюю карточку с вашей правкой.'
                      ' Запрос не создан.')
        return True
    return False


def edit(bridge, iid, intent):
    """Owner replacement is a new proposal, never a rewritten model transcript."""
    with bridge.store.transaction() as session:
        bridge.guard()
        bridge.store.check_audit(session)
        row = session.get(TelegramInbox, iid)
        if row.state == 'DONE':
            return
        if row.state != 'RECEIVED' or row.intent != intent:
            raise Denied('telegram_voice_edit_not_pending')
        delivery = session.scalar(select(TelegramDelivery).where(
            TelegramDelivery.profile == bridge.profile,
            TelegramDelivery.message_id == intent['reply_message_id'], TelegramDelivery.state == 'SENT'))
        record = delivery and session.scalar(select(Audit).where(
            Audit.event['kind'].as_string().in_((PROPOSED, CORRECTED)),
            Audit.event['profile'].as_string() == bridge.profile,
            Audit.event['delivery_id'].as_string() == delivery.id))
        if not record:
            bridge.finish(session, iid, 'Не удалось связать ответ с карточкой расшифровки.'
                          ' Ответьте на сообщение бота с текстом расшифровки. Запрос не создан.')
            return
        proposal = _proposal(bridge, session, {'proposal_id': record.event['proposal_id'],
                                             'message_id': intent['reply_message_id']})
        if _closed_or_stale(bridge, session, iid, proposal):
            return
        bridge.check_text(intent['text'])
        if intent['text'] == proposal['text']:
            bridge.finish(session, iid, 'Текст совпадает с карточкой. Новая версия не создана;'
                          ' сохраните запрос кнопкой в последней карточке.')
            return
        proposal_id = str(uuid5(NAMESPACE_URL, 'acc:voice-correction:' + iid))
        delivery_id = bridge.finish(session, iid, preview(intent['text'], corrected=True), keyboard(proposal_id))
        bridge.store.audit(session, CORRECTED, 'owner', profile=bridge.profile, proposal_id=proposal_id,
            previous_proposal_id=proposal['proposal_id'], voice_inbox_id=proposal['voice_inbox_id'],
            voice_fingerprint=proposal['voice_fingerprint'], audio_sha256=proposal['audio_sha256'],
            text=intent['text'], text_hash=digest(intent['text']), owner_inbox_id=iid,
            owner_fingerprint=row.fingerprint, delivery_id=delivery_id,
            confirmed=False, task_created=False, project_selected=False)


def decide(bridge, iid, intent):
    with bridge.store.transaction() as session:
        bridge.store.check_audit(session)
        row = session.get(TelegramInbox, iid)
        if row.state in {'DONE', 'NEEDS_PLANNING'}:
            return
        if row.state != 'RECEIVED':
            raise Denied('telegram_voice_confirmation_not_pending')
        proposal = _proposal(bridge, session, intent)
        # All corrected cards share the same one-save boundary as the raw ASR.
        if _closed_or_stale(bridge, session, iid, proposal):
            return
        bridge.store.audit(session, DECIDED, 'owner', profile=bridge.profile,
                           proposal_id=intent['proposal_id'], confirmed=intent['confirm'])
        if not intent['confirm']:
            bridge.finish(session, iid, 'Расшифровка отклонена. Запрос, AI и исполнитель не создавались.')
            return
        row.state = 'NEEDS_PLANNING'
        bridge.store.audit(session, ACCEPTED, 'owner', profile=bridge.profile, proposal_id=intent['proposal_id'],
                           request_id=iid, request_fingerprint=row.fingerprint,
                           text=proposal['text'], text_hash=proposal['text_hash'], task_created=False)
        from .calendar_dialogue import handle_locked
        source_received = session.get(TelegramInbox, proposal['voice_inbox_id']).created_at
        if handle_locked(bridge, session, iid, proposal['text'], received_at=source_received):
            return
        from .telegram_project_picker import keyboard as picker_keyboard, issue
        number = iid.rsplit(':', 1)[1]
        delivery = bridge.enqueue(session, iid + ':reply', capture_receipt(iid), picker_keyboard(number, 0))
        issue(bridge, session, delivery, number, 0)
