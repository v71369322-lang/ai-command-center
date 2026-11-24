import base64
import hashlib
import json
from pathlib import Path
import subprocess

import httpx
import pytest

from command_center.google_script_calendar import (
    PROTOCOL, ScriptCalendarHTTP, ScriptCalendarProfile, envelope, script_calendar_runtime,
)
from command_center.store import Denied, digest

KEY = 'ab' * 32  # Public synthetic fixture; never a deployed key.
START, END = '2026-11-25T00:00:00+03:00', '2026-11-26T00:00:00+03:00'


def profile(**changes):
    return ScriptCalendarProfile(**({'enabled': True, 'owner_id': 123, 'source_revision': 'a' * 40,
        'deployment_id': 'public_synthetic_deployment_123', 'connection_id': 'c' * 64,
        'key_fingerprint': hashlib.sha256(bytes.fromhex(KEY)).hexdigest()} | changes))


def request_value():
    return {'protocol': PROTOCOL, 'connection': 'c' * 64, 'nonce': 'd' * 32,
            'issued_at': 1000, 'start': START, 'end': END}


def answer(request, **changes):
    return envelope({**request, 'timezone': 'Europe/Moscow', 'events': [], 'truncated': False,
                     **changes}, KEY, 'JARVIS_CALENDAR_RESPONSE_V1')


def decode(body):
    return json.loads(base64.b64decode(json.loads(body)['payload']))


def client(handler, **kwargs):
    item = profile()
    return ScriptCalendarHTTP(item, digest(item.model_dump()), KEY,
        transport=httpx.MockTransport(handler), clock=lambda: 1000, sleep=lambda _: None, **kwargs)


def test_signed_read_follows_only_content_service_get_without_forwarding_body():
    calls, original = [], []
    def handler(req):
        calls.append(req)
        if req.method == 'POST':
            original.append(decode(req.content))
            assert KEY.encode() not in req.content and 'authorization' not in req.headers
            return httpx.Response(302, headers={'location': 'https://script.googleusercontent.com/macros/echo?key=fixture'})
        assert req.content == b'' and 'authorization' not in req.headers
        return httpx.Response(200, json=answer(original[0]))
    service = client(handler)
    try:
        assert service.agenda(START, END)['events'] == []
        assert [req.method for req in calls] == ['POST', 'GET']
        assert not hasattr(service, 'call')  # Cannot be used as an event publisher.
    finally:
        service.close()


@pytest.mark.parametrize('target', ['https://example.com/macros/echo',
    'https://script.googleusercontent.com.evil.example/macros/echo',
    'http://script.googleusercontent.com/macros/echo',
    'https://user@script.googleusercontent.com/macros/echo',
    'https://script.googleusercontent.com/elsewhere'])
def test_redirect_escape_is_rejected_without_second_contact(target):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(302, headers={'location': target})
    service = client(handler)
    try:
        with pytest.raises(Denied):
            service.agenda(START, END)
        assert len(calls) == 1
    finally:
        service.close()


@pytest.mark.parametrize('change', [{'nonce': 'e' * 32}, {'connection': 'b' * 64},
    {'issued_at': 900}, {'start': END}, {'timezone': 'UTC'}, {'events': [{}] * 51},
    {'events': [{'summary': 'private', 'start': {}, 'end': {}, 'attendees': []}]}])
def test_signed_but_wrong_bound_or_oversized_response_fails_closed(change):
    service = client(lambda req: httpx.Response(200, json=answer(decode(req.content), **change)))
    try:
        with pytest.raises(Denied):
            service.agenda(START, END)
    finally:
        service.close()


def test_bad_mac_and_provider_error_never_look_like_an_empty_calendar():
    for result in [{'payload': 'e30=', 'signature': '0' * 64}, {'error': 'unavailable'}]:
        service = client(lambda req: httpx.Response(200, json=result))
        try:
            with pytest.raises(Denied):
                service.agenda(START, END)
        finally:
            service.close()


def test_transport_retry_is_bounded_and_uses_a_fresh_nonce():
    calls = []
    def handler(req):
        calls.append(decode(req.content))
        if len(calls) == 1:
            raise httpx.ReadTimeout('private detail', request=req)
        return httpx.Response(200, json=answer(calls[-1]))
    service = client(handler)
    try:
        assert service.agenda(START, END)['source'] == 'Google Calendar'
        assert len(calls) == 2 and calls[0]['nonce'] != calls[1]['nonce']
    finally:
        service.close()


def test_two_timeouts_are_redacted_and_stop():
    calls = []
    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout('private token', request=req)
    service = client(handler)
    try:
        with pytest.raises(Denied) as caught:
            service.agenda(START, END)
        assert str(caught.value) == 'google_script_calendar_unavailable' and len(calls) == 2
    finally:
        service.close()


