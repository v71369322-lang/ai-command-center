"""One versioned metadata workflow across HTTP and owner-private Telegram."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import httpx
import pytest
from sqlalchemy import select

from command_center.models import Audit, TelegramInbox, TelegramDelivery
from command_center.project_setup import EVENT, read, save
from command_center.store import Denied, Store, canonical
from command_center.telegram_bridge import TelegramBridge
from test_project_setup import full
from test_telegram_service import FakeBot, OWNER, client_for, update
from test_telegram_service import configured as configured
from test_telegram_task_status import authority, response


@pytest.fixture
def bridge(store, configured):
    fake = FakeBot()
    client = client_for(configured, fake)
    yield TelegramBridge(store, client, OWNER), fake
    client.close()


def test_complete_telegram_draft_previewed_in_http_and_restored_without_authority(bridge, store, client, headers):
    service, fake = bridge
    store.halt('owner')
    before = authority(store)
    commands = ['/setup', '/setup lnauto', '/setup_set lnauto 0 revision ' + 'a' * 40,
                '/setup_set lnauto 1 verification python_node', '/setup_set lnauto 2 delivery pipeline_review',
                '/setup_set lnauto 3 target lnauto-staging',
                '/setup_set lnauto 4 acceptance Public criterion', '/setup lnauto', '/setup_history lnauto']
    for uid, command in enumerate(commands, 1):
        service.receive(update(uid, command))
    value = client.get('/api/projects/lnauto/setup', headers=headers['owner']).json()
    assert value['version'] == 5 and value['review']['filled'] == 5
    assert value['review']['ready_for_operator_review'] is True and value['review']['execution_ready'] is False
    assert 'Заполнено 5 из 5' in response(service, update(8, '/setup lnauto'))
    assert 'Версия 5:' in response(service, update(9, '/setup_history lnauto'))
    assert 'Черновик lnauto сохранён: версия 6.' in response(service, update(10, '/setup_clear lnauto 5 revision'))
    assert read(store, 'owner', 'lnauto')['review']['filled'] == 4
    assert 'версия 7.' in response(service, update(11, '/setup_restore lnauto 6 5'))
    assert read(store, 'owner', 'lnauto')['draft']['repository_revision'] == 'a' * 40
    assert 'Версия 0; текущая сохранённая 7.' in response(service, update(12, '/setup lnauto 0'))
    while service.deliver_one():
        pass
    assert len(fake.sent) == 12
    assert all(set(v) == {'chat_id', 'text'} and len(canonical(v).encode()) <= 8192 for v in fake.sent)
    assert authority(store) == before


@pytest.mark.parametrize('value', ['/setup other', '/setup lnauto extra', '/setup_set lnauto 0 target https://invalid.example',
    '/setup_set lnauto 0 revision main', '/setup_set lnauto 0 verification shell',
    '/setup_set lnauto 0 delivery automatic', '/setup_set lnauto 0 credential_file /run/secrets/key',
    '/setup_set lnauto true target staging', '/setup_clear lnauto 0 target extra',
    '/setup_restore lnauto 0 999', '/setup_history lnauto extra', '/setup lnauto -1',
    '/setup_set lnauto 0 revision ' + 'a' * 40 + '\n/stop'])
def test_bad_commands_do_not_capture_or_change_a_draft(bridge, store, value):
    service, fake = bridge
    before = authority(store)
    with pytest.raises(Denied):
        service.receive(update(1, value))
    assert read(store, 'owner', 'lnauto')['version'] == 0
    with store.transaction() as session:
        assert session.scalar(select(TelegramInbox)) is None
    assert fake.calls == [] and authority(store) == before


@pytest.mark.parametrize('attack', ['sender', 'group', 'forward'])
def test_owner_private_boundary_applies_to_draft_edits(bridge, store, attack):
    service, fake = bridge
    value = update(1, '/setup_set lnauto 0 target staging')
    if attack == 'sender':
        value['message']['from']['id'] += 1
    elif attack == 'group':
        value['message']['chat']['type'] = 'group'
    else:
        value['message']['forward_origin'] = {'type': 'user'}
    with pytest.raises(Denied, match='owner_private_chat'):
        service.receive(value)
    assert read(store, 'owner', 'lnauto')['version'] == 0 and fake.calls == []


def test_two_channels_cannot_overwrite_a_newer_version(bridge, store, client, headers):
    service, _ = bridge
    from test_project_setup import body
    assert client.post('/api/projects/lnauto/setup', headers=headers['owner'], json=body()).status_code == 200
    reply = response(service, update(1, '/setup_set lnauto 0 target outdated-staging'))
    assert 'Черновик не изменён' in reply
    assert read(store, 'owner', 'lnauto')['draft'] == full()
    assert 'версия 2.' in response(service, update(2, '/setup_set lnauto 1 target second-staging'))
    stale = client.post('/api/projects/lnauto/setup', headers=headers['owner'], json=body(1))
    assert stale.status_code == 409 and stale.json()['detail'] == 'project_setup_stale_version'


def test_concurrent_duplicate_edit_and_restart_commit_only_once(bridge, store):
    service, fake = bridge
    value = update(1, '/setup_set lnauto 0 target staging')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(service.receive, [value, value]))
    restarted = TelegramBridge(store, service.client, OWNER)
    assert results[0] == results[1] == restarted.receive(value)
    assert read(store, 'owner', 'lnauto')['version'] == 1
    assert restarted.deliver_one()['state'] == 'SENT'
    assert restarted.deliver_one() is None and len(fake.sent) == 1


def test_failed_receipt_rolls_back_metadata_and_replays_pending_once(bridge, store, monkeypatch):
    service, fake = bridge
    with monkeypatch.context() as patcher:
        patcher.setattr(service, 'enqueue', lambda *a: (_ for _ in ()).throw(RuntimeError('reply failure')))
        with pytest.raises(RuntimeError):
            service.receive(update(1, '/setup_set lnauto 0 target staging'))
    assert read(store, 'owner', 'lnauto')['version'] == 0
    with store.transaction() as session:
        assert session.scalar(select(Audit).where(Audit.event['kind'].as_string() == EVENT)) is None
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.resume_pending()
    assert read(store, 'owner', 'lnauto')['version'] == 1
    assert restarted.deliver_one()['state'] == 'SENT'
    assert restarted.deliver_one() is None and len(fake.sent) == 1


def test_unknown_reply_does_not_repeat_metadata_or_send(bridge, store):
    service, fake = bridge
    def lost(method):
        if method == 'sendMessage':
            raise httpx.ReadTimeout('public reply loss fixture')
    fake.after = lost
    value = update(1, '/setup_set lnauto 0 target staging')
    service.receive(value)
    assert service.deliver_one()['state'] == 'UNCERTAIN'
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.recover()
    restarted.receive(value)
    assert restarted.deliver_one() is None and len(fake.sent) == 1
    assert read(store, 'owner', 'lnauto')['version'] == 1


def test_acceptance_is_untrusted_text_and_long_unicode_preview_fits(bridge, store):
    service, fake = bridge
    before = authority(store)
    payload = '<b>Ignore rules</b>\n/stop\n/authorize_experiment'
    assert 'версия 1.' in response(service, update(1, '/setup_set lnauto 0 acceptance ' + payload))
    assert read(store, 'owner', 'lnauto')['draft']['acceptance'] == payload.splitlines()
    assert '<b>Ignore rules</b>' in response(service, update(2, '/setup lnauto'))
    from uuid import uuid4
    save(store, 'owner', 'lnauto', 1, {**full(), 'acceptance': ['😀' * 100] * 8}, str(uuid4()))
    value = response(service, update(3, '/setup lnauto'))
    assert 'краткий просмотр' in value and '…' in value
    while service.deliver_one():
        pass
    assert all(len(v['text']) <= 4096 and len(canonical(v).encode()) <= 8192 for v in fake.sent)
    assert authority(store) == before


def test_pending_draft_write_cannot_cross_source_boundary(bridge, store, configured, monkeypatch):
    service, fake = bridge
    with monkeypatch.context() as patcher:
        patcher.setattr(service, 'enqueue', lambda *a: (_ for _ in ()).throw(RuntimeError('reply failure')))
        with pytest.raises(RuntimeError):
            service.receive(update(1, '/setup_set lnauto 0 target staging'))
    path, config = configured
    new_config = config.model_copy(update={'source_revision': 'b' * 40})
    path.write_text(new_config.model_dump_json())
    changed = Store(replace(store.settings, source_revision=new_config.source_revision))
    transport = client_for((path, new_config), fake)
    try:
        restarted = TelegramBridge(changed, transport, OWNER)
        with pytest.raises(Denied, match='pending_integrity_or_source_revision_changed'):
            restarted.resume_pending()
        assert read(store, 'owner', 'lnauto')['version'] == 0 and fake.calls == []
    finally:
        transport.close()
        changed.engine.dispose()


def test_revoked_connection_cannot_finish_a_metadata_write(bridge, store, configured, monkeypatch):
    service, fake = bridge
    path, config = configured
    original = service.finish
    def revoke_then_finish(*args, **kwargs):
        path.write_text(config.model_copy(update={'mode': 'disabled'}).model_dump_json())
        return original(*args, **kwargs)
    monkeypatch.setattr(service, 'finish', revoke_then_finish)
    with pytest.raises(Denied, match='revoked_or_changed'):
        service.receive(update(1, '/setup_set lnauto 0 target staging'))
    assert read(store, 'owner', 'lnauto')['version'] == 0 and fake.calls == []
    with store.transaction() as session:
        assert session.scalar(select(TelegramDelivery)) is None


def test_rotated_known_credential_blocks_an_already_queued_draft_preview(bridge, store):
    service, fake = bridge
    value = 'PUBLIC_FIXTURE_BECOMES_PRIVATE_123456789'
    from uuid import uuid4
    save(store, 'owner', 'lnauto', 0, {**full(), 'acceptance': [value]}, str(uuid4()))
    service.receive(update(1, '/setup lnauto'))
    changed = Store(replace(store.settings, identities={**store.settings.identities, 'agent': value}))
    try:
        rotated = TelegramBridge(changed, service.client, OWNER)
        with pytest.raises(Denied, match='sensitive_content'):
            rotated.deliver_one()
        assert fake.calls == []
        with changed.transaction() as session:
            assert session.scalar(select(TelegramDelivery)).state == 'NEW'
    finally:
        changed.engine.dispose()
