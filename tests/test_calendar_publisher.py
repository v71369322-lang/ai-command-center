from uuid import uuid4

import httpx

from command_center.calendar_drafts import create, decide
from command_center.calendar_publisher import CalendarPublisher
from command_center.calendar_sync import configure_binding, prepare_sync
from command_center.google_calendar_contract import insert_request
from command_center.store import digest


def setup(store):
    document = {'title': 'Созвон', 'start': '2026-11-03T15:00:00+05:00',
                'end': '2026-11-03T15:30:00+05:00', 'timezone': 'Asia/Almaty',
                'note': '', 'telegram_reminder_minutes': 20}
    draft = create(store, 'owner', document, str(uuid4()), digest('source'))
    decide(store, 'owner', draft['id'], 1, str(uuid4()), True)
    binding = {'enabled': True, 'calendar_id': 'commander@example.com',
               'credential_fingerprint': 'a' * 64}
    configure_binding(store, 'owner', binding, 0, str(uuid4()))
    prepare_sync(store, 'owner', draft['id'], str(uuid4()))
    return draft, binding


def provider_response(draft, binding):
    body = insert_request(binding['calendar_id'], draft['id'], draft['document'])['body']
    return {'id': 'commander12345', 'etag': '"etag"', 'status': 'confirmed',
            'summary': body['summary'], 'start': body['start'], 'end': body['end'],
            'extendedProperties': body['extendedProperties']}


def test_publisher_records_exact_success_once(store):
    draft, binding = setup(store)

    class Client:
        def call(self, request):
            assert request['query']['sendUpdates'] == 'none'
            return provider_response(draft, binding)

    state = CalendarPublisher(store, Client()).publish(draft['id'], str(uuid4()))
    assert state['state'] == 'SYNCED' and state['event_id'] == 'commander12345'


def test_lost_response_becomes_unknown_without_retry(store):
    draft, _ = setup(store)

    class Client:
        def call(self, request):
            raise httpx.ReadTimeout('fixture timeout')

    state = CalendarPublisher(store, Client()).publish(draft['id'], str(uuid4()))
    assert state['state'] == 'UNKNOWN'


def test_definite_http_rejection_is_terminal_and_body_is_not_recorded(store):
    draft, _ = setup(store)

    class Client:
        def call(self, request):
            response = httpx.Response(403, request=httpx.Request('POST', 'https://www.googleapis.com'))
            raise httpx.HTTPStatusError('secret provider body', request=response.request, response=response)

    state = CalendarPublisher(store, Client()).publish(draft['id'], str(uuid4()))
    assert state['state'] == 'FAILED' and state['error_code'] == 'http_403'
