import base64
import hashlib
import json
from pathlib import Path
import subprocess
from uuid import uuid4

import httpx
import pytest

from command_center.calendar_dialogue import extract
from command_center.google_script_calendar import envelope
from command_center.google_script_calendar_write import ScriptWriteHTTP, ScriptWriteProfile, REQUEST, RESPONSE, PROTOCOL
from command_center.store import Denied, digest

KEY = 'ab' * 32  # Public synthetic fixture only.


def profile(**changes):
    return ScriptWriteProfile(**({'enabled': True, 'create_enabled': True, 'owner_id': 123,
        'source_revision': 'a' * 40, 'deployment_id': 'public_synthetic_write_deployment',
        'connection_id': 'c' * 64, 'key_fingerprint': hashlib.sha256(bytes.fromhex(KEY)).hexdigest(),
        'calendar_id': 'synthetic@group.calendar.google.com', 'calendar_label': 'Jarvis'} | changes))


def document():
    return {'title': 'Встреча — тест 🙂', 'start': '2026-11-26T15:00:00+03:00',
        'end': '2026-11-26T15:30:00+03:00', 'timezone': 'Europe/Moscow',
        'note': '', 'telegram_reminder_minutes': 20}


def request(draft_id, action='create', doc=None):
    doc = doc or document()
    return {'protocol': PROTOCOL, 'connection': 'c' * 64, 'nonce': 'd' * 32, 'issued_at': 1000,
            'calendar_id': 'synthetic@group.calendar.google.com',
            'action': action, 'draft_id': draft_id, 'document_hash': digest(doc), 'document': doc}


