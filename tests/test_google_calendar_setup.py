import os
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from command_center.google_calendar_access import CalendarAccess, SCOPES
from command_center.google_calendar_oauth import CalendarOAuthHTTP, Credentials, open_credentials, seal_credentials
from command_center.google_calendar_setup import (
    CalendarCredentialFiles, CalendarLoopback, complete_connection, connection_binding,
)
from command_center.store import Denied, digest

CLIENT = 'a' * 24 + '.apps.googleusercontent.com'
POSIX = pytest.mark.skipif(sys.platform == 'win32', reason='POSIX credential permissions tested on Linux')


def access():
    return CalendarAccess(enabled=True, source_revision='a' * 40, owner_id=123,
                          calendar_id='a' * 32 + '@group.calendar.google.com')


def directory(tmp_path):
    tmp_path.chmod(0o700)
    (tmp_path / 'calendar.key').write_bytes(b'k' * 32)
    (tmp_path / 'calendar.key').chmod(0o600)
    return tmp_path


@POSIX
def test_private_atomic_archive_roundtrip_and_exclusive_owner(tmp_path):
    path = directory(tmp_path)
    record = Credentials('fixture-access-token-123', 'fixture-refresh-token-123', 4600)
    with CalendarCredentialFiles(path) as files:
        with pytest.raises(Denied):
            CalendarCredentialFiles(path)
        archive = seal_credentials(record, files.key, 'a' * 64)
        files.save(archive)
        assert files.load() == archive
        assert (path / 'calendar.enc').stat().st_mode & 0o777 == 0o600
        assert len(list(path.glob('.calendar-*'))) == 0
    with CalendarCredentialFiles(path) as files:
        assert open_credentials(files.load(), files.key, 'a' * 64) == record


@POSIX
@pytest.mark.parametrize('unsafe', ['directory', 'key_mode', 'key_link', 'key_hardlink', 'key_size'])
def test_unsafe_custody_denied(tmp_path, unsafe):
    path = directory(tmp_path)
    key = path / 'calendar.key'
    if unsafe == 'directory':
        path.chmod(0o755)
    elif unsafe == 'key_mode':
        key.chmod(0o644)
    elif unsafe == 'key_link':
        key.rename(path / 'other')
        key.symlink_to(path / 'other')
    elif unsafe == 'key_hardlink':
        os.link(key, path / 'other')
    else:
        key.write_bytes(b'wrong-key')
    with pytest.raises(Denied):
        CalendarCredentialFiles(path)


@POSIX
def test_symlink_target_is_never_followed_or_replaced(tmp_path):
    path = directory(tmp_path)
    other = path / 'other'
    other.write_bytes(b'untouched')
    (path / 'calendar.enc').symlink_to(other)
    with CalendarCredentialFiles(path) as files:
        with pytest.raises(Denied):
            files.load()
        with pytest.raises(Denied):
            files.save(b'x' * 100)
    assert other.read_bytes() == b'untouched'
    assert (path / 'calendar.enc').is_symlink()


@POSIX
def test_failed_atomic_replace_preserves_previous_archive_and_cleans_temp(tmp_path, monkeypatch):
    path = directory(tmp_path)
    with CalendarCredentialFiles(path) as files:
        first = seal_credentials(Credentials('fixture-access-token-123', 'fixture-refresh-token-123', 4600),
                                 files.key, 'a' * 64)
        files.save(first)
        def fail(*args, **kwargs):
            raise OSError('simulated disk failure')
        monkeypatch.setattr(os, 'replace', fail)
        with pytest.raises(Denied, match='commit_failed'):
            files.save(first)
        assert files.load() == first
        assert list(path.glob('.calendar-*')) == []


def test_exact_connection_binding_checks_revision_and_profile():
    profile = access()
    approved = digest(profile.model_dump())
    first = connection_binding(profile, approved, CLIENT, 'a' * 40)
    assert first != connection_binding(profile, approved, 'different-client', 'a' * 40)
    for approval, revision in [('wrong', 'a' * 40), (approved, 'b' * 40)]:
        with pytest.raises(Denied):
            connection_binding(profile, approval, CLIENT, revision)


