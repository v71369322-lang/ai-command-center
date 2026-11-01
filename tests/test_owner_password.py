from dataclasses import replace
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from command_center.api import create_app
from command_center.owner_auth import OwnerAuth
from command_center import password_auth

PUBLIC_PASSWORD = 'public-password-fixture-not-a-real-secret'


@pytest.fixture
def password_config(settings, tmp_path):
    path = tmp_path / 'owner.json'
    path.write_text(json.dumps(password_auth.document('owner', PUBLIC_PASSWORD)))
    path.chmod(0o600)
    return replace(settings, auth_mode='password', owner_password_file=str(path),
                   web_origin='https://testserver')


def login(client, password=PUBLIC_PASSWORD, username='owner', origin='https://testserver'):
    return client.post('/api/auth/login', json={'username': username, 'password': password},
                       headers={'Origin': origin})


def test_password_hash_and_private_file(tmp_path):
    doc = password_auth.document('owner', PUBLIC_PASSWORD)
    assert PUBLIC_PASSWORD not in json.dumps(doc)
    assert password_auth.verify(doc, 'owner', PUBLIC_PASSWORD)
    assert not password_auth.verify(doc, 'intruder', PUBLIC_PASSWORD)
    assert not password_auth.verify(doc, 'owner', 'wrong')
    path = tmp_path / 'owner.json'
    path.write_text(json.dumps(doc))
    path.chmod(0o600)
    assert password_auth.load(str(path)) == doc
    path.chmod(0o644)
    with pytest.raises(ValueError, match='protected'):
        password_auth.load(str(path))
    link = tmp_path / 'link'
    link.symlink_to(path)
    with pytest.raises(OSError):
        password_auth.load(str(link))


@pytest.mark.parametrize('origin,loopback,valid', [
    ('https://owner.example', False, True), ('http://127.0.0.1:18000', False, False),
    ('http://127.0.0.1:18000', True, True), ('http://public.example', True, False),
    ('http://127.0.0.1.attacker.example', True, False), ('https://owner.example/path', False, False),
    ('https://user:password@owner.example', False, False), ('https://owner.example:bad', False, False),
])
def test_password_origin_policy(origin, loopback, valid):
    assert password_auth.origin_valid(origin, loopback) is valid


def test_password_session_csrf_logout_and_no_bearer_bypass(store, password_config, headers):
    with TestClient(create_app(password_config), base_url='https://testserver') as c:
        assert c.get('/api/state', headers=headers['owner']).status_code == 401
        response = login(c)
        assert response.status_code == 200 and response.json()['mfa_verified'] is False
        cookie = response.headers['set-cookie'].lower()
        assert 'secure' in cookie and 'httponly' in cookie and 'samesite=strict' in cookie
        assert PUBLIC_PASSWORD not in response.text
        csrf = response.json()['csrf_token']
        assert c.get('/api/state').status_code == 200
        assert c.post('/api/control/stop').status_code == 403
        assert c.post('/api/control/stop', headers={'X-CSRF-Token': csrf, 'Origin': 'https://evil.invalid'}).status_code == 403
        assert c.post('/api/control/stop', headers={'X-CSRF-Token': csrf}).status_code == 200
        csrf = c.get('/api/auth/csrf').json()['csrf_token']
        assert c.post('/api/auth/logout', headers={'X-CSRF-Token': csrf}).status_code == 200
        assert c.get('/api/state').status_code == 401


def test_password_bruteforce_survives_api_restart(store, password_config):
    with TestClient(create_app(password_config), base_url='https://testserver') as c:
        for _ in range(5):
            assert login(c, password='wrong').status_code == 401
    with TestClient(create_app(password_config), base_url='https://testserver') as c:
        assert login(c).status_code == 429
    events = json.dumps(store.snapshot()['events'])
    assert PUBLIC_PASSWORD not in events and '"password"' not in events