def harness(envelopes, **kwargs):
    result = subprocess.run(['node', str(Path(__file__).with_name('calendar_create_harness.cjs'))],
        input=json.dumps({'envelopes': envelopes, **kwargs}), capture_output=True, text=True, encoding='utf-8', timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def decoded(signed):
    return json.loads(base64.b64decode(signed['payload']))


def test_bridge_replayed_create_uses_one_deterministic_event_and_no_invites():
    iid = str(uuid4())
    signed = envelope(request(iid), KEY, REQUEST)
    result = harness([signed, signed])
    assert result['writes'] == 1 and len(result['events']) == 1
    assert decoded(result['responses'][0])['event']['id'] == iid.replace('-', '')
    assert result['responses'][0] == result['responses'][1]


def test_lost_insert_response_can_be_read_back_without_second_write():
    iid = str(uuid4())
    first = harness([envelope(request(iid), KEY, REQUEST)], lose_response=True)
    assert first['writes'] == 1 and first['responses'] == [{'error': 'unavailable'}]
    second = harness([envelope(request(iid, 'get'), KEY, REQUEST)], events=first['events'])
    assert second['writes'] == 0 and decoded(second['responses'][0])['status'] == 'FOUND'


@pytest.mark.parametrize('attack', ['signature', 'connection', 'protocol', 'stale', 'hash', 'action',
                                  'extra', 'disabled', 'busy', 'invalid_date', 'calendar'])
def test_untrusted_requests_never_create_events(attack):
    r = request(str(uuid4()))
    options = {}
    if attack == 'connection':
        r['connection'] = 'e' * 64
    elif attack == 'protocol':
        r['protocol'] = 'jarvis-agenda-v1'
    elif attack == 'stale':
        r['issued_at'] = 0
    elif attack == 'hash':
        r['document_hash'] = 'e' * 64
    elif attack == 'action':
        r['action'] = 'delete'
    elif attack == 'extra':
        r['unexpected'] = 'extra'
    elif attack == 'calendar':
        r['calendar_id'] = 'another-calendar'
    elif attack in {'disabled', 'busy'}:
        options[attack] = True
    elif attack == 'invalid_date':
        r['document']['start'] = 'not a date'
        r['document_hash'] = digest(r['document'])
    signed = envelope(r, KEY, REQUEST)
    if attack == 'signature':
        signed['signature'] = '0' * 64
    result = harness([signed], **options)
    assert result['writes'] == 0 and result['responses'] == [{'error': 'unavailable'}]


def test_same_draft_with_changed_content_is_rejected_without_overwriting():
    iid = str(uuid4())
    other = {**document(), 'title': 'Changed'}
    result = harness([envelope(request(iid), KEY, REQUEST), envelope(request(iid, doc=other), KEY, REQUEST)])
    assert result['writes'] == 1 and result['responses'][1] == {'error': 'unavailable'}


def test_python_transport_accepts_only_the_bound_signed_bridge_event():
    state = {}
    calls = []

    def handle(req):
        nonlocal state
        body = json.loads(req.content)
        calls.append(decoded(body)['action'])
        result = harness([body], events=state)
        state = result['events']
        return httpx.Response(200, json=result['responses'][0])
    p = profile()
    client = ScriptWriteHTTP(p, digest(p.model_dump()), KEY, transport=httpx.MockTransport(handle), clock=lambda: 1000)
    iid = str(uuid4())
    assert client.create(iid, document()) == client.lookup(iid, document())
    assert calls == ['create', 'get'] and len(state) == 1
    client.close()
    with pytest.raises(Denied, match='closed'):
        client.lookup(iid, document())


@pytest.mark.parametrize('attack', ['signature', 'nonce', 'id', 'document', 'description', 'redirect', 'timeout'])
def test_python_transport_fails_closed_without_retry(attack):
    calls = []

    def handle(req):
        calls.append(1)
        if attack == 'timeout':
            raise httpx.ReadTimeout('private provider detail')
        if attack == 'redirect':
            return httpx.Response(302, headers={'location': 'https://evil.example/steal'})
        r = decoded(json.loads(req.content))
        signed = harness([json.loads(req.content)])['responses'][0]
        result = decoded(signed)
        if attack == 'nonce':
            result['nonce'] = 'e' * 32
        elif attack == 'id':
            result['event']['id'] = 'e' * 32
        elif attack == 'document':
            result['event']['summary'] = 'Changed'
        elif attack == 'description':
            result['event']['description'] = 'Changed'
        signed = envelope(result, KEY, RESPONSE)
        if attack == 'signature':
            signed['signature'] = '0' * 64
        assert r['action'] == 'create'
        return httpx.Response(200, json=signed)
    p = profile()
    client = ScriptWriteHTTP(p, digest(p.model_dump()), KEY, transport=httpx.MockTransport(handle), clock=lambda: 1000)
    with pytest.raises(Denied, match='result_unknown'):
        client.create(str(uuid4()), document())
    assert len(calls) == 1


def test_missing_meeting_fields_are_not_filled_by_parser():
    assert extract('Запиши мне завтра встречу.', initial=True) == {'date': 'завтра', 'title': 'Встреча'}
    assert extract('В 15:00 на 30 минут') == {'clock': '15:00', 'duration_minutes': 30}
    assert extract('Запиши завтра встречу в 15:00 на 1 час', initial=True)['duration_minutes'] == 60
    assert extract('Запиши завтра или послезавтра встречу', initial=True) == {'ambiguous': True}
    assert extract('Запиши 2026-02-30 встречу', initial=True) == {'ambiguous': True}
    assert extract('Прочитать книгу', initial=True) is None


def test_create_package_uses_owned_events_service_without_external_fetch_scope():
    manifest = json.loads((Path(__file__).parents[1] / 'infra/google-calendar-create/appsscript.json').read_text())
    assert manifest['oauthScopes'] == ['https://www.googleapis.com/auth/calendar.events.owned']
    assert manifest['dependencies']['enabledAdvancedServices'] == [
        {'userSymbol': 'Calendar', 'version': 'v3', 'serviceId': 'calendar'}]


def test_google_optional_timezone_and_utc_normalization_keep_exact_confirmed_instants():
    iid = str(uuid4())
    result = harness([envelope(request(iid), KEY, REQUEST)], normalize_times=True)
    event = decoded(result['responses'][0])['event']
    assert event['start'] == {'dateTime': document()['start'], 'timeZone': document()['timezone']}
    assert result['writes'] == 1


@pytest.mark.parametrize('attack', ['timezone', 'instant', 'reminder', 'private_hash', 'attendees', 'recurrence'])
def test_provider_event_changes_are_not_reported_as_exact_confirmation(attack):
    iid = str(uuid4())
    events = harness([envelope(request(iid), KEY, REQUEST)])['events']
    event = events[iid.replace('-', '')]
    if attack == 'timezone':
        event['start']['timeZone'] = 'Asia/Almaty'
    elif attack == 'instant':
        event['start']['dateTime'] = '2026-11-26T16:00:00+03:00'
    elif attack == 'reminder':
        event['reminders']['overrides'][0]['minutes'] = 10
    elif attack == 'private_hash':
        event['extendedProperties']['private']['commanderDocumentHash'] = '0' * 64
    elif attack == 'attendees':
        event['attendees'] = [{'email': 'synthetic@example.com'}]
    else:
        event['recurrence'] = ['RRULE:FREQ=DAILY']
    result = harness([envelope(request(iid, 'get'), KEY, REQUEST)], events=events)
    assert result['writes'] == 0 and result['responses'] == [{'error': 'unavailable'}]
