from urllib.parse import parse_qs, urlsplit
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from command_center.google_calendar_access import CalendarAccess, PersonalCalendarHTTP, SCOPES
from command_center.google_calendar_oauth import (
    CalendarOAuthHTTP, CalendarTokenProvider, Credentials, DesktopAuthorization, open_credentials, seal_credentials,
)
from command_center.store import Denied, digest

CLIENT = 'a' * 24 + '.apps.googleusercontent.com'
REDIRECT = 'http://127.0.0.1:8912/oauth/google/callback'
ACCESS = 'fixture-access-not-real-1234'
REFRESH = 'fixture-refresh-not-real-1234'


def token_response(**changes):
    return {'access_token': ACCESS, 'refresh_token': REFRESH, 'expires_in': 3600,
            'token_type': 'Bearer', 'scope': ' '.join(SCOPES)} | changes


def test_encrypted_credentials_survive_restart_and_hide_values():
    record = Credentials(ACCESS, REFRESH, 4600)
    archive = seal_credentials(record, b'k' * 32, 'a' * 64)
    assert ACCESS.encode() not in archive and REFRESH.encode() not in archive
    assert ACCESS not in repr(record)
    assert open_credentials(archive, b'k' * 32, 'a' * 64) == record
    assert seal_credentials(record, b'k' * 32, 'a' * 64) != archive


@pytest.mark.parametrize('mutation', ['key', 'binding', 'ciphertext', 'truncated'])
def test_custody_rejects_tampering_or_cross_owner_binding(mutation):
    key, binding = b'k' * 32, 'a' * 64
    archive = seal_credentials(Credentials(ACCESS, REFRESH, 4600), key, binding)
    if mutation == 'key':
        key = b'x' * 32
    elif mutation == 'binding':
        binding = 'b' * 64
    elif mutation == 'ciphertext':
        archive = archive[:-1] + bytes([archive[-1] ^ 1])
    else:
        archive = archive[:40]
    with pytest.raises(Denied, match='archive_invalid'):
        open_credentials(archive, key, binding)


def test_pkce_callback_consumed_exactly_once():
    calls = []
    attempt = DesktopAuthorization(CLIENT, REDIRECT)
    auth = parse_qs(urlsplit(attempt.authorization_url).query)
    def handler(req):
        calls.append(req)
        form = parse_qs(req.content.decode())
        assert req.url == 'https://oauth2.googleapis.com/token'
        assert form['redirect_uri'] == [REDIRECT]
        assert len(form['code_verifier'][0]) >= 43
        return httpx.Response(200, json=token_response())
    http = CalendarOAuthHTTP(CLIENT, transport=httpx.MockTransport(handler))
    try:
        query = {'state': auth['state'], 'code': ['fixture-code']}
        result = attempt.complete(query, http, now=1000)
        assert result.expires_at == 4600
        with pytest.raises(Denied, match='consumed'):
            attempt.complete(query, http, now=1000)
        assert len(calls) == 1
    finally:
        http.close()


def test_state_mismatch_and_expiry_prevent_network_access():
    ticks = [1]
    attempt = DesktopAuthorization(CLIENT, REDIRECT, clock=lambda: ticks[0])
    calls = []
    http = CalendarOAuthHTTP(CLIENT, transport=httpx.MockTransport(lambda req: calls.append(req)))
    try:
        with pytest.raises(Denied, match='state_invalid'):
            attempt.complete({'state': ['wrong'], 'code': ['fixture-code']}, http, now=1000)
        state = parse_qs(urlsplit(attempt.authorization_url).query)['state']
        ticks[0] = 301
        with pytest.raises(Denied, match='expired'):
            attempt.complete({'state': state, 'code': ['fixture-code']}, http, now=1000)
        assert calls == []
    finally:
        http.close()


@pytest.mark.parametrize('changes', [{'scope': 'https://www.googleapis.com/auth/calendar'},
    {'scope': SCOPES[0]}, {'expires_in': True}, {'access_token': 'short'},
    {'refresh_token': None}, {'token_type': 'Other'}])
def test_token_metadata_fails_closed(changes):
    http = CalendarOAuthHTTP(CLIENT, transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json=token_response(**changes))))
    try:
        with pytest.raises(Denied, match='exchange_failed'):
            http.refresh(Credentials(ACCESS, REFRESH, 1000), now=1000)
    finally:
        http.close()


def test_refresh_retains_prior_exact_scope_and_refresh_token_when_omitted():
    value = token_response()
    del value['scope'], value['refresh_token']
    http = CalendarOAuthHTTP(CLIENT, transport=httpx.MockTransport(lambda req: httpx.Response(200, json=value)))
    try:
        result = http.refresh(Credentials(ACCESS, REFRESH, 1000), now=1000)
        assert result.refresh_token == REFRESH
        assert result.expires_at == 4600
    finally:
        http.close()


