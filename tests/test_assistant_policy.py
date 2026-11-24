from copy import deepcopy

import httpx
import pytest

from command_center.assistant_policy import assistant_only, http_allowed
from command_center.deployment_profile import render, services, validate_manifest, validate_profile
from command_center.store import Denied
from command_center.telegram_bridge import MockTelegramHTTP, TelegramBridge
from test_deployment import release as release
from test_telegram_bridge import BotHTTP, OWNER, message


@pytest.mark.parametrize('value', ['', 'true', 'false', '2'])
def test_malformed_mode_never_enables_developer(value, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', value)
    with pytest.raises(RuntimeError, match='assistant_mode_invalid'):
        assistant_only()


@pytest.mark.parametrize('path', ['/api/simulator/commands', '/api/tasks/id/approve',
    '/api/tasks/id/retry', '/api/coding/tasks', '/api/experiments/first/task',
    '/api/project-inbox/coding/workspace', '/api/project-inbox/plan', '/api/integration/reconcile-billing'])
def test_http_developer_writes_rejected(path):
    assert not http_allowed('POST', path)


def test_profile_removes_runtime_without_widening_access(release):
    original, _ = release
    m = deepcopy(original['manifest'])
    m['assistant_only'] = True
    m['images'] = {'api': m['images']['api']}
    profile = render(original['compose'], m)
    validate_profile(profile, m)
    assert set(profile['services']) == services(m) == {'api', 'db', 'redis'}
    assert profile['services']['api']['environment']['F1_ASSISTANT_ONLY'] == '1'
    assert not any('sock' in v['target'] for s in profile['services'].values() for v in s.get('volumes', []))
    profile['services']['api']['environment'].pop('F1_ASSISTANT_ONLY')
    with pytest.raises(ValueError, match='assistant_mode_binding_changed'):
        validate_profile(profile, m)


@pytest.mark.parametrize('value', [False, 1, 'true'])
def test_profile_flag_strict(release, value):
    original, _ = release
    m = deepcopy(original['manifest']) | {'assistant_only': value}
    with pytest.raises(ValueError, match='assistant_restriction_only_required'):
        validate_manifest(m)


def test_store_cannot_create_approve_claim_or_retry(store, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    for call in [lambda: store.create('owner', 'test', {'kind': 'render', 'cost': 0, 'text': 'test'}),
                 lambda: store.approve('owner', 'missing', 1),
                 lambda: store.claim('missing'), lambda: store.retry('owner', 'missing')]:
        with pytest.raises(Denied, match='developer_functionality_disabled'):
            call()
    assert store.snapshot()['tasks'] == []


def test_telegram_blocks_developer_but_keeps_capture(store, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    fake = BotHTTP()
    client = MockTelegramHTTP(httpx.MockTransport(fake))
    try:
        bridge = TelegramBridge(store, client, OWNER)
        bridge.receive(message(1, '/demo test'))
        bridge.receive(message(2, 'Позвонить поставщику'))
        bridge.deliver_one()
        assert 'отключены' in fake.sent[-1]['text']
        assert store.snapshot()['tasks'] == []
    finally:
        client.close()


def test_personal_replies_do_not_send_owner_back_to_developer_setup(store, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    fake = BotHTTP()
    client = MockTelegramHTTP(httpx.MockTransport(fake))
    try:
        bridge = TelegramBridge(store, client, OWNER)
        for uid, value in enumerate(['Идея: новый десерт', '/requests', '/request 1',
                                     '/projects', '/project command-center', '/attention'], 1):
            bridge.receive(message(uid, value))
        while bridge.deliver_one():
            pass
        responses = '\n'.join(item['text'] for item in fake.sent)
        assert 'Сохранено во входящих' in responses
        assert 'Идея: новый десерт' in responses
        assert not any(token in responses for token in ['/develop', '/setup', '/connection',
                                                       'Ожидает планирования', 'GitHub App', 'Baseline:'])
    finally:
        client.close()


def test_real_http_rejects_owner_developer_routes(client, headers, store, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    for path in ['/api/simulator/commands', '/api/tasks/missing/approve', '/api/project-inbox/plan']:
        response = client.post(path, headers=headers['owner'], json={})
        assert response.status_code == 403
        assert response.json()['detail'] == 'developer_functionality_disabled'
    assert client.get('/api/health').status_code == 401
    assert client.get('/api/health', headers=headers['owner']).status_code == 200
    assert store.snapshot()['tasks'] == []


def test_disabled_pending_intent_never_reaches_old_handler(store, monkeypatch):
    from command_center.models import TelegramInbox
    from command_center.store import digest
    client = MockTelegramHTTP(httpx.MockTransport(BotHTTP()))
    try:
        bridge = TelegramBridge(store, client, OWNER)
        intent = {'kind': 'demo', 'text': 'old developer intent'}
        iid = bridge.profile + ':17'
        with store.transaction() as session:
            session.add(TelegramInbox(id=iid, profile=bridge.profile,
                fingerprint=digest(intent), intent=intent, state='RECEIVED', created_at=store.now(session)))
        monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
        bridge._apply_pending(iid, intent)
        assert store.snapshot()['tasks'] == []
        with store.transaction() as session:
            assert session.get(TelegramInbox, iid).state == 'DONE'
    finally:
        client.close()