def test_password_parallel_attempts_share_durable_limit(store, password_config):
    from concurrent.futures import ThreadPoolExecutor
    def attempt(_):
        with TestClient(create_app(password_config), base_url='https://testserver') as c:
            return login(c, password='wrong').status_code
    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(attempt, range(6)))
    assert statuses.count(401) == 5 and statuses.count(429) == 1


def test_password_invalid_username_uses_same_error(store, password_config):
    with TestClient(create_app(password_config), base_url='https://testserver') as c:
        a = login(c, username='intruder')
        b = login(c, password='wrong')
        assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_password_expiry_rotation_and_revocation(store, password_config):
    with TestClient(create_app(password_config), base_url='https://testserver') as c:
        assert login(c).status_code == 200
        with store.transaction() as session:
            session.execute(text("UPDATE owner_sessions SET expires_at=clock_timestamp()-interval '1 second'"))
        assert c.get('/api/state').status_code == 401
        assert login(c).status_code == 200
        OwnerAuth(store).revoke(all_sessions=True)
        assert c.get('/api/state').status_code == 401
        assert login(c).status_code == 200
        Path(password_config.owner_password_file).write_text(json.dumps(password_auth.document('owner', PUBLIC_PASSWORD)))
        assert c.get('/api/state').status_code == 401


def test_password_requires_exact_origin_and_secure_transport(store, password_config):
    with TestClient(create_app(password_config), base_url='https://testserver') as c:
        assert login(c, origin='https://evil.invalid').status_code == 403
        assert c.post('/api/auth/login', json={'username': 'owner', 'password': PUBLIC_PASSWORD}).status_code == 403
    with TestClient(create_app(password_config), base_url='http://testserver') as c:
        assert login(c).status_code == 403
    configured = replace(password_config, web_origin='http://127.0.0.1:18000', password_loopback_http=True)
    with TestClient(create_app(configured), base_url=configured.web_origin) as c:
        r = login(c, origin=configured.web_origin)
        assert r.status_code == 200 and 'f1-loopback-session=' in r.headers['set-cookie']
        assert c.get('/api/state').status_code == 200
        assert c.get('/api/state', headers={'Host': 'evil.invalid'}).status_code == 401


def test_password_missing_config_and_oidc_cannot_use_login(store, password_config, settings):
    Path(password_config.owner_password_file).unlink()
    with TestClient(create_app(password_config), base_url='https://testserver') as c:
        assert login(c).status_code == 503 and c.get('/api/state').status_code == 401
    with TestClient(create_app(replace(settings, auth_mode='oidc')), base_url='https://testserver') as c:
        assert login(c).status_code == 503


def test_password_fails_closed_on_database_and_audit_failure(store, admin, password_config):
    from unittest.mock import patch
    from sqlalchemy.exc import OperationalError
    with TestClient(create_app(password_config), base_url='https://testserver') as c:
        with patch('command_center.owner_auth.OwnerAuth.password_login', side_effect=OperationalError('x', {}, Exception())):
            response = login(c)
            assert response.status_code == 503 and 'set-cookie' not in response.headers
        with admin.transaction() as session:
            session.execute(text("UPDATE audit SET digest=repeat('f',64) WHERE sequence=(SELECT min(sequence) FROM audit)"))
        response = login(c)
        assert response.status_code == 409 and 'set-cookie' not in response.headers


def test_rotation_during_verification_cannot_authorize_old_password(store, password_config, monkeypatch):
    original = password_auth.verify
    def rotate(value, username, password):
        valid = original(value, username, password)
        Path(password_config.owner_password_file).write_text(json.dumps(password_auth.document('owner', PUBLIC_PASSWORD)))
        return valid
    monkeypatch.setattr(password_auth, 'verify', rotate)
    with TestClient(create_app(password_config), base_url='https://testserver') as c:
        assert login(c).status_code == 200
        assert c.get('/api/state').status_code == 401
