from urllib.parse import parse_qs, urlparse

import pytest

from command_center.google_oauth_contract import (AUTH_ENDPOINT, SCOPE, TOKEN_ENDPOINT,
                                                   authorization_request, token_request,
                                                   verify_token_metadata)
from command_center.store import Denied

CLIENT = '1234567890-abcdefghijklmnopqrstuvwxyz.apps.googleusercontent.com'
REDIRECT = 'https://commander.example.test/oauth/google/callback'
STATE = 's' * 43
VERIFIER = 'v' * 64


def test_authorization_uses_exact_scope_offline_consent_and_pkce():
    request = authorization_request(CLIENT, REDIRECT, STATE, VERIFIER)
    parsed = urlparse(request['url'])
    query = parse_qs(parsed.query)
    assert parsed.scheme + '://' + parsed.netloc + parsed.path == AUTH_ENDPOINT
    assert query['scope'] == [SCOPE]
    assert query['access_type'] == ['offline'] and query['prompt'] == ['consent']
    assert query['code_challenge_method'] == ['S256']
    assert 'client_secret' not in query


def test_token_exchange_contract_contains_no_client_secret():
    request = token_request(CLIENT, REDIRECT, 'authorization-code-fixture', VERIFIER)
    assert request['url'] == TOKEN_ENDPOINT and request['method'] == 'POST'
    assert set(request['form']) == {'client_id', 'code', 'code_verifier', 'redirect_uri', 'grant_type'}


def test_token_metadata_returns_only_fingerprints():
    metadata = verify_token_metadata({'access_token': 'a' * 40, 'refresh_token': 'r' * 40,
        'token_type': 'Bearer', 'expires_in': 3600, 'scope': SCOPE})
    assert metadata['credential_value_returned'] is False
    assert 'a' * 20 not in str(metadata) and 'r' * 20 not in str(metadata)


@pytest.mark.parametrize('change', [
    {'scope': SCOPE + ' https://www.googleapis.com/auth/calendar'},
    {'refresh_token': ''}, {'token_type': 'bearer'}, {'expires_in': True},
])
def test_broader_or_malformed_token_response_is_rejected(change):
    response = {'access_token': 'a' * 40, 'refresh_token': 'r' * 40,
                'token_type': 'Bearer', 'expires_in': 3600, 'scope': SCOPE}
    response.update(change)
    with pytest.raises(Denied, match='token_response_invalid'):
        verify_token_metadata(response)
