"""Owner readback and confirmation for trusted voice transcripts."""

import re
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from .models import Audit, TelegramDelivery, TelegramInbox
from .store import Denied, canonical, digest
from .telegram_requests import capture_receipt
from .telegram_voice_requests import INTAKE, verify_transcript

PROPOSED = 'telegram_voice_transcript_proposed'
ACCEPTED = 'telegram_voice_transcript_accepted'
LABEL_ACCEPT = 'Сохранить запрос'
LABEL_REJECT = 'Удалить расшифровку'


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


def propose(bridge, voice_inbox_id, response, request):
    """Import a verified transcript from a future trusted worker; no provider call."""
    transcript = verify_transcript(response, request)
    bridge.check_text(transcript['text'])
    proposal_id = str(uuid5(NAMESPACE_URL, 'acc:voice-transcript:' + voice_inbox_id))
    with bridge.store.transaction() as session:
        bridge.store.check_audit(session)
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
        text = ('Расшифровка голосового поручения:\n\n' + transcript['text']
                + '\n\nПроверьте текст. Сохранение создаст только запрос без запуска AI или проекта.')
        delivery = bridge.enqueue(session, f'voice-transcript:{proposal_id}', text, keyboard(proposal_id))
        bridge.store.audit(session, PROPOSED, 'transcriber', **event, delivery_id=delivery,
                           confirmed=False, task_created=False, project_selected=False)
        return {'proposal_id': proposal_id, 'delivery_id': delivery}


def _proposal(bridge, session, intent):
    record = session.execute(select(Audit).where(
        Audit.event['kind'].as_string() == PROPOSED,
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
            or not source or source.fingerprint != event.get('voice_fingerprint')
            or event.get('text_hash') != digest(event.get('text'))):
        raise Denied('telegram_voice_transcript_card_invalid')
    bridge.check_text(event['text'])
    return event


def decide(bridge, iid, intent):
    with bridge.store.transaction() as session:
        bridge.store.check_audit(session)
        row = session.get(TelegramInbox, iid)
        if row.state in {'DONE', 'NEEDS_PLANNING'}:
            return
        if row.state != 'RECEIVED':
            raise Denied('telegram_voice_confirmation_not_pending')
        proposal = _proposal(bridge, session, intent)
        if not intent['confirm']:
            bridge.finish(session, iid, 'Расшифровка отклонена. Запрос, AI и исполнитель не создавались.')
            return
        row.state = 'NEEDS_PLANNING'
        bridge.store.audit(session, ACCEPTED, 'owner', profile=bridge.profile, proposal_id=intent['proposal_id'],
                           request_id=iid, request_fingerprint=row.fingerprint,
                           text=proposal['text'], text_hash=proposal['text_hash'], task_created=False)
        from .telegram_project_picker import keyboard as picker_keyboard, issue
        number = iid.rsplit(':', 1)[1]
        delivery = bridge.enqueue(session, iid + ':reply', capture_receipt(iid), picker_keyboard(number, 0))
        issue(bridge, session, delivery, number, 0)
