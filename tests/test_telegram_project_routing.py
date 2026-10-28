"""Telegram project labels reuse the API classifier, with atomic replies."""
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from sqlalchemy import select

from command_center.models import TelegramInbox, TelegramDelivery, Audit
from command_center.project_inbox import inbox, EVENT, classify
from command_center.store import Denied
from command_center.telegram_bridge import TelegramBridge, MockTelegramHTTP
from test_telegram_bridge import OWNER, BotHTTP, message
from test_telegram_task_status import authority, response
from test_project_inbox import body


@pytest.fixture
def bridge(store):
    fake = BotHTTP()
    client = MockTelegramHTTP(httpx.MockTransport(fake))
    yield TelegramBridge(store, client, OWNER), fake
    client.close()


@pytest.mark.parametrize('pid', ['command-center', 'vanilla-sugar', 'lnauto', 'capital-lab'])
def test_owner_routes_then_reads_same_project_in_api_and_bot(bridge, store, pid):
    service, _ = bridge
    service.receive(message(1, 'Public synthetic request'))
    before = authority(store)
    assert pid in response(service, message(2, '/projects'))
    reply = response(service, message(3, '/assign 1 ' + pid + ' 0'))
    assert 'выполнение не запускалось' in reply
    assert inbox(store, 'owner', pid)['requests'][0]['assignment_version'] == 1
    assert 'Версия назначения: 1' in response(service, message(4, '/request 1'))
    response(service, message(5, '/assign 1 none 1'))
    assert inbox(store, 'owner', 'unassigned')['requests'][0]['assignment_version'] == 2
    assert authority(store) == before


@pytest.mark.parametrize('text', ['/assign 1 crm.invalid 0', '/assign ../x lnauto 0',
    '/assign 1 lnauto -1', '/assign 1 lnauto 0 sudo', '/assign 1 lnauto 1001', '/assign 01 lnauto 0'])
def test_invalid_scope_is_not_captured_or_executed(bridge, store, text):
    service, _ = bridge
    with pytest.raises(Denied, match='assignment_invalid'):
        service.receive(message(1, text))
    assert store.snapshot()['tasks'] == []


def test_wrong_sender_and_other_profile_request_cannot_be_assigned(bridge, store):
    service, _ = bridge
    other = TelegramBridge(store, service.client, OWNER + 1)
    other.receive(message(1, 'Foreign request', owner=OWNER + 1, chat=OWNER + 1))
    with pytest.raises(Denied, match='not_found'):
        service.receive(message(2, '/assign 1 lnauto 0'))
    with pytest.raises(Denied, match='owner_private_chat'):
        service.receive(message(3, '/assign 1 lnauto 0', owner=OWNER + 1))
    assert inbox(store, 'owner')['requests'][0]['project_id'] is None


def test_duplicate_concurrent_and_restart_commit_once(bridge, store):
    service, _ = bridge
    service.receive(message(1, 'Public request'))
    command = message(2, '/assign 1 lnauto 0')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(service.receive, [command, command]))
    restarted = TelegramBridge(store, service.client, OWNER)
    assert results[0] == results[1] == restarted.receive(command)
    with store.transaction() as session:
        assert len(session.execute(select(Audit).where(Audit.event['kind'].as_string() == EVENT)).scalars().all()) == 1
        assert len(session.execute(select(TelegramDelivery)).scalars().all()) == 2


def test_reply_failure_rolls_back_assignment_and_recovers_without_redelivery(bridge, store, monkeypatch):
    service, _ = bridge
    service.receive(message(1, 'Public request'))
    with monkeypatch.context() as patch:
        patch.setattr(service, 'finish', lambda *args: (_ for _ in ()).throw(RuntimeError('crash')))
        with pytest.raises(RuntimeError, match='crash'):
            service.receive(message(2, '/assign 1 lnauto 0'))
    assert inbox(store, 'owner')['requests'][0]['assignment_version'] == 0
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.resume_pending()
    assert inbox(store, 'owner')['requests'][0]['assignment_version'] == 1
    assert restarted.receive(message(2, '/assign 1 lnauto 0'))['state'] == 'DONE'


def test_stale_pending_does_not_overwrite_web_selection(bridge, store, monkeypatch):
    service, _ = bridge
    request = service.receive(message(1, 'Public request'))
    with monkeypatch.context() as patch:
        patch.setattr(service, '_apply_pending', lambda *args: (_ for _ in ()).throw(RuntimeError('crash')))
        with pytest.raises(RuntimeError):
            service.receive(message(2, '/assign 1 lnauto 0'))
    classify(store, 'owner', **body(request['inbox_id'], 'vanilla-sugar'))
    service.resume_pending()
    assert inbox(store, 'owner')['requests'][0]['project_id'] == 'vanilla-sugar'
    with store.transaction() as session:
        assert session.get(TelegramInbox, service.profile + ':2').state == 'REJECTED'


def test_revocation_during_confirmation_rolls_back_everything(bridge, store, monkeypatch):
    service, _ = bridge
    service.receive(message(1, 'Public request'))
    with monkeypatch.context() as patch:
        patch.setattr(service, 'finish', lambda *args: (_ for _ in ()).throw(Denied('revoked')))
        with pytest.raises(Denied, match='revoked'):
            service.receive(message(2, '/assign 1 lnauto 0'))
    assert inbox(store, 'owner')['requests'][0]['assignment_version'] == 0