def test_invalid_interval_and_changed_approval_never_read_credentials_or_network():
    item = profile()
    with pytest.raises(Denied):
        ScriptCalendarHTTP(item, 'wrong', KEY)
    service = client(lambda req: pytest.fail('no request expected'))
    try:
        with pytest.raises(Denied):
            service.agenda(START, '2027-01-01T00:00:00+03:00')
    finally:
        service.close()


def run_script(signed, **changes):
    result = subprocess.run(['node', str(Path(__file__).with_name('calendar_bridge_harness.cjs'))],
        input=json.dumps({'envelope': signed, **changes}), capture_output=True, text=True, timeout=10)  # nosec B603,B607: fixed Node test harness and synthetic input, no shell
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_real_javascript_and_python_signatures_interoperate_and_repeat_is_rejected():
    request = request_value()
    signed = envelope(request, KEY, 'JARVIS_CALENDAR_REQUEST_V1')
    result = run_script(signed, repeat=True, event_count=51, all_day=True)
    assert result['reads'] == 1 and result['repeated'] == {'error': 'unavailable'}
    service = client(lambda req: pytest.fail('no HTTP in protocol check'))
    try:
        verified = service._verify(result['response'], request)
        assert verified['truncated'] is True and len(verified['events']) == 50
        assert verified['events'][0]['start'] == {'date': '2026-11-25'}
    finally:
        service.close()


@pytest.mark.parametrize('change', [{'nonce': []}, {'issued_at': 800}, {'end': START},
    {'connection': 'e' * 64}, {'extra': 'field'}])
def test_javascript_rejects_invalid_signed_requests_before_calendar_read(change):
    result = run_script(envelope(request_value() | change, KEY, 'JARVIS_CALENDAR_REQUEST_V1'))
    assert result['reads'] == 0 and result['response'] == {'error': 'unavailable'}


def test_javascript_rejects_bad_signature_and_hides_provider_errors():
    signed = envelope(request_value(), KEY, 'JARVIS_CALENDAR_REQUEST_V1')
    assert run_script(signed | {'signature': '0' * 64})['reads'] == 0
    result = run_script(signed, provider_failure=True)
    assert result['response'] == {'error': 'unavailable'} and 'private' not in str(result)


def test_runtime_scope_denied_before_private_key_read(monkeypatch):
    body = json.dumps({'profile': profile().model_dump(), 'key_file': '/private/key'})
    calls = []
    def read(path, limit):
        calls.append(path)
        return body
    monkeypatch.setattr('command_center.google_script_calendar.private_read', read)
    with pytest.raises(Denied):
        with script_calendar_runtime('/private/config', 'wrong', 'a' * 40, 123):
            pass
    assert calls == ['/private/config']


@pytest.mark.parametrize('status', [401, 403, 429])
def test_definite_rejection_is_not_retried(status):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(status, json={'error': 'private detail'})
    service = client(handler)
    try:
        with pytest.raises(Denied):
            service.agenda(START, END)
        assert len(calls) == 1
    finally:
        service.close()


def test_large_response_and_redirect_chain_are_bounded():
    for second in [httpx.Response(200, content=b'x' * 65537), httpx.Response(302,
        headers={'location': 'https://script.googleusercontent.com/macros/echo?another'})]:
        calls = []
        def handler(req):
            calls.append(req)
            return (httpx.Response(302, headers={'location':
                'https://script.googleusercontent.com/macros/echo?first'}) if len(calls) == 1 else second)
        service = client(handler)
        try:
            with pytest.raises(Denied):
                service.agenda(START, END)
            assert len(calls) == 2
        finally:
            service.close()


def test_private_content_url_is_redacted_in_httpx_logs(caplog):
    import logging
    service = client(lambda req: httpx.Response(200, json={}))
    try:
        with caplog.at_level(logging.INFO, logger='httpx'):
            logging.getLogger('httpx').info('GET https://script.googleusercontent.com/macros/echo?private=fixture')
        assert 'private=fixture' not in caplog.text and '[redacted]' in caplog.text
    finally:
        service.close()


def test_one_total_deadline_cancels_slow_headers_without_retry(monkeypatch):
    import asyncio
    original_timeout = asyncio.timeout
    def fast_deadline(seconds):
        assert seconds == 12
        return original_timeout(.02)
    monkeypatch.setattr('command_center.google_script_calendar.asyncio.timeout', fast_deadline)
    calls = []
    async def slow(req):
        calls.append(req)
        await asyncio.sleep(1)
        pytest.fail('total deadline did not cancel pending headers')
    service = client(slow)
    try:
        with pytest.raises(Denied, match='unavailable'):
            service.agenda(START, END)
        assert len(calls) == 1
    finally:
        service.close()


def test_closed_client_cannot_contact_google():
    service = client(lambda req: pytest.fail('closed client used'))
    service.close()
    with pytest.raises(Denied, match='closed'):
        service.agenda(START, END)
