"""Explicit personal-calendar access; no browser session or developer authority."""
import base64
import hashlib
import json
import re
from datetime import datetime
from urllib.parse import quote, urlencode, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from .google_calendar_contract import insert_request, reconciliation_request
from .google_oauth_contract import AUTH_ENDPOINT
from .store import Denied, digest

READ_SCOPE = 'https://www.googleapis.com/auth/calendar.events.readonly'
WRITE_SCOPE = 'https://www.googleapis.com/auth/calendar.app.created'
SCOPES = (READ_SCOPE, WRITE_SCOPE)
ORIGIN = 'https://www.googleapis.com'


def desktop_authorization(client_id, redirect_uri, state, verifier):
    """Desktop PKCE callback accepts only an explicit IPv4 loopback listener."""
    try:
        uri = urlsplit(redirect_uri)
        valid = (uri.scheme == 'http' and uri.hostname == '127.0.0.1'
                 and uri.netloc == f'127.0.0.1:{uri.port}' and 1024 <= uri.port <= 65535
                 and uri.path == '/oauth/google/callback' and not uri.query and not uri.fragment)
    except (ValueError, TypeError):
        valid = False
    if (not valid or not isinstance(client_id, str)
            or not re.fullmatch(r'[A-Za-z0-9._-]{20,170}\.apps\.googleusercontent\.com', client_id)
            or not isinstance(state, str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', state)
            or not isinstance(verifier, str) or not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}', verifier)):
        raise Denied('google_desktop_authorization_invalid')
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    return {'url': AUTH_ENDPOINT + '?' + urlencode({'client_id': client_id, 'redirect_uri': redirect_uri,
        'response_type': 'code', 'scope': ' '.join(SCOPES), 'access_type': 'offline',
        'include_granted_scopes': 'false', 'prompt': 'consent', 'state': state,
        'code_challenge': challenge, 'code_challenge_method': 'S256'}),
        'state_hash': digest(state), 'verifier_hash': digest(verifier)}


class CalendarAccess(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: int = Field(default=1, strict=True)
    enabled: StrictBool = False
    source_revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    owner_id: int = Field(strict=True, gt=0, lt=2**52, repr=False)
    # A secondary calendar created by this OAuth client, never "primary".
    calendar_id: str = Field(pattern=r'^[a-z0-9]{16,128}@group\.calendar\.google\.com$')
    timezone: str = 'Europe/Moscow'
    scopes: tuple[str, ...] = SCOPES

    @model_validator(mode='after')
    def bounded(self):
        if self.schema_version != 1 or self.scopes != SCOPES or self.timezone != 'Europe/Moscow':
            raise ValueError('google_personal_access_scope_invalid')
        return self


def _instant(value):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise Denied('google_agenda_interval_invalid') from None


class PersonalCalendarHTTP:
    """Injected token custody; exact insert/reconcile plus bounded primary agenda.

    Construction does not authorize publishing a draft: CalendarPublisher and
    calendar_sync still enforce the existing durable owner-confirmed intent.
    No automatic retry, redirects, PATCH, DELETE, invitation or arbitrary URL.
    """
    def __init__(self, profile, approved_profile, token_provider, *, transport=None):
        self.profile = CalendarAccess.model_validate(profile.model_dump())
        if not self.profile.enabled or digest(self.profile.model_dump()) != approved_profile:
            raise Denied('google_exact_access_approval_required')
        if not callable(token_provider) or (transport is not None and not isinstance(transport, httpx.MockTransport)):
            raise Denied('google_credential_provider_required')
        self._token_provider = token_provider
        self.client = httpx.Client(base_url=ORIGIN, transport=transport, follow_redirects=False,
            trust_env=False, timeout=10, limits=httpx.Limits(max_connections=1))

    def __repr__(self):
        return '<PersonalCalendarHTTP credentials=redacted>'

    def _send(self, request):
        token = self._token_provider()
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9._~+/-]{20,4096}', token):
            raise Denied('google_access_token_invalid')
        try:
            with self.client.stream(request['method'], request['path'], params=request['query'],
                    json=request.get('body'), headers={'Authorization': 'Bearer ' + token}) as response:
                data = bytearray()
                for chunk in response.iter_bytes(8192):
                    data.extend(chunk)
                    if len(data) > 65536:
                        raise Denied('google_calendar_response_too_large')
                if response.status_code >= 300:
                    # Preserve definite rejection semantics without retaining
                    # credentials or Google's possibly private response body.
                    if response.status_code < 400:
                        raise Denied('google_calendar_redirect_forbidden')
                    safe = httpx.Response(response.status_code,
                        request=httpx.Request(request['method'], ORIGIN + request['path']))
                    safe.raise_for_status()
                value = json.loads(data)
                if not isinstance(value, dict):
                    raise ValueError()
                return value
        except httpx.TimeoutException:
            raise httpx.TimeoutException('google_calendar_timeout') from None
        except httpx.TransportError:
            raise httpx.TransportError('google_calendar_transport_failed') from None
        except (ValueError, UnicodeError):
            raise Denied('google_calendar_response_invalid') from None

    def call(self, request):
        """Same interface as the existing mock publisher client, strict wire shape."""
        try:
            if request['method'] == 'POST':
                body = request['body']
                draft_id = body['extendedProperties']['private']['commanderDraftId']
                document = {'title': body['summary'], 'note': body['description'],
                    'start': body['start']['dateTime'], 'end': body['end']['dateTime'],
                    'timezone': body['start']['timeZone'],
                    'telegram_reminder_minutes': body['reminders']['overrides'][0]['minutes']}
                exact = insert_request(self.profile.calendar_id, draft_id, document)
            elif request['method'] == 'GET':
                prefix = 'commanderDraftId='
                item = request['query']['privateExtendedProperty']
                if not item.startswith(prefix):
                    raise ValueError()
                exact = reconciliation_request(self.profile.calendar_id, item[len(prefix):])
            else:
                raise ValueError()
            if request != exact:
                raise ValueError()
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise Denied('google_calendar_request_scope_changed') from None
        return self._send(exact)

    def agenda(self, start, end):
        first, last = _instant(start), _instant(end)
        if first >= last or (last - first).total_seconds() > 31 * 86400:
            raise Denied('google_agenda_interval_invalid')
        # Read-only scope covers primary; writes are separately pinned above.
        path = '/calendar/v3/calendars/' + quote('primary', safe='') + '/events'
        result = self._send({'method': 'GET', 'path': path, 'query': {
            'timeMin': start, 'timeMax': end, 'timeZone': self.profile.timezone,
            'maxResults': '50', 'singleEvents': 'true', 'orderBy': 'startTime',
            'showDeleted': 'false', 'fields': 'summary,timeZone,items(id,status,summary,start,end),nextPageToken'}})
        rows = result.get('items', [])
        if not isinstance(rows, list) or len(rows) > 50 or any(not isinstance(row, dict) for row in rows):
            raise Denied('google_agenda_response_invalid')
        # Ignore unsolicited private fields even when a provider ignores fields=.
        rows = [{key: row[key] for key in ('id', 'status', 'summary', 'start', 'end') if key in row}
                for row in rows]
        for row in rows:
            for key in ('start', 'end'):
                if key in row:
                    if not isinstance(row[key], dict):
                        raise Denied('google_agenda_response_invalid')
                    row[key] = {name: row[key][name] for name in ('date', 'dateTime', 'timeZone')
                                if name in row[key]}
        return {'events': rows, 'timezone': self.profile.timezone, 'start': start, 'end': end,
                'truncated': bool(result.get('nextPageToken')), 'source': 'Google Calendar'}

    def close(self):
        self.client.close()
