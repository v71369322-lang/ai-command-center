"""Calendar-only OAuth exchange and encrypted credentials; no implicit activation.

The caller owns protected key/archive persistence and exact access approval.
Neither browser cookies nor credentials are read from the environment.
"""
import hmac
import json
import re
import secrets
import time
import threading
from dataclasses import dataclass, field

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .google_calendar_access import SCOPES, desktop_authorization
from .google_oauth_contract import TOKEN_ENDPOINT
from .store import Denied, canonical

MAGIC = b'JARVIS-CALENDAR-OAUTH-v1\x00'


def _token(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9._~+/=-]{20,4096}', value)


@dataclass(frozen=True, repr=False)
class Credentials:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_at: int

    def __post_init__(self):
        if (not _token(self.access_token) or not _token(self.refresh_token)
                or type(self.expires_at) is not int or self.expires_at <= 0):
            raise Denied('google_credentials_invalid')

    def __repr__(self):
        return '<CalendarCredentials redacted>'


def _aad(binding):
    # The protected caller binds owner, OAuth client and exact approved profile.
    if not isinstance(binding, str) or not re.fullmatch('[a-f0-9]{64}', binding):
        raise Denied('google_credential_binding_invalid')
    return MAGIC + binding.encode()


def seal_credentials(credentials, key, binding):
    if not isinstance(key, bytes) or len(key) != 32:
        raise Denied('google_credential_key_invalid')
    nonce = secrets.token_bytes(12)
    body = canonical({'access_token': credentials.access_token,
        'refresh_token': credentials.refresh_token, 'expires_at': credentials.expires_at,
        'scopes': list(SCOPES)}).encode()
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, body, _aad(binding))


def open_credentials(archive, key, binding):
    try:
        if (not isinstance(archive, bytes) or not archive.startswith(MAGIC)
                or not 64 <= len(archive) <= 16384 or not isinstance(key, bytes) or len(key) != 32):
            raise ValueError()
        start = len(MAGIC)
        body = AESGCM(key).decrypt(archive[start:start + 12], archive[start + 12:], _aad(binding))
        value = json.loads(body)
        if set(value) != {'access_token', 'refresh_token', 'expires_at', 'scopes'} or value['scopes'] != list(SCOPES):
            raise ValueError()
        return Credentials(value['access_token'], value['refresh_token'], value['expires_at'])
    except Exception:
        raise Denied('google_credential_archive_invalid') from None


class CalendarOAuthHTTP:
    """Fixed token endpoint, bounded responses, no redirects or automatic replay."""
    def __init__(self, client_id, client_secret=None, *, transport=None):
        desktop_authorization(client_id, 'http://127.0.0.1:8912/oauth/google/callback', 's' * 32, 'v' * 43)
        if client_secret is not None and not _token(client_secret):
            raise Denied('google_oauth_client_secret_invalid')
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise Denied('google_oauth_transport_invalid')
        self._client_id, self._client_secret = client_id, client_secret
        self._http = httpx.Client(transport=transport, trust_env=False, follow_redirects=False, timeout=10)

    def __repr__(self):
        return '<CalendarOAuthHTTP credentials=redacted>'

    def _exchange(self, form, *, previous=None, now):
        form = dict(form, client_id=self._client_id)
        if self._client_secret is not None:
            form['client_secret'] = self._client_secret
        try:
            with self._http.stream('POST', TOKEN_ENDPOINT, data=form) as response:
                data = bytearray()
                for chunk in response.iter_bytes(4096):
                    data.extend(chunk)
                    if len(data) > 16384:
                        raise ValueError()
                if response.status_code != 200:
                    raise ValueError()
                value = json.loads(data)
            # Refresh may omit scope/refresh_token; retain only the earlier exact grant.
            scope = value.get('scope', ' '.join(SCOPES) if previous is not None else '')
            if (not isinstance(scope, str) or set(scope.split()) != set(SCOPES)
                    or value.get('token_type') != 'Bearer'
                    or type(value.get('expires_in')) is not int or not 60 <= value['expires_in'] <= 86400
                    or type(now) is not int or now <= 0):
                raise ValueError()
            refresh = value.get('refresh_token', previous.refresh_token if previous is not None else None)
            return Credentials(value.get('access_token'), refresh, now + value['expires_in'])
        except Exception:
            # Do not expose response bodies, form fields or httpx requests to logs.
            raise Denied('google_oauth_exchange_failed_reauthorization_may_be_required') from None

    def refresh(self, credentials, *, now):
        return self._exchange({'grant_type': 'refresh_token', 'refresh_token': credentials.refresh_token},
                              previous=credentials, now=now)

    def close(self):
        self._http.close()


