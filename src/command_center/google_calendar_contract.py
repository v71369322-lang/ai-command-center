"""Provider-neutral Google Calendar request/response contract; live HTTP is disabled."""

import re
from urllib.parse import quote

import httpx

from .calendar_drafts import validate
from .store import Denied, digest


def insert_request(calendar_id, draft_id, document):
    """Build a minimal insert request with a private idempotency binding."""
    document = validate(document)
    if (not isinstance(calendar_id, str) or not 1 <= len(calendar_id) <= 256
            or any(char in calendar_id for char in '\r\n\x00')
            or not isinstance(draft_id, str)
            or not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}', draft_id)):
        raise Denied('google_calendar_binding_invalid')
    document_hash = digest(document)
    body = {
        'summary': document['title'],
        'description': document['note'],
        'start': {'dateTime': document['start'], 'timeZone': document['timezone']},
        'end': {'dateTime': document['end'], 'timeZone': document['timezone']},
        'attendees': [],
        'guestsCanInviteOthers': False,
        'guestsCanModify': False,
        'guestsCanSeeOtherGuests': False,
        'reminders': {'useDefault': False, 'overrides': [
            {'method': 'popup', 'minutes': document['telegram_reminder_minutes']},
        ]},
        'extendedProperties': {'private': {
            'commanderDraftId': draft_id,
            'commanderDocumentHash': document_hash,
        }},
    }
    return {'method': 'POST',
            'path': '/calendar/v3/calendars/' + quote(calendar_id, safe='') + '/events',
            'query': {'sendUpdates': 'none', 'supportsAttachments': 'false'},
            'body': body, 'document_hash': document_hash}


def reconciliation_request(calendar_id, draft_id):
    """Build the read-before-retry lookup for an unknown insert outcome."""
    if (not isinstance(calendar_id, str) or not 1 <= len(calendar_id) <= 256
            or any(char in calendar_id for char in '\r\n\x00')
            or not isinstance(draft_id, str)
            or not re.fullmatch(r'[0-9a-f-]{36}', draft_id)):
        raise Denied('google_calendar_binding_invalid')
    return {'method': 'GET', 'path': '/calendar/v3/calendars/' + quote(calendar_id, safe='') + '/events',
            'query': {'privateExtendedProperty': 'commanderDraftId=' + draft_id,
                      'maxResults': '2', 'showDeleted': 'false', 'singleEvents': 'true'}}


def verify_event(response, draft_id, document):
    """Accept only the exact confirmed event created for this local draft."""
    document = validate(document)
    private = response.get('extendedProperties', {}).get('private', {}) if isinstance(response, dict) else {}
    if (not isinstance(response, dict)
            or not isinstance(response.get('id'), str) or not re.fullmatch(r'[a-z0-9]{5,1024}', response['id'])
            or not isinstance(response.get('etag'), str) or not 3 <= len(response['etag']) <= 512
            or response.get('status') != 'confirmed'
            or response.get('summary') != document['title']
            or response.get('start') != {'dateTime': document['start'], 'timeZone': document['timezone']}
            or response.get('end') != {'dateTime': document['end'], 'timeZone': document['timezone']}
            or private != {'commanderDraftId': draft_id,
                            'commanderDocumentHash': digest(document)}):
        raise Denied('google_calendar_response_binding_invalid')
    return {'event_id': response['id'], 'etag': response['etag'],
            'document_hash': digest(document), 'status': 'SYNCED'}


class MockGoogleCalendarHTTP:
    """Exercise exact Google shapes without credentials or network access."""

    def __init__(self, transport):
        if not isinstance(transport, httpx.MockTransport):
            raise ValueError('google_calendar_live_transport_disabled')
        self.client = httpx.Client(transport=transport, base_url='https://www.googleapis.com',
                                   timeout=5, trust_env=False)

    def call(self, request):
        if request.get('method') not in {'GET', 'POST'} or not isinstance(request.get('path'), str):
            raise Denied('google_calendar_request_invalid')
        response = self.client.request(request['method'], request['path'], params=request.get('query'),
                                       json=request.get('body'))
        if len(response.content) > 65536:
            raise Denied('google_calendar_response_too_large')
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise Denied('google_calendar_response_invalid')
        return value

    def close(self):
        self.client.close()
