from copy import deepcopy
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from command_center.google_calendar_access import (
    CalendarAccess, PersonalCalendarHTTP, SCOPES, desktop_authorization,
)
from command_center.google_calendar_contract import insert_request, reconciliation_request
from command_center.store import Denied, digest


def profile(**changes):
    return CalendarAccess(**({'enabled': True, 'source_revision': 'a' * 40,
        'owner_id': 123, 'calendar_id': 'a' * 32 + '@group.calendar.google.com'} | changes))


def request():
    return insert_request(profile().calendar_id, str(uuid4()), {
        'title': 'Встреча', 'note': '', 'start': '2026-11-25T12:00:00+03:00',
        'end': '2026-11-25T13:00:00+03:00', 'timezone': 'Europe/Moscow',
        'telegram_reminder_minutes': 15})


def client(handler, token_provider=lambda: 'fixture-token-not-real-123'):
    item = profile()
    return PersonalCalendarHTTP(item, digest(item.model_dump()), token_provider,
                                transport=httpx.MockTransport(handler))


def test_pkce_has_only_personal_scopes_and_loopback():
    value = desktop_authorization('a' * 24 + '.apps.googleusercontent.com',
        'http://127.0.0.1:8912/oauth/google/callback', 's' * 32, 'v' * 43)
    query = parse_qs(urlsplit(value['url']).query)
    assert query['scope'] == [' '.join(SCOPES)]
    assert query['code_challenge_method'] == ['S256']
    assert query['access_type'] == ['offline']
    assert 'v' * 43 not in str(value)


@pytest.mark.parametrize('redirect', [None, '', 'https://example.com/oauth/google/callback',
    'http://127.0.0.1:8912/oauth/google/callback?next=evil',
    'http://localhost:8912/oauth/google/callback', 'http://127.0.0.1/oauth/google/callback'])
def test_invalid_callback_denied(redirect):
    with pytest.raises(Denied):
        desktop_authorization('a' * 24 + '.apps.googleusercontent.com', redirect, 's' * 32, 'v' * 43)


@pytest.mark.parametrize('changes', [{'calendar_id': 'primary'}, {'schema_version': True},
    {'owner_id': True}, {'scopes': ('https://www.googleapis.com/auth/calendar',)}])
def test_profile_rejects_expanded_authority(changes):
    with pytest.raises(ValidationError):
        profile(**changes)


def test_exact_profile_approval_and_enabled_required():
    for item, approval in [(profile(), 'wrong'), (profile(enabled=False), digest(profile().model_dump()))]:
        with pytest.raises(Denied):
            PersonalCalendarHTTP(item, approval, lambda: 'unused')


@pytest.mark.parametrize('mutation', ['path', 'attendees', 'method', 'query', 'timezone'])
def test_mutated_request_rejected_before_token_access(mutation):
    value = deepcopy(request())
    if mutation == 'path':
        value['path'] = '/calendar/v3/calendars/primary/events'
    elif mutation == 'attendees':
        value['body']['attendees'] = [{'email': 'someone@example.com'}]
    elif mutation == 'method':
        value['method'] = 'DELETE'
    elif mutation == 'query':
        value['query']['sendUpdates'] = 'all'
    else:
        value['body']['end']['timeZone'] = 'UTC'
    calls = []
    item = client(lambda req: calls.append(req), lambda: calls.append('token'))
    try:
        with pytest.raises(Denied):
            item.call(value)
        assert calls == []
    finally:
        item.close()


def test_exact_insert_and_reconciliation_use_fixed_google_origin():
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200, json={'items': []})
    item = client(handler)
    try:
        item.call(request())
        item.call(reconciliation_request(profile().calendar_id, str(uuid4())))
        assert [req.method for req in calls] == ['POST', 'GET']
        assert all(req.url.host == 'www.googleapis.com' for req in calls)
    finally:
        item.close()


@pytest.mark.parametrize('status', [401, 403, 429, 500])
def test_http_rejection_redacts_token_body_and_never_retries(status):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(status, json={'secret': 'private-provider-body'})
    item = client(handler)
    try:
        with pytest.raises(httpx.HTTPStatusError) as caught:
            item.call(request())
        assert len(calls) == 1
        assert 'authorization' not in caught.value.request.headers
        assert caught.value.response.content == b''
        assert 'private-provider-body' not in str(caught.value)
    finally:
        item.close()


def test_timeout_preserves_unknown_outcome_without_retry_or_secret():
    calls = []
    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout('private-token', request=req)
    item = client(handler)
    try:
        with pytest.raises(httpx.TimeoutException) as caught:
            item.call(request())
        assert str(caught.value) == 'google_calendar_timeout'
        assert len(calls) == 1
    finally:
        item.close()


@pytest.mark.parametrize('response', [httpx.Response(302, headers={'location': 'https://example.com'}),
    httpx.Response(200, content=b'x' * 65537), httpx.Response(200, json=[]),
    httpx.Response(200, content=b'not-json')])
def test_invalid_or_redirected_response_denied(response):
    item = client(lambda req: response)
    try:
        with pytest.raises(Denied):
            item.call(request())
    finally:
        item.close()


def test_agenda_is_bounded_read_only_and_drops_unsolicited_private_fields():
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200, json={'items': [{'id': 'one', 'summary': 'Встреча',
            'attendees': ['private'], 'start': {'date': '2026-11-25', 'extra': 'private'}}],
            'nextPageToken': 'more'})
    item = client(handler)
    try:
        result = item.agenda('2026-11-25T00:00:00+03:00', '2026-11-26T00:00:00+03:00')
        assert result['truncated'] is True
        assert result['events'] == [{'id': 'one', 'summary': 'Встреча', 'start': {'date': '2026-11-25'}}]
        assert calls[0].method == 'GET'
        assert calls[0].url.params['maxResults'] == '50'
        with pytest.raises(Denied):
            item.agenda('2026-11-01', '2027-01-01')
        assert len(calls) == 1
    finally:
        item.close()
