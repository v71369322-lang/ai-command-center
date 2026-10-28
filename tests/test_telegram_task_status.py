"""Read-only owner commands with real PostgreSQL and fake Bot API only."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from command_center.models import Approval, Audit, Outbox, TelegramDelivery, TelegramInbox
from command_center.store import Denied
from command_center.telegram_bridge import MockTelegramHTTP, TelegramBridge
from test_telegram_bridge import BotHTTP, OWNER, message


@pytest.fixture
def bridge(store):
    fake = BotHTTP()
    client = MockTelegramHTTP(httpx.MockTransport(fake))
    yield TelegramBridge(store, client, OWNER), fake
    client.close()


def response(service, update):
    result = service.receive(update)
    with service.store.transaction() as session:
        row = session.get(TelegramDelivery, service_reply_id(service, result['inbox_id']))
        assert row.body['chat_id'] == OWNER
        assert 'parse_mode' not in row.body and 'reply_markup' not in row.body
        return row.body['text']


def service_reply_id(service, inbox_id):
    from command_center.store import digest
    return digest({'profile': service.profile, 'event': inbox_id + ':reply'})


def authority(store):
    snapshot = store.snapshot()
    # Read-only queries are themselves durably journaled, but must not change
    # tasks, grants, dispatch intent, admission, epoch or budget.
    snapshot.pop('checkpoint_digest')
    snapshot.pop('events')
    with store.transaction() as session:
        return (snapshot, [(a.task_id, a.task_version, a.used, a.revoked) for a in
                session.execute(select(Approval)).scalars()],
                [(o.id, o.task_id, o.sent_at) for o in session.execute(select(Outbox)).scalars()])


def test_empty_commands_do_not_create_tasks_or_grant_authority(bridge, store):
    service, _ = bridge
    before = authority(store)
    assert 'пока нет' in response(service, message(1, '/tasks'))
    assert 'не найдена' in response(service, message(2, '/status ' + str(uuid4())))
    assert authority(store) == before


def test_queries_are_available_while_halted_and_duplicate_is_snapshot(bridge, store):
    service, _ = bridge
    task = service.receive(message(1, '/demo safe'))['task_id']
    before = authority(store)
    query = message(2, '/status ' + task)
    first = response(service, query)
    assert 'Ожидает отдельного подтверждения' in first
    assert authority(store) == before
    store.halt('owner')
    halted = authority(store)
    restarted = TelegramBridge(store, service.client, OWNER)
    assert response(restarted, query) == first
    fresh = response(restarted, message(3, '/tasks'))
    assert 'Новые запуски остановлены' in fresh and task in fresh
    assert authority(store) == halted
    with store.transaction() as session:
        assert session.scalar(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_delivery_queued',
            Audit.event['delivery_id'].as_string() == service_reply_id(service, service.profile + ':2')))
        assert len(session.execute(select(TelegramDelivery).where(
            TelegramDelivery.id == service_reply_id(service, service.profile + ':2'))).scalars().all()) == 1


def test_task_list_is_latest_five_and_excludes_plain_captures(bridge, store):
    service, _ = bridge
    ids = [service.receive(message(i, '/demo safe'))['task_id'] for i in range(1, 8)]
    service.receive(message(8, 'ordinary request awaiting AI planning'))
    before = authority(store)
    reply = response(service, message(9, '/tasks'))
    assert all(task in reply for task in ids[-5:])
    assert all(task not in reply for task in ids[:2])
    assert reply.index(ids[-1]) < reply.index(ids[-2])
    assert 'ordinary request' not in reply and len(reply) < 4096
    assert authority(store) == before


@pytest.mark.parametrize('scope', ['web', 'different_owner', 'forged_inbox_link'])
def test_status_and_list_cannot_read_outside_connection(bridge, store, admin, scope):
    service, _ = bridge
    own = service.receive(message(1, '/demo safe'))
    target = store.create('owner', 'not-telegram', {'kind': 'approved_render', 'values': {'request': 'web only'}})['id']
    if scope == 'different_owner':
        other = TelegramBridge(store, service.client, OWNER + 1)
        foreign = message(2, '/demo safe', owner=OWNER + 1, chat=OWNER + 1)
        target = other.receive(foreign)['task_id']
    elif scope == 'forged_inbox_link':
        with admin.transaction() as session:
            session.get(TelegramInbox, own['inbox_id']).task_id = target
    before = authority(store)
    reply = response(service, message(10, '/status ' + target))
    assert 'не найдена' in reply and target not in reply
    assert target not in response(service, message(11, '/tasks'))
    assert authority(store) == before


@pytest.mark.parametrize('attack', ['sender', 'group', 'forward', 'invalid_id'])
def test_unauthorized_or_malformed_queries_fail_closed(bridge, store, attack):
    service, _ = bridge
    update = message(1, '/tasks')
    if attack == 'sender':
        update['message']['from']['id'] += 1
    elif attack == 'group':
        update['message']['chat']['type'] = 'group'
    elif attack == 'forward':
        update['message']['forward_origin'] = {'type': 'user'}
    else:
        update['message']['text'] = '/status not-a-task'
    with pytest.raises(Denied):
        service.receive(update)
    assert store.snapshot()['tasks'] == []
    with store.transaction() as session:
        assert session.execute(select(TelegramDelivery)).first() is None


@pytest.mark.parametrize('state,expected', [
    ('READY', 'Ожидает исполнителя'), ('VERIFYING', 'Результат проверяется'),
    ('CANCEL_REQUESTED', 'фактическая остановка ещё не подтверждена'),
    ('CANCELLED', 'В записи задачи: отменена'),
    ('RECONCILING', 'Результат неопределён'), ('SECURITY_BLOCKED', 'заблокировано проверкой безопасности'),
    ('FAILED', 'не завершился успешно'), ('FUTURE_STATE', 'Неизвестное состояние'),
])
def test_fixed_status_explanations_do_not_echo_untrusted_task_fields(bridge, admin, state, expected):
    service, _ = bridge
    task_id = service.receive(message(1, '/demo safe'))['task_id']
    # Deliberate database fixtures test presentation, not actual execution.
    hidden = 'private-reason-and-artifact-not-for-telegram'
    with admin.transaction() as session:
        task = service.store.task(session, task_id)
        task.state, task.reason, task.artifact = state, hidden, hidden
    reply = response(service, message(2, '/status ' + task_id))
    assert expected in reply and hidden not in reply


def test_expired_running_lease_is_not_displayed_as_confirmed_execution(bridge, admin):
    service, _ = bridge
    task_id = service.receive(message(1, '/demo safe'))['task_id']
    with admin.transaction() as session:
        session.execute(text("UPDATE tasks SET state='RUNNING',lease_until=clock_timestamp()-interval '1 second' WHERE id=:id"), {'id': task_id})
    reply = response(service, message(2, '/status ' + task_id))
    assert 'текущее выполнение не подтверждено' in reply and 'Выполняется.' not in reply


@pytest.mark.parametrize('proof', ['missing', 'bad_hash', 'wrong_fence', 'wrong_revision', 'valid'])
def test_success_requires_hash_and_independent_source_fence_anchor(bridge, admin, proof):
    service, _ = bridge
    task_id = service.receive(message(1, '/demo safe'))['task_id']
    artifact = 'public synthetic fixture only'
    checksum = hashlib.sha256(artifact.encode()).hexdigest()
    with admin.transaction() as session:
        task = service.store.task(session, task_id)
        task.state, task.artifact, task.artifact_hash = 'SUCCEEDED', artifact, checksum
        if proof == 'bad_hash':
            task.artifact_hash = 'a' * 64
        if proof != 'missing':
            service.store.audit(session, 'verified', 'verifier', task_id,
                fence=task.fence + (1 if proof == 'wrong_fence' else 0), artifact_hash=checksum,
                **({'revision': 'b' * 40} if proof == 'wrong_revision' else {}))
    reply = response(service, message(2, '/status ' + task_id))
    if proof == 'valid':
        assert 'Результат независимо проверен' in reply and checksum in reply
    else:
        assert 'Успех не подтверждён' in reply and 'Результат независимо проверен' not in reply
    assert artifact not in reply


def test_concurrent_duplicate_status_has_one_reply(bridge, store):
    service, _ = bridge
    query = message(1, '/tasks')
    before = authority(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(service.receive, [query, query]))
    assert results[0] == results[1] and authority(store) == before
    with store.transaction() as session:
        assert len(session.execute(select(TelegramDelivery)).scalars().all()) == 1


def test_crash_before_reply_recovers_once_without_changing_task_authority(bridge, store, monkeypatch):
    service, _ = bridge
    task = service.receive(message(1, '/demo safe'))['task_id']
    before = authority(store)
    with monkeypatch.context() as patch:
        patch.setattr(service, 'finish', lambda *args: (_ for _ in ()).throw(RuntimeError('synthetic crash')))
        with pytest.raises(RuntimeError, match='synthetic crash'):
            service.receive(message(2, '/status ' + task))
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.resume_pending()
    restarted.resume_pending()
    reply = response(restarted, message(2, '/status ' + task))
    assert task in reply and 'Ожидает отдельного подтверждения' in reply
    assert authority(store) == before
    with store.transaction() as session:
        assert session.get(TelegramInbox, service.profile + ':2').state == 'DONE'
        assert session.get(TelegramDelivery, service_reply_id(service, service.profile + ':2')).state == 'NEW'


def test_revocation_after_read_prevents_reply_commit(bridge, monkeypatch, store):
    service, fake = bridge
    task = service.receive(message(1, '/demo safe'))['task_id']
    real_summary = service.task_summary
    def revoke(session, task):
        value = real_summary(session, task)
        monkeypatch.setattr(service, 'guard', lambda: (_ for _ in ()).throw(Denied('revoked')))
        return value
    monkeypatch.setattr(service, 'task_summary', revoke)
    with pytest.raises(Denied, match='revoked'):
        service.receive(message(2, '/status ' + task))
    with store.transaction() as session:
        assert session.get(TelegramDelivery, service_reply_id(service, service.profile + ':2')) is None
    assert fake.sent == []


def test_status_failure_never_sends_and_permission_revocation_is_checked(bridge, admin, monkeypatch):
    service, fake = bridge
    with monkeypatch.context() as patch:
        patch.setattr(service.store, 'transaction', lambda: (_ for _ in ()).throw(OperationalError('x', {}, Exception())))
        with pytest.raises(OperationalError):
            service.receive(message(1, '/tasks'))
    with monkeypatch.context() as patch:
        patch.setattr(service, 'guard', lambda: (_ for _ in ()).throw(Denied('revoked')))
        with pytest.raises(Denied, match='revoked'):
            service.receive(message(1, '/tasks'))
    with admin.transaction() as session:
        session.execute(text("UPDATE audit SET digest=repeat('f',64) WHERE sequence=(SELECT min(sequence) FROM audit)"))
    with pytest.raises(Denied, match='audit_integrity'):
        service.receive(message(1, '/tasks'))
    assert fake.sent == []


def test_revision_change_does_not_inherit_mock_profile_history(bridge, store):
    service, _ = bridge
    task = service.receive(message(1, '/demo safe'))['task_id']
    from command_center.store import Store
    other_store = Store(replace(store.settings, source_revision='a' * 40))
    try:
        other = TelegramBridge(other_store, service.client, OWNER)
        assert 'не найдена' in response(other, message(2, '/status ' + task))
    finally:
        other_store.engine.dispose()
