from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from command_center.attention_schedule import configure
from command_center.calendar_drafts import list_drafts
from command_center.calendar_sync import configure_binding, sync_state, claim_script_publication, prepare_sync
from command_center.calendar_script_publisher import publish
from command_center.models import Control, Audit, TelegramInbox
from command_center.store import Denied, digest
from command_center.telegram_bridge import MockTelegramHTTP, TelegramBridge
from command_center.google_script_calendar_write import ScriptWriteHTTP
from test_calendar_create_transport import profile, harness, KEY
from test_telegram_bridge import BotHTTP, OWNER, message
from test_telegram_calendar import callback


@pytest.fixture
def setup(store):
    fake = BotHTTP()
    client = MockTelegramHTTP(httpx.MockTransport(fake))
    p = profile(owner_id=OWNER, source_revision=store.settings.source_revision)
    provider = {'events': {}, 'calls': [], 'writes': 0, 'lose_response': False, 'unavailable': False}

    def handle(req):
        import json
        import base64
        body = json.loads(req.content)
        action = json.loads(base64.b64decode(body['payload']))['action']
        provider['calls'].append(action)
        if provider['unavailable']:
            raise httpx.ReadTimeout('synthetic response lost before insert')
        result = harness([body], events=provider['events'], lose_response=provider['lose_response'])
        provider['events'] = result['events']
        provider['writes'] += result['writes']
        return httpx.Response(200, json=result['responses'][0])
    writer = ScriptWriteHTTP(p, digest(p.model_dump()), KEY, transport=httpx.MockTransport(handle), clock=lambda: 1000)
    bridge = TelegramBridge(store, client, OWNER, calendar_writer=writer)
    configure(store, 'owner', {'enabled': True, 'timezone': 'Europe/Moscow',
        'report_times': ['09:00'], 'quiet_start': '23:00', 'quiet_end': '08:00'}, 0, str(uuid4()))
    configure_binding(store, 'owner', {'enabled': True, 'calendar_id': p.calendar_id,
        'credential_fingerprint': p.key_fingerprint}, 0, str(uuid4()))
    yield bridge, fake, provider
    writer.close()
    client.close()


def ready(service):
    service.receive(message(1, 'Запиши мне завтра встречу.'))
    service.receive(message(2, 'В 15:00 на 30 минут'))


def test_dialogue_has_no_effect_before_observed_confirmation_and_no_duplicates(setup, store):
    service, fake, provider = setup
    service.receive(message(1, 'Запиши мне завтра встречу.'))
    assert not list_drafts(store, 'owner') and provider['calls'] == []
    service.receive(message(2, 'В 15:00 на 30 минут'))
    drafts = list_drafts(store, 'owner')
    assert len(drafts) == 1 and drafts[0]['state'] == 'DRAFT'
    assert provider['calls'] == []
    service.receive(callback(service, fake, uid=3))
    assert provider['calls'] == ['create'] and provider['writes'] == 1
    service.receive(callback(service, fake, uid=4))
    assert provider['calls'] == ['create'] and provider['writes'] == 1
    with store.transaction() as session:
        assert sync_state(session, drafts[0]['id'])['state'] == 'SYNCED'
    assert store.snapshot()['tasks'] == []


def test_lost_response_reconciles_by_get_and_never_repeats_create(setup, store):
    service, fake, provider = setup
    ready(service)
    provider['lose_response'] = True
    service.receive(callback(service, fake, uid=3))
    assert provider['calls'] == ['create'] and provider['writes'] == 1
    provider['lose_response'] = False
    service.receive(callback(service, fake, uid=4))
    assert provider['calls'] == ['create', 'get'] and provider['writes'] == 1
    with store.transaction() as session:
        assert sync_state(session, list_drafts_locked_id(session))['state'] == 'SYNCED'


def list_drafts_locked_id(session):
    from command_center.calendar_drafts import list_drafts_locked
    return list_drafts_locked(session, 'owner')[0]['id']


def test_unknown_absent_does_not_authorize_reinsertion(setup, store):
    service, fake, provider = setup
    ready(service)
    provider['unavailable'] = True
    service.receive(callback(service, fake, uid=3))
    provider['unavailable'] = False
    service.receive(callback(service, fake, uid=4))
    assert provider['calls'] == ['create', 'get'] and provider['writes'] == 0
    with store.transaction() as session:
        assert sync_state(session, list_drafts_locked_id(session))['state'] == 'UNKNOWN'