def test_real_loopback_receives_callback_without_echoing_code_or_state(capsys):
    with CalendarLoopback(CLIENT) as listener:
        state = parse_qs(urlsplit(listener.authorization_url).query)['state'][0]
        calls = []
        def handler(req):
            calls.append(req)
            return httpx.Response(200, json={'access_token': 'fixture-access-token-123',
                'refresh_token': 'fixture-refresh-token-123', 'expires_in': 3600,
                'token_type': 'Bearer', 'scope': ' '.join(SCOPES)})
        oauth = CalendarOAuthHTTP(CLIENT, transport=httpx.MockTransport(handler))
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(listener.wait, oauth, now=lambda: 1000)
                with httpx.Client(trust_env=False) as browser:
                    bad = browser.get('http://' + listener.host + '/oauth/google/callback',
                                      params={'state': 'wrong', 'code': 'private-code'})
                    assert bad.status_code == 400
                    good = browser.get('http://' + listener.host + '/oauth/google/callback',
                                       params={'state': state, 'code': 'private-code'})
                assert good.status_code == 200
                assert state not in good.text and 'private-code' not in good.text
                assert future.result(timeout=3).expires_at == 4600
            assert len(calls) == 1
        finally:
            oauth.close()
        output = capsys.readouterr()
        assert state not in output.err and 'private-code' not in output.err
        with socket.socket() as sock:
            assert sock.connect_ex(('127.0.0.1', int(listener.host.split(':')[1]))) != 0


@pytest.mark.parametrize('path,headers', [('/wrong', {}),
    ('/oauth/google/callback?state=x', {'Host': 'evil.example'}),
    ('/oauth/google/callback?' + 'x' * 4100, {})])
def test_invalid_callback_requests_do_not_finish_attempt(path, headers):
    with CalendarLoopback(CLIENT) as listener:
        # Exercise one actual HTTP request without waiting five minutes.
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(listener._server.handle_request)
            response = httpx.get('http://' + listener.host + path, headers=headers, trust_env=False)
            future.result(timeout=3)
        assert response.status_code == 400
        assert listener._query is None


def test_expired_listener_closes_without_any_token_exchange():
    ticks = [1]
    with CalendarLoopback(CLIENT, clock=lambda: ticks[0]) as listener:
        ticks[0] = 302
        with pytest.raises(Denied, match='timeout'):
            listener.wait(None, now=lambda: 1000)


def test_incomplete_local_request_cannot_block_listener_indefinitely():
    with CalendarLoopback(CLIENT) as listener:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(listener._server.handle_request)
            with socket.create_connection(('127.0.0.1', int(listener.host.split(':')[1])), timeout=2) as sock:
                sock.sendall(b'GET /oauth/google/callback?state=never-complete')
                future.result(timeout=3)
        assert listener._query is None


def test_connection_persists_encrypted_only_after_exact_approval():
    profile = access()
    class Files:
        key = b'k' * 32
        archive = None
        def save(self, value):
            self.archive = value
    class Listener:
        calls = 0
        def wait(self, oauth, now):
            self.calls += 1
            return Credentials('fixture-access-token-123', 'fixture-refresh-token-123', now() + 3600)
    files, listener = Files(), Listener()
    oauth = CalendarOAuthHTTP(CLIENT, transport=httpx.MockTransport(lambda req: pytest.fail('no network')))
    try:
        with pytest.raises(Denied):
            complete_connection(listener, oauth, files, profile, 'wrong', 'a' * 40)
        assert listener.calls == 0
        result = complete_connection(listener, oauth, files, profile, digest(profile.model_dump()),
                                     'a' * 40, now=lambda: 1000)
        assert result['status'] == 'CREDENTIALS_STORED' and result['event_created'] is False
        assert b'fixture-access' not in files.archive
        assert open_credentials(files.archive, files.key, result['connection_binding']).expires_at == 4600
    finally:
        oauth.close()
