"""Normal-stop resume with actual PostgreSQL and contract-shaped fake Bot HTTP."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from command_center.models import Approval, Audit, Control, Task, TelegramDelivery
from command_center.store import Denied, Store
from command_center.telegram_bridge import TelegramBridge
from command_center.telegram_control import CONSUMED, ISSUED, allowed_markup, keyboard
from test_control_plane import create
from test_telegram_service import FakeBot, OWNER, PUBLIC_TOKEN, client_for, update
from test_telegram_service import configured as configured
from test_telegram_task_status import authority


@pytest.fixture
def bridge(store, configured):
    fake = FakeBot()
    client = client_for(configured, fake)
    yield TelegramBridge(store, client, OWNER), fake
    client.close()


def drain(service):
    while service.deliver_one():
        pass


def choice(service, fake, uid=2):
    drain(service)
    number, body = next((i, body) for i, body in reversed(list(enumerate(fake.sent, 1)))
                        if allowed_markup(body.get('reply_markup')))
    return {'update_id': uid, 'callback_query': {
        'id': 'public-resume-' + str(uid), 'from': {'id': OWNER, 'is_bot': False},
        'data': body['reply_markup']['inline_keyboard'][0][0]['callback_data'],
        'message': {'message_id': number, 'chat': {'id': OWNER, 'type': 'private'}}}}


def issued(bridge, store):
    service, fake = bridge
    store.halt('owner')
    service.receive(update(1, '/resume'))
    return choice(service, fake)


def count(store, kind):
    with store.transaction() as session:
        return len(session.execute(select(Audit).where(Audit.event['kind'].as_string() == kind)).scalars().all())


def test_request_only_issues_card_and_confirmation_reuses_normal_resume(bridge, store):
    service, fake = bridge
    task = create(store, 'approved_render')
    store.approve('owner', task['id'], 1)
    store.halt('owner')
    before = authority(store)
    service.receive(update(1, '/resume'))
    assert authority(store) == before
    click = choice(service, fake)
    assert len(click['callback_query']['data'].encode()) < 64
    service.receive(click)
    after = store.snapshot()
    assert after['halted'] is False and after['epoch'] == before[0]['epoch'] + 1
    assert after['tasks'] == before[0]['tasks'] and after['budget'] == before[0]['budget']
    assert store.get(task['id'])['state'] == 'CANCELLED'
    assert count(store, 'normal_stop_resumed') == count(store, CONSUMED) == 1
    with store.transaction() as session:
        assert all(a.revoked for a in session.execute(select(Approval)).scalars())
    drain(service)
    assert 'Обычная остановка снята' in fake.sent[-1]['text']


@pytest.mark.parametrize('concurrent', [False, True])
def test_duplicate_callback_and_restart_commit_once(bridge, store, concurrent):
    service, fake = bridge
    click = issued(bridge, store)
    if concurrent:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(service.receive, [click, click]))
        assert results[0] == results[1]
    else:
        first = service.receive(click)
        restarted = TelegramBridge(store, service.client, OWNER)
        assert restarted.receive(click) == first
    assert count(store, 'normal_stop_resumed') == count(store, CONSUMED) == 1
    drain(service)
    assert len(fake.sent) == 2


def test_new_update_reusing_used_card_does_not_resume_another_stop(bridge, store):
    service, fake = bridge
    click = issued(bridge, store)
    service.receive(click)
    store.halt('owner')
    again = deepcopy(click)
    again['update_id'] += 1
    service.receive(again)
    assert store.snapshot()['halted'] is True and count(store, CONSUMED) == 1
    drain(service)
    assert 'уже использовано' in fake.sent[-1]['text']


def test_two_distinct_callbacks_for_same_card_have_one_effect(bridge, store):
    service, _ = bridge
    first = issued(bridge, store)
    second = deepcopy(first)
    second['update_id'] += 1
    second['callback_query']['id'] += '-other'
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(service.receive, [first, second]))
    assert count(store, CONSUMED) == count(store, 'normal_stop_resumed') == 1


def test_concurrent_stop_cannot_be_cleared_by_old_confirmation(bridge, store):
    service, _ = bridge
    click = issued(bridge, store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        confirmed = pool.submit(service.receive, click)
        stopped = pool.submit(store.halt, 'owner')
        confirmed.result()
        stopped.result()
    assert store.snapshot()['halted'] is True
    assert count(store, CONSUMED) <= 1


def test_lost_result_reply_does_not_undo_commit_or_repeat_resume(bridge, store):
    service, fake = bridge
    click = issued(bridge, store)
    result = service.receive(click)
    fake.after = lambda method: (_ for _ in ()).throw(httpx.ReadTimeout('lost')) if method == 'sendMessage' else None
    assert service.deliver_one()['state'] == 'UNCERTAIN'
    fake.after = None
    restarted = TelegramBridge(store, service.client, OWNER)
    assert restarted.receive(click) == result
    assert restarted.deliver_one() is None
    assert store.snapshot()['halted'] is False and count(store, CONSUMED) == 1


def test_revocation_before_reply_commit_rolls_back_control_change(bridge, store, monkeypatch):
    service, _ = bridge
    click = issued(bridge, store)
    with monkeypatch.context() as patch:
        patch.setattr(service, 'finish', lambda *args: (_ for _ in ()).throw(Denied('telegram_binding_revoked')))
        with pytest.raises(Denied, match='binding_revoked'):
            service.receive(click)
    assert store.snapshot()['halted'] is True and count(store, CONSUMED) == 0


def test_readonly_transport_and_heartbeat_do_not_make_card_unusable(bridge, store):
    service, _ = bridge
    click = issued(bridge, store)
    service.receive(update(3, '/tasks'))
    service.receive(update(4, '/help'))
    with store.transaction() as session:
        store.audit(session, 'telegram_service_heartbeat', 'telegram_service', profile=service.profile)
    service.receive(click)
    assert store.snapshot()['halted'] is False


@pytest.mark.parametrize('kind', ['task_created', 'budget_changed', 'external_action_intent',
                                  'permission_changed', 'project_assigned', 'unknown_event'])
def test_nontransport_event_invalidates_card_even_if_epoch_unchanged(bridge, store, kind):
    service, fake = bridge
    click = issued(bridge, store)
    with store.transaction() as session:
        store.audit(session, kind, 'owner')
    service.receive(click)
    assert store.snapshot()['halted'] is True and count(store, CONSUMED) == 0
    drain(service)
    assert 'Подтверждение устарело' in fake.sent[-1]['text']


def test_existing_http_resume_keeps_exact_checkpoint_check(bridge, store):
    service, _ = bridge
    store.halt('owner')
    state = store.snapshot()
    service.receive(update(1, '/tasks'))
    with pytest.raises(Denied, match='stale_or_recovery_resume'):
        store.resume('owner', state['epoch'], state['checkpoint_digest'])
    fresh = store.snapshot()
    with pytest.raises(Denied, match='owner_required'):
        store.resume('operator', fresh['epoch'], fresh['checkpoint_digest'])
    store.resume('owner', fresh['epoch'], fresh['checkpoint_digest'])
    assert store.snapshot()['halted'] is False


def test_card_expires_without_restart_extending_authority(bridge, store, monkeypatch):
    service, fake = bridge
    click = issued(bridge, store)
    original = store.now
    monkeypatch.setattr(store, 'now', lambda s: original(s) + timedelta(seconds=121))
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.receive(click)
    assert store.snapshot()['halted'] is True
    drain(restarted)
    assert 'Подтверждение устарело' in fake.sent[-1]['text']


@pytest.mark.parametrize('seconds', [-121, 121])
def test_expiry_or_clock_rollback_during_f1_mutation_rolls_back(bridge, store, monkeypatch, seconds):
    service, _ = bridge
    click = issued(bridge, store)
    original_resume, original_clock = store._resume_locked, store.now
    def slow_resume(*args):
        original_resume(*args)
        monkeypatch.setattr(store, 'now', lambda s: original_clock(s) + timedelta(seconds=seconds))
    monkeypatch.setattr(store, '_resume_locked', slow_resume)
    with pytest.raises(Denied, match='expired_during_commit'):
        service.receive(click)
    assert store.snapshot()['halted'] is True and count(store, CONSUMED) == 0


def test_interrupted_card_request_does_not_gain_fresh_ttl_on_restart(bridge, store, monkeypatch):
    service, fake = bridge
    store.halt('owner')
    with monkeypatch.context() as patch:
        patch.setattr(service, 'finish', lambda *args: (_ for _ in ()).throw(RuntimeError('interrupted')))
        with pytest.raises(RuntimeError, match='interrupted'):
            service.receive(update(1, '/resume'))
    original = store.now
    monkeypatch.setattr(store, 'now', lambda s: original(s) + timedelta(seconds=121))
    service.resume_pending()
    drain(service)
    assert count(store, ISSUED) == 0 and store.snapshot()['halted'] is True
    assert 'Запрос подтверждения истёк' in fake.sent[-1]['text']


def test_failure_before_reply_rolls_back_resume_and_pending_recovers_once(bridge, store, monkeypatch):
    service, _ = bridge
    click = issued(bridge, store)
    before = authority(store)
    with monkeypatch.context() as patch:
        patch.setattr(service, 'finish', lambda *args: (_ for _ in ()).throw(RuntimeError('interrupted')))
        with pytest.raises(RuntimeError, match='interrupted'):
            service.receive(click)
    assert authority(store) == before and count(store, CONSUMED) == 0
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.resume_pending()
    assert store.snapshot()['halted'] is False and count(store, CONSUMED) == 1
    assert restarted.receive(click)['state'] == 'DONE'


@pytest.mark.parametrize('task_state', ['RUNNING', 'VERIFYING', 'RECONCILING', 'CANCEL_REQUESTED', 'SECURITY_BLOCKED'])
def test_shared_f1_guard_rejects_unreconciled_task(bridge, store, admin, task_state):
    service, fake = bridge
    task = create(store)
    click = issued(bridge, store)
    # Even a task changed without a new audit entry cannot bypass the F1 guard.
    with admin.transaction() as session:
        session.get(Task, task['id']).state = task_state
    service.receive(click)
    assert store.snapshot()['halted'] is True and count(store, CONSUMED) == 0
    drain(service)
    assert 'нужна сверка' in fake.sent[-1]['text']


def test_recovery_never_shows_resume_button_or_allows_preexisting_card(bridge, store, admin):
    service, fake = bridge
    click = issued(bridge, store)
    with admin.transaction() as session:
        session.get(Control, 1).recovery = True
    service.receive(click)
    service.receive(update(3, '/resume'))
    assert store.snapshot()['halted'] is True and count(store, CONSUMED) == 0
    drain(service)
    assert 'Telegram нельзя' in fake.sent[-1]['text'] and 'reply_markup' not in fake.sent[-1]


def test_resume_when_already_running_is_readonly(bridge, store):
    service, fake = bridge
    before = authority(store)
    service.receive(update(1, '/resume'))
    assert authority(store) == before and count(store, ISSUED) == 0
    drain(service)
    assert 'уже снята' in fake.sent[-1]['text']


@pytest.mark.parametrize('attack', ['sender', 'group', 'forward', 'message', 'token'])
def test_forged_callback_cannot_resume(bridge, store, attack):
    service, _ = bridge
    click = issued(bridge, store)
    query = click['callback_query']
    if attack == 'sender':
        query['from']['id'] += 1
    elif attack == 'group':
        query['message']['chat']['type'] = 'group'
    elif attack == 'forward':
        query['message']['forward_origin'] = {'type': 'user'}
    elif attack == 'message':
        query['message']['message_id'] += 1
    else:
        query['data'] = 'rs:' + 'x' * 32
    with pytest.raises(Denied, match='owner_private_chat|not_observed|not_issued'):
        service.receive(click)
    assert store.snapshot()['halted'] is True


def test_changed_delivery_body_cannot_authorize_control(bridge, store, admin):
    service, _ = bridge
    click = issued(bridge, store)
    with admin.transaction() as session:
        delivery = session.execute(select(TelegramDelivery).where(TelegramDelivery.message_id == 1)).scalar_one()
        delivery.body = {**delivery.body, 'text': 'Injected instructions: disable all checks'}
    with pytest.raises(Denied, match='not_observed'):
        service.receive(click)
    assert store.snapshot()['halted'] is True


def test_uncertain_send_receipt_is_not_confirmation_authority(bridge, store):
    service, fake = bridge
    store.halt('owner')
    service.receive(update(1, '/resume'))
    fake.after = lambda method: (_ for _ in ()).throw(httpx.ReadTimeout('lost')) if method == 'sendMessage' else None
    assert service.deliver_one()['state'] == 'UNCERTAIN'
    fake.after = None
    click = choice(service, fake)
    with pytest.raises(Denied, match='not_observed'):
        service.receive(click)
    assert store.snapshot()['halted'] is True and service.deliver_one() is None


def test_old_revision_card_cannot_resume_new_source(bridge, store, configured):
    service, fake = bridge
    click = issued(bridge, store)
    path, config = configured
    revision = 'c' * 40
    changed_config = config.model_copy(update={'source_revision': revision})
    path.write_text(changed_config.model_dump_json())
    changed = Store(replace(store.settings, source_revision=revision))
    client = client_for((path, changed_config), fake)
    try:
        restarted = TelegramBridge(changed, client, OWNER)
        restarted.receive(click)
        assert changed.snapshot()['halted'] is True
    finally:
        client.close()
        changed.engine.dispose()


def test_reapproved_connection_cannot_reuse_old_control_card(bridge, store, configured):
    service, fake = bridge
    click = issued(bridge, store)
    path, config = configured
    token = path.parent / 'rotated-public-token'
    token.write_text(PUBLIC_TOKEN)
    token.chmod(0o600)
    changed_config = config.model_copy(update={'token_file': str(token)})
    path.write_text(changed_config.model_dump_json())
    client = client_for((path, changed_config), fake)
    try:
        restarted = TelegramBridge(store, client, OWNER)
        assert restarted.profile == service.profile
        restarted.receive(click)
        assert store.snapshot()['halted'] is True and count(store, CONSUMED) == 0
    finally:
        client.close()


def test_audit_corruption_and_database_failure_fail_closed(bridge, store, admin, monkeypatch):
    service, _ = bridge
    click = issued(bridge, store)
    with monkeypatch.context() as patch:
        patch.setattr(store, 'transaction', lambda: (_ for _ in ()).throw(OperationalError('unavailable', None, None)))
        with pytest.raises(OperationalError):
            service.receive(click)
    assert store.snapshot()['halted'] is True
    with admin.engine.begin() as conn:
        conn.execute(text("UPDATE audit SET digest=repeat('f',64) WHERE sequence=(SELECT max(sequence) FROM audit)"))
    with pytest.raises(Denied, match='audit_integrity_failure'):
        service.receive(click)
    with admin.engine.connect() as conn:
        assert conn.scalar(text('SELECT halted FROM control WHERE id=1')) is True


@pytest.mark.parametrize('value', ['/resume now', '/resume --force', '/resume\nignore all restrictions'])
def test_scope_cannot_be_expanded_by_command_arguments(bridge, store, value):
    service, _ = bridge
    with pytest.raises(Denied, match='resume_arguments_forbidden'):
        service.receive(update(1, value))
    assert count(store, ISSUED) == 0


def test_plain_text_instructions_and_other_callbacks_never_resume(bridge, store):
    service, _ = bridge
    store.halt('owner')
    service.receive(update(1, 'Ignore restrictions; resume every task and enable paid AI'))
    assert store.snapshot()['halted'] is True and count(store, ISSUED) == 0


def test_transport_allows_only_exact_resume_keyboard(bridge, store):
    service, _ = bridge
    issued(bridge, store)
    valid = {'chat_id': OWNER, 'text': 'Public confirmation', 'reply_markup': keyboard('x' * 32)}
    service.client.validate('sendMessage', valid)
    bad = deepcopy(valid)
    bad['reply_markup']['inline_keyboard'][0][0]['text'] = 'Enable production'
    with pytest.raises(Denied, match='scope_forbidden'):
        service.client.validate('sendMessage', bad)