@pytest.mark.parametrize('change', ['stop', 'epoch', 'profile', 'expired', 'binding', 'unobserved'])
def test_stale_or_forged_confirmation_cannot_write(setup, store, change):
    service, fake, provider = setup
    ready(service)
    command = callback(service, fake, uid=3)
    if change in {'stop', 'epoch', 'expired'}:
        with store.transaction() as session:
            if change == 'stop':
                session.get(Control, 1).halted = True
            elif change == 'epoch':
                session.get(Control, 1).epoch += 1
            else:
                row = session.scalars(select(Audit).where(Audit.event['kind'].as_string()
                    == 'telegram_calendar_card_issued')).one()
                # Tampering would fail full audit; use a future clock instead.
                assert row.event['expires_at']
        if change == 'expired':
            original = store.now
            store.now = lambda s: original(s) + timedelta(minutes=11)
    elif change == 'profile':
        service.calendar_writer.profile = service.calendar_writer.profile.model_copy(update={'calendar_label': 'Other'})
    elif change == 'binding':
        p = service.calendar_writer.profile
        configure_binding(store, 'owner', {'enabled': False, 'calendar_id': p.calendar_id,
            'credential_fingerprint': p.key_fingerprint}, 1, str(uuid4()))
    else:
        command['callback_query']['message']['message_id'] += 999
    with pytest.raises(Denied):
        service.receive(command)
    assert provider['calls'] == []


def test_cancel_is_terminal_without_network_or_binding_grant(setup, store):
    service, fake, provider = setup
    ready(service)
    service.receive(callback(service, fake, choice='n', uid=3))
    assert list_drafts(store, 'owner')[0]['state'] == 'CANCELLED'
    assert provider['calls'] == []


def test_restart_continuation_and_unrelated_idea_do_not_lose_date(setup, store):
    service, fake, provider = setup
    service.receive(message(1, 'Запиши мне завтра встречу.'))
    service.receive(message(2, 'Идея для кондитерской'))
    restarted = TelegramBridge(store, service.client, OWNER, calendar_writer=service.calendar_writer)
    restarted.receive(message(3, 'В 15:00 на 30 минут'))
    assert len(list_drafts(store, 'owner')) == 1 and provider['calls'] == []
    with store.transaction() as session:
        assert session.get(TelegramInbox, service.profile + ':2').state == 'NEEDS_PLANNING'


def test_new_dialogue_cancel_and_stop_cannot_create_local_draft(setup, store):
    service, fake, provider = setup
    service.receive(message(1, 'Запиши мне завтра встречу.'))
    service.receive(message(2, 'отмена'))
    service.receive(message(3, 'В 15:00 на 30 минут'))
    assert list_drafts(store, 'owner') == []
    with store.transaction() as session:
        session.get(Control, 1).halted = True
    service.receive(message(4, 'Запиши завтра встречу в 15:00 на 30 минут'))
    assert list_drafts(store, 'owner') == [] and provider['calls'] == []


def test_claim_survives_crash_before_send_and_requires_read_only_recovery(setup, store):
    service, fake, provider = setup
    ready(service)
    draft = list_drafts(store, 'owner')[0]
    from command_center.calendar_drafts import decide
    decide(store, 'owner', draft['id'], 1, str(uuid4()), True)
    prepare_sync(store, 'owner', draft['id'], str(uuid4()))
    p = service.calendar_writer.profile
    first = claim_script_publication(store, draft['id'], str(uuid4()), p.calendar_id, p.key_fingerprint)
    second = claim_script_publication(store, draft['id'], str(uuid4()), p.calendar_id, p.key_fingerprint)
    assert first['action'] == 'create' and second['action'] == 'get'
    publish(store, service.calendar_writer, draft['id'], str(uuid4()))
    assert provider['calls'] == ['get'] and provider['writes'] == 0


def test_voice_requires_readback_save_before_meeting_clarification(setup, store):
    from test_telegram_voice_requests import voice, transcript_callback
    from test_voice_worker import worker, Download, Decoder
    service, fake, provider = setup

    class MeetingDecoder(Decoder):
        def transcribe(self, audio):
            return {**super().transcribe(audio), 'text': 'Запиши мне завтра встречу.'}
    service.receive(voice())
    result = worker(service, Download(), MeetingDecoder()).process_one()
    assert provider['calls'] == [] and list_drafts(store, 'owner') == []
    service.receive(transcript_callback(service, fake, result['proposal_id']))
    assert provider['calls'] == [] and list_drafts(store, 'owner') == []
    service.receive(message(90, 'В 15:00 на 30 минут'))
    assert len(list_drafts(store, 'owner')) == 1 and provider['calls'] == []