@pytest.mark.parametrize('failure', ['timeout', 'revoked', 'redirect', 'oversized'])
def test_exchange_failure_redacts_and_never_retries(failure):
    calls = []
    def handler(req):
        calls.append(req)
        if failure == 'timeout':
            raise httpx.ReadTimeout(REFRESH, request=req)
        if failure == 'revoked':
            return httpx.Response(400, json={'error': 'invalid_grant', 'private': REFRESH})
        if failure == 'redirect':
            return httpx.Response(302, headers={'location': 'https://example.com'})
        return httpx.Response(200, content=b'x' * 16385)
    http = CalendarOAuthHTTP(CLIENT, transport=httpx.MockTransport(handler))
    attempt = DesktopAuthorization(CLIENT, REDIRECT)
    query = {'state': parse_qs(urlsplit(attempt.authorization_url).query)['state'], 'code': ['fixture-code']}
    try:
        with pytest.raises(Denied) as caught:
            attempt.complete(query, http, now=1000)
        assert REFRESH not in str(caught.value)
        with pytest.raises(Denied, match='consumed'):
            attempt.complete(query, http, now=1000)
        assert len(calls) == 1
    finally:
        http.close()


def test_user_denial_is_consumed_without_exchange():
    calls = []
    http = CalendarOAuthHTTP(CLIENT, transport=httpx.MockTransport(lambda req: calls.append(req)))
    attempt = DesktopAuthorization(CLIENT, REDIRECT)
    query = {'state': parse_qs(urlsplit(attempt.authorization_url).query)['state'], 'error': ['access_denied']}
    try:
        with pytest.raises(Denied, match='callback_invalid'):
            attempt.complete(query, http, now=1000)
        with pytest.raises(Denied, match='consumed'):
            attempt.complete(query, http, now=1000)
        assert calls == []
    finally:
        http.close()


def test_provider_refreshes_once_then_reloads_durable_encrypted_credentials():
    calls = []
    key, binding = b'k' * 32, 'a' * 64
    archive = [seal_credentials(Credentials(ACCESS, REFRESH, 1000), key, binding)]
    def handler(req):
        calls.append(req)
        return httpx.Response(200, json=token_response(access_token='new-fixture-access-token-123'))
    http = CalendarOAuthHTTP(CLIENT, transport=httpx.MockTransport(handler))
    provider = CalendarTokenProvider(http, key, binding, lambda: archive[0],
                                     lambda value: archive.__setitem__(0, value), clock=lambda: 1000)
    try:
        assert provider() == 'new-fixture-access-token-123'
        assert provider() == 'new-fixture-access-token-123'
        assert len(calls) == 1
        assert open_credentials(archive[0], key, binding).expires_at == 4600
        assert ACCESS not in repr(provider)
    finally:
        http.close()


@pytest.mark.parametrize('failure', ['persistence', 'revocation', 'corrupt'])
def test_provider_failure_never_returns_token_or_automatically_retries(failure):
    key, binding = b'k' * 32, 'a' * 64
    archive = seal_credentials(Credentials(ACCESS, REFRESH, 1000), key, binding)
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(400 if failure == 'revocation' else 200, json=token_response())
    def save(value):
        assert ACCESS.encode() not in value
        raise OSError('private-filesystem-detail')
    http = CalendarOAuthHTTP(CLIENT, transport=httpx.MockTransport(handler))
    provider = CalendarTokenProvider(http, key, binding,
        lambda: b'corrupt' if failure == 'corrupt' else archive, save, clock=lambda: 1000)
    try:
        with pytest.raises(Denied, match='unavailable') as caught:
            provider()
        assert 'private-filesystem-detail' not in str(caught.value)
        count = len(calls)
        with pytest.raises(Denied, match='reauthorization_required'):
            provider()
        assert len(calls) == count
    finally:
        http.close()


def test_concurrent_matching_callbacks_exchange_only_once():
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200, json=token_response())
    http = CalendarOAuthHTTP(CLIENT, transport=httpx.MockTransport(handler))
    attempt = DesktopAuthorization(CLIENT, REDIRECT)
    query = {'state': parse_qs(urlsplit(attempt.authorization_url).query)['state'], 'code': ['fixture-code']}
    def complete(_):
        try:
            return attempt.complete(query, http, now=1000)
        except Denied:
            return None
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(complete, range(2)))
        assert sum(result is not None for result in results) == 1
        assert len(calls) == 1
    finally:
        http.close()


def test_encrypted_provider_supplies_bearer_to_bounded_calendar_client():
    item = CalendarAccess(enabled=True, source_revision='a' * 40, owner_id=123,
                          calendar_id='a' * 32 + '@group.calendar.google.com')
    # Bind custody to both the exact approved access profile and OAuth client.
    binding = digest({'profile': item.model_dump(), 'client_id': CLIENT})
    archive = seal_credentials(Credentials(ACCESS, REFRESH, 4600), b'k' * 32, binding)
    oauth = CalendarOAuthHTTP(CLIENT, transport=httpx.MockTransport(
        lambda req: pytest.fail('unexpired credentials must not refresh')))
    provider = CalendarTokenProvider(oauth, b'k' * 32, binding, lambda: archive,
                                      lambda value: pytest.fail('no persistence needed'), clock=lambda: 1000)
    def handler(req):
        assert req.headers['authorization'] == 'Bearer ' + ACCESS
        assert req.method == 'GET' and req.url.path.endswith('/primary/events')
        return httpx.Response(200, json={'items': []})
    calendar = PersonalCalendarHTTP(item, digest(item.model_dump()), provider,
                                    transport=httpx.MockTransport(handler))
    try:
        assert calendar.agenda('2026-11-25T00:00:00+03:00',
                               '2026-11-26T00:00:00+03:00')['events'] == []
    finally:
        calendar.close()
        oauth.close()