class DesktopAuthorization:
    """One in-memory pending PKCE attempt, expires after five minutes.

    A loopback listener must supply parsed query lists from the exact callback
    path. This class does not open a listener or imply consent/access approval.
    """
    def __init__(self, client_id, redirect_uri, *, clock=time.monotonic):
        self._clock = clock
        self._deadline = clock() + 300
        self._state, self._verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        self._redirect = redirect_uri
        self._request = desktop_authorization(client_id, redirect_uri, self._state, self._verifier)
        self._used = False
        self._lock = threading.Lock()
        self._client_id = client_id

    def __repr__(self):
        return '<DesktopCalendarAuthorization redacted>'

    @property
    def authorization_url(self):
        return self._request['url']

    def complete(self, query, http, *, now):
        with self._lock:
            return self._complete(query, http, now=now)

    def _complete(self, query, http, *, now):
        if self._used or self._clock() >= self._deadline:
            raise Denied('google_oauth_attempt_expired_or_consumed')
        if (not isinstance(query, dict) or not isinstance(query.get('state'), list)
                or len(query['state']) != 1 or not isinstance(query['state'][0], str)
                or not hmac.compare_digest(query['state'][0], self._state)):
            raise Denied('google_oauth_callback_state_invalid')
        # Consume a matching callback before any token request, including denial
        # and uncertain network results. A new consent attempt is required then.
        self._used = True
        if (not isinstance(http, CalendarOAuthHTTP) or http._client_id != self._client_id
                or 'error' in query or not isinstance(query.get('code'), list)
                or len(query['code']) != 1 or not isinstance(query['code'][0], str)
                or not re.fullmatch(r'[A-Za-z0-9._~/+-]{8,2048}', query['code'][0])):
            raise Denied('google_oauth_callback_invalid')
        verifier, self._verifier = self._verifier, ''
        return http._exchange({'grant_type': 'authorization_code', 'code': query['code'][0],
            'code_verifier': verifier, 'redirect_uri': self._redirect}, now=now)


class CalendarTokenProvider:
    """Synchronous encrypted-custody adapter for PersonalCalendarHTTP.

    load/save are trusted protected persistence callbacks; save must atomically
    replace durable ciphertext before returning. They never receive plaintext.
    A single owner process must own this provider (no multi-process refresh).
    Any custody/refresh failure disables it until explicit reauthorization/restart.
    """
    def __init__(self, oauth, key, binding, load, save, *, clock=time.time):
        if (not isinstance(oauth, CalendarOAuthHTTP) or not callable(load) or not callable(save)
                or not isinstance(key, bytes) or len(key) != 32):
            raise Denied('google_credential_provider_invalid')
        _aad(binding)
        self._oauth, self._key, self._binding = oauth, key, binding
        self._load, self._save, self._clock = load, save, clock
        self._lock = threading.Lock()
        self._disabled = False

    def __repr__(self):
        return '<CalendarTokenProvider credentials=redacted>'

    def __call__(self):
        with self._lock:
            if self._disabled:
                raise Denied('google_credentials_reauthorization_required')
            try:
                record = open_credentials(self._load(), self._key, self._binding)
                now = int(self._clock())
                if now <= 0:
                    raise ValueError()
                if record.expires_at <= now + 60:
                    record = self._oauth.refresh(record, now=now)
                    # No new access token escapes if durable custody fails.
                    self._save(seal_credentials(record, self._key, self._binding))
                return record.access_token
            except Exception:
                self._disabled = True
                raise Denied('google_credentials_unavailable_reauthorization_required') from None
