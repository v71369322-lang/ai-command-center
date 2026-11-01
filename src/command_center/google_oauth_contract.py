"""Google OAuth Authorization Code + PKCE contract without credential persistence."""

import base64
import hashlib
import re
from urllib.parse import urlencode

from .store import Denied, digest

SCOPE = 'https://www.googleapis.com/auth/calendar.events'
AUTH_ENDPOINT = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token'


def _client(client_id, redirect_uri):
    if (not isinstance(client_id, str) or not re.fullmatch(r'[A-Za-z0-9._-]{20,200}', client_id)
            or not isinstance(redirect_uri, str) or not redirect_uri.startswith('https://')
            or len(redirect_uri) > 500 or any(char in redirect_uri for char in '\r\n#')):
        raise Denied('google_oauth_client_invalid')


def authorization_request(client_id, redirect_uri, state, verifier):
    _client(client_id, redirect_uri)
    if (not isinstance(state, str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', state)
            or not isinstance(verifier, str) or not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}', verifier)):
        raise Denied('google_oauth_pkce_invalid')
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    query = {'client_id': client_id, 'redirect_uri': redirect_uri, 'response_type': 'code',
             'scope': SCOPE, 'access_type': 'offline', 'include_granted_scopes': 'false',
             'prompt': 'consent', 'state': state, 'code_challenge': challenge,
             'code_challenge_method': 'S256'}
    return {'url': AUTH_ENDPOINT + '?' + urlencode(query), 'state_hash': digest(state),
            'verifier_hash': digest(verifier), 'scope': SCOPE}


def token_request(client_id, redirect_uri, code, verifier):
    _client(client_id, redirect_uri)
    if (not isinstance(code, str) or not 8 <= len(code) <= 2048 or any(char in code for char in '\r\n')
            or not isinstance(verifier, str) or not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}', verifier)):
        raise Denied('google_oauth_callback_invalid')
    return {'method': 'POST', 'url': TOKEN_ENDPOINT, 'form': {'client_id': client_id, 'code': code,
            'code_verifier': verifier, 'redirect_uri': redirect_uri, 'grant_type': 'authorization_code'}}


def verify_token_metadata(response):
    """Return fingerprints only; the trusted custody layer stores raw material separately."""
    if (not isinstance(response, dict)
            or not isinstance(response.get('access_token'), str) or len(response['access_token']) < 20
            or not isinstance(response.get('refresh_token'), str) or len(response['refresh_token']) < 20
            or response.get('token_type') != 'Bearer'
            or type(response.get('expires_in')) is not int or not 60 <= response['expires_in'] <= 86400
            or set(response.get('scope', '').split()) != {SCOPE}):
        raise Denied('google_oauth_token_response_invalid')
    return {'access_token_fingerprint': digest(response['access_token']),
            'refresh_token_fingerprint': digest(response['refresh_token']),
            'expires_in': response['expires_in'], 'scope': SCOPE,
            'credential_value_returned': False}
