import json
from uuid import uuid4

import httpx
import pytest

from command_center.google_calendar_contract import (MockGoogleCalendarHTTP, insert_request,
                                                       reconciliation_request, verify_event)
from command_center.store import Denied


def document():
    return {'title': 'Созвон по проекту', 'start': '2026-11-03T15:00:00+05:00',
            'end': '2026-11-03T15:30:00+05:00', 'timezone': 'Asia/Almaty',
            'note': 'Короткая пометка', 'telegram_reminder_minutes': 20}


def response_for(request, draft_id):
    body = request['body']
    return {'id': 'commander12345', 'etag': '"fixture-etag"', 'status': 'confirmed',
            'summary': body['summary'], 'start': body['start'], 'end': body['end'],
            'extendedProperties': {'private': body['extendedProperties']['private']}}


def test_insert_contract_has_no_attendees_and_exact_private_binding():
    draft_id = str(uuid4())
    request = insert_request('ai commander@example.com', draft_id, document())
    assert request['path'].endswith('/ai%20commander%40example.com/events')
    assert request['query'] == {'sendUpdates': 'none', 'supportsAttachments': 'false'}
    assert request['body']['attendees'] == []
    assert request['body']['extendedProperties']['private']['commanderDraftId'] == draft_id
    assert verify_event(response_for(request, draft_id), draft_id, document())['status'] == 'SYNCED'


def test_reconciliation_is_exact_and_bounded():
    draft_id = str(uuid4())
    request = reconciliation_request('calendar-id', draft_id)
    assert request == {'method': 'GET', 'path': '/calendar/v3/calendars/calendar-id/events',
                       'query': {'privateExtendedProperty': 'commanderDraftId=' + draft_id,
                                 'maxResults': '2', 'showDeleted': 'false', 'singleEvents': 'true'}}


@pytest.mark.parametrize('mutation', ['id', 'etag', 'status', 'title', 'time', 'binding'])
def test_mismatched_provider_response_fails_closed(mutation):
    draft_id = str(uuid4())
    request = insert_request('calendar-id', draft_id, document())
    response = response_for(request, draft_id)
    if mutation == 'id':
        response['id'] = '../bad'
    if mutation == 'etag':
        response['etag'] = ''
    if mutation == 'status':
        response['status'] = 'cancelled'
    if mutation == 'title':
        response['summary'] = 'Другое'
    if mutation == 'time':
        response['start']['dateTime'] = '2026-11-03T16:00:00+05:00'
    if mutation == 'binding':
        response['extendedProperties']['private']['commanderDraftId'] = str(uuid4())
    with pytest.raises(Denied, match='response_binding_invalid'):
        verify_event(response, draft_id, document())


def test_mock_transport_exercises_shape_without_live_http():
    draft_id = str(uuid4())
    request = insert_request('calendar-id', draft_id, document())

    def handler(http_request):
        assert http_request.url.host == 'www.googleapis.com'
        assert http_request.method == 'POST'
        assert 'sendUpdates=none' in str(http_request.url)
        assert json.loads(http_request.content)['attendees'] == []
        return httpx.Response(200, json=response_for(request, draft_id))

    client = MockGoogleCalendarHTTP(httpx.MockTransport(handler))
    assert verify_event(client.call(request), draft_id, document())['event_id'] == 'commander12345'
    client.close()
    with pytest.raises(ValueError, match='live_transport_disabled'):
        MockGoogleCalendarHTTP(httpx.HTTPTransport())
