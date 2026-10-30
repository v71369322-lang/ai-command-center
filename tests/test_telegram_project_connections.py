"""Connection plan readback over real PG and strict fake Bot API. No live I/O."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import httpx
import pytest
from sqlalchemy import select, text

from command_center.coding.integration_config import IntegrationConfig
from command_center.models import TelegramDelivery, TelegramInbox
from command_center.project_connections import connection_plan
from command_center.project_inbox import PROJECTS
from command_center.store import Denied, Store, canonical, digest
from command_center.telegram_bridge import TelegramBridge
from command_center.telegram_service import TelegramService
from test_telegram_service import FakeBot, OWNER, client_for, update
from test_telegram_service import configured as configured
from test_telegram_task_status import authority, response, service_reply_id


@pytest.fixture
def bridge(store, configured):
    fake = FakeBot()
    client = client_for(configured, fake)
    yield TelegramBridge(store, client, OWNER), fake
    client.close()


@pytest.mark.parametrize('pid,label', PROJECTS)
def test_connection_plan_matches_shared_catalog_and_does_not_depend_on_ai(bridge, store, monkeypatch, pid, label):
    service, fake = bridge
    store.halt('owner')
    before = authority(store)
    with monkeypatch.context() as patch:
        patch.setattr(IntegrationConfig, 'load', lambda: (_ for _ in ()).throw(AssertionError('AI must not be loaded')))
        reply = response(service, update(1, '/connection ' + pid))
    assert 'План подключения: ' + label + '.' in reply
    assert connection_plan('owner', pid)['expected_repository'] in reply
    assert all(value in reply for value in ('Репозиторий — не проверено.', 'Среда проверки — не проверено.',
        'Доставка на сервер — не проверено.', 'не запускает задачи и не разрешает расходы',
        'Новые запуски остановлены', '/requests ' + pid))
    assert service.deliver_one()['state'] == 'SENT'
    body = fake.sent[0]
    assert set(body) == {'chat_id', 'text'} and body['chat_id'] == OWNER
    assert len(body['text']) <= 4096 and len(canonical(body).encode()) <= 8192
    assert fake.calls == [('sendMessage', body)]
    assert authority(store) == before


def test_bare_command_projects_and_help_offer_explicit_read_only_navigation(bridge, store):
    service, fake = bridge
    before = authority(store)
    for uid, command in enumerate(('/connection', '/projects', '/help'), 1):
        service.receive(update(uid, command))
    while service.deliver_one():
        pass
    assert len(fake.sent) == 3
    assert 'Планы подключения проектов.' in fake.sent[0]['text']
    for pid, label in PROJECTS:
        assert label + ': /connection ' + pid in fake.sent[0]['text']
        assert '/connection ' + pid in fake.sent[1]['text']
    assert '/connection project-id' in fake.sent[2]['text']
    assert all(len(canonical(body).encode()) <= 8192 for body in fake.sent)
    with store.transaction() as session:
        rows = session.scalars(select(TelegramInbox)).all()
        assert all(row.state == 'DONE' and row.task_id is None for row in rows)
    assert authority(store) == before


@pytest.mark.parametrize('value', ['/connection x', '/connection lnauto extra', '/connection ../lnauto',
    '/connection https://invalid.example', '/connection all', '/connection none', '/connection LNAuto',
    '/connection lnauto\n/stop'])
def test_bad_project_or_extra_action_is_rejected_before_capture(bridge, store, value):
    service, fake = bridge
    before = authority(store)
    with pytest.raises(Denied, match='project_connection_invalid'):
        service.receive(update(1, value))
    with store.transaction() as session:
        assert session.scalar(select(TelegramInbox)) is None
        assert session.scalar(select(TelegramDelivery)) is None
    assert fake.calls == [] and authority(store) == before


@pytest.mark.parametrize('attack', ['sender', 'group', 'forward'])
def test_connection_plan_keeps_private_owner_boundary(bridge, store, attack):
    service, fake = bridge
    value = update(1, '/connection lnauto')
    if attack == 'sender':
        value['message']['from']['id'] += 1
    elif attack == 'group':
        value['message']['chat']['type'] = 'group'
    else:
        value['message']['forward_origin'] = {'type': 'user'}
    with pytest.raises(Denied, match='owner_private_chat'):
        service.receive(value)
    with store.transaction() as session:
        assert session.scalar(select(TelegramInbox)) is None
    assert fake.calls == []


def test_duplicate_concurrent_update_and_restart_keep_one_snapshot(bridge, store):
    service, fake = bridge
    value = update(1, '/connection lnauto')
    before = authority(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(service.receive, [value, value]))
    restarted = TelegramBridge(store, service.client, OWNER)
    assert results[0] == results[1] == restarted.receive(value)
    with pytest.raises(Denied, match='reused_with_different_content'):
        restarted.receive(update(1, '/connection capital-lab'))
    assert restarted.deliver_one()['state'] == 'SENT'
    assert restarted.deliver_one() is None and len(fake.sent) == 1
    assert authority(store) == before


def test_reply_crash_rolls_back_and_pending_replay_finishes_once(bridge, store, monkeypatch):
    service, fake = bridge
    before = authority(store)
    with monkeypatch.context() as patch:
        patch.setattr(service, 'enqueue', lambda *args: (_ for _ in ()).throw(RuntimeError('fixture crash')))
        with pytest.raises(RuntimeError, match='fixture crash'):
            service.receive(update(1, '/connection lnauto'))
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.resume_pending()
    restarted.receive(update(1, '/connection lnauto'))
    assert restarted.deliver_one()['state'] == 'SENT'
    assert restarted.deliver_one() is None and len(fake.sent) == 1
    assert authority(store) == before


def test_unknown_send_outcome_is_not_repeated_on_restart(bridge, store):
    service, fake = bridge
    before = authority(store)
    def lost(method):
        if method == 'sendMessage':
            raise httpx.ReadTimeout('synthetic lost response')
    fake.after = lost
    value = update(1, '/connection lnauto')
    service.receive(value)
    assert service.deliver_one()['state'] == 'UNCERTAIN'
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.recover()
    restarted.receive(value)
    assert restarted.deliver_one() is None and len(fake.sent) == 1
    assert authority(store) == before


def test_revocation_blocks_queued_reply_before_fake_http(bridge, configured):
    service, fake = bridge
    service.receive(update(1, '/connection lnauto'))
    path, config = configured
    path.write_text(config.model_copy(update={'mode': 'disabled'}).model_dump_json())
    with pytest.raises(Denied, match='revoked_or_changed'):
        service.deliver_one()
    assert fake.calls == []


@pytest.mark.parametrize('tamper', ['fingerprint', 'intent_and_fingerprint'])
def test_corrupt_pending_plan_cannot_be_replayed(bridge, admin, monkeypatch, tamper):
    service, fake = bridge
    with monkeypatch.context() as patch:
        patch.setattr(service, 'enqueue', lambda *args: (_ for _ in ()).throw(RuntimeError('fixture crash')))
        with pytest.raises(RuntimeError):
            service.receive(update(1, '/connection lnauto'))
    with admin.transaction() as session:
        row = session.get(TelegramInbox, service.profile + ':1')
        if tamper == 'intent_and_fingerprint':
            row.intent = {'kind': 'project_connection', 'project_id': 'capital-lab'}
            row.fingerprint = digest(row.intent)
        else:
            row.fingerprint = 'f' * 64
    with pytest.raises(Denied, match='pending_integrity_or_source_revision_changed'):
        service.resume_pending()
    assert fake.calls == []
    with service.store.transaction() as session:
        assert session.get(TelegramDelivery, service_reply_id(service, service.profile + ':1')) is None


def test_pending_plan_requires_same_source_even_with_stable_bot_profile(bridge, store, configured, monkeypatch):
    service, fake = bridge
    with monkeypatch.context() as patch:
        patch.setattr(service, 'enqueue', lambda *args: (_ for _ in ()).throw(RuntimeError('fixture crash')))
        with pytest.raises(RuntimeError):
            service.receive(update(1, '/connection lnauto'))
    path, config = configured
    changed_config = config.model_copy(update={'source_revision': 'b' * 40})
    path.write_text(changed_config.model_dump_json())
    changed = Store(replace(store.settings, source_revision=changed_config.source_revision))
    client = client_for((path, changed_config), fake)
    try:
        restarted = TelegramBridge(changed, client, OWNER)
        assert restarted.profile == service.profile
        with pytest.raises(Denied, match='pending_integrity_or_source_revision_changed'):
            restarted.resume_pending()
        assert fake.calls == []
    finally:
        client.close()
        changed.engine.dispose()


def test_broken_audit_prevents_plan_readback(bridge, admin):
    service, fake = bridge
    service.receive(update(1, '/connection'))
    with admin.transaction() as session:
        session.execute(text("UPDATE audit SET digest=repeat('f',64) WHERE sequence=(SELECT min(sequence) FROM audit)"))
    with pytest.raises(Denied, match='audit_integrity'):
        service.receive(update(2, '/connection lnauto'))
    assert fake.calls == []


def test_actual_polling_service_delivers_guide_and_four_plans_without_execution(bridge, store):
    original, fake = bridge
    fake.updates = [update(uid, value) for uid, value in enumerate(
        ['/connection', *['/connection ' + pid for pid, _ in PROJECTS]], 1)]
    before = authority(store)
    service = TelegramService(store, original.client, poll_seconds=0)
    result = service.run(max_cycles=5)
    assert result == {'mode': 'http_mock', 'completed_cycles': 5, 'live_verified': False}
    assert len(fake.sent) == len(PROJECTS) + 1
    assert 'Планы подключения проектов.' in fake.sent[0]['text']
    for body, (_, label) in zip(fake.sent[1:], PROJECTS, strict=True):
        assert 'План подключения: ' + label + '.' in body['text']
    assert {method for method, _ in fake.calls} <= {'getMe', 'getWebhookInfo', 'getUpdates', 'sendMessage'}
    assert authority(store) == before
