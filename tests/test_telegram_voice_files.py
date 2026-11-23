from hashlib import sha256
import json

import httpx
import pytest

from command_center.store import Denied
from command_center.telegram_transport import ConfiguredTelegramHTTP, TelegramHTTPError
from command_center.telegram_voice_files import TelegramVoiceFiles
from command_center.telegram_voice_requests import parse_message

TOKEN = '123456789:PUBLIC_FIXTURE_NOT_AN_ACTUAL_KEY_12345'


def intent():
    return parse_message({'voice': {'file_id': 'public-file', 'file_unique_id': 'public_unique',
        'duration': 2, 'file_size': 5, 'mime_type': 'audio/ogg'}})


def client(handler):
    configured = object.__new__(ConfiguredTelegramHTTP)
    configured._token, configured.approved = TOKEN, 'a' * 64
    configured.check_enabled = lambda: None
    configured.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return configured


def metadata(**changes):
    return {'ok': True, 'result': {'file_id': 'public-file', 'file_unique_id': 'public_unique',
        'file_size': 5, 'file_path': 'voice/file_10.oga', **changes}}


def test_only_exact_intake_file_is_downloaded_from_fixed_telegram_host():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.host == 'api.telegram.org'
        if request.method == 'POST':
            assert json.loads(request.content) == {'file_id': 'public-file'}
            return httpx.Response(200, json=metadata())
        assert request.url.path.endswith('/voice/file_10.oga')
        return httpx.Response(200, content=b'audio')

    configured = client(handler)
    try:
        result = TelegramVoiceFiles(configured, approved_connection='a' * 64).download(intent())
        assert result == (b'audio', sha256(b'audio').hexdigest())
        assert len(seen) == 2
    finally:
        configured.close()


@pytest.mark.parametrize('change', [
    {'file_unique_id': 'another_unique'}, {'file_id': 'different'}, {'file_size': 6},
    {'file_path': '../credentials'}, {'file_path': 'https://outside.test/file.oga'},
    {'file_path': 'voice/file_10.oga?redirect=outside'},
])
def test_swapped_file_or_path_cannot_trigger_download(change):
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json=metadata(**change))

    configured = client(handler)
    try:
        with pytest.raises(Denied):
            TelegramVoiceFiles(configured, approved_connection='a' * 64).download(intent())
        assert calls == ['POST']
    finally:
        configured.close()


@pytest.mark.parametrize('mode', ['redirect', 'too_large', 'timeout'])
def test_audio_failure_never_follows_redirect_or_exposes_token(mode, caplog):
    def handler(request):
        if request.method == 'POST':
            return httpx.Response(200, json=metadata())
        if mode == 'redirect':
            return httpx.Response(302, headers={'Location': 'https://outside.test/'})
        if mode == 'too_large':
            return httpx.Response(200, content=b'123456')
        raise httpx.ReadTimeout('unsafe ' + TOKEN, request=request)

    configured = client(handler)
    try:
        with pytest.raises((Denied, TelegramHTTPError)) as error:
            TelegramVoiceFiles(configured, approved_connection='a' * 64).download(intent())
        assert TOKEN not in str(error.value) + caplog.text
    finally:
        configured.close()
