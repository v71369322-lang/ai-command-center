"""Observed Bot API cards + PostgreSQL F1; all provider and Telegram I/O is mocked."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import hashlib
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from command_center.coding.integration_config import FileCredentials
from command_center.models import Approval, Audit, ExternalAction, ExternalGrant, Outbox, Task, TelegramDelivery
from command_center.planning_admission import PlanningProfile
from command_center.project_inbox import classify
from command_center.store import Denied, canonical
from command_center.telegram_bridge import TelegramBridge
from command_center.telegram_planning_authorize import ISSUED, CONSUMED, allowed_markup, keyboard, parse_callback
from test_telegram_readiness import bridge as bridge
from test_telegram_service import configured as configured, OWNER, update


@pytest.fixture
def profile(bridge, store, tmp_path, monkeypatch):
    service, _ = bridge
    rid = service.receive(update(10, 'Тестовый точный план очереди'))['inbox_id']
    classify(store, 'owner', rid, 'command-center', 0, str(uuid4()))
    service.receive(update(11, '/plan_prepare 10'))
    with store.transaction() as session:
        now = int(store.now(session).timestamp())
    value = PlanningProfile.model_validate({
        'tariff': {'model': 'public-synthetic-model', 'input_nano_rub': 1, 'output_nano_rub': 2,
            'context_tokens': 8192, 'max_output_tokens': 32, 'confirmed': True, 'evidence': 'SYNTHETIC_TARIFF'},
        'evidence': {'account': 'SYNTHETIC_ACCOUNT', 'model': 'SYNTHETIC_MODEL', 'funding': 'SYNTHETIC_FUNDING',
            'data_sharing': 'SYNTHETIC_DATA', 'observed_at': now - 10, 'expires_at': now + 900},
        'available_nano_rub': 1_000_000, 'daily_nano_rub': 1_000_000, 'monthly_nano_rub': 1_000_000})
    directory = tmp_path / 'planning-profile'
    directory.mkdir(mode=0o700)
    path = directory / 'profile.json'
    def save(changed=value):
        raw = changed.model_dump_json().encode()
        path.write_bytes(raw)
        path.chmod(0o600)
        monkeypatch.setenv('F1_PLANNING_PROFILE_FILE', str(path))
        monkeypatch.setenv('F1_PLANNING_PROFILE_SHA256', hashlib.sha256(raw).hexdigest())
    save()
    return value, save, path, rid


def rows(store, model):
    with store.transaction() as session:
        return list(session.scalars(select(model)))


def issue(bridge, uid=20):
    return bridge[0].receive(update(uid, '/plan_authorize 10'))


def click(bridge, uid=21):
    while bridge[0].deliver_one():
        pass
    number, body = next((i, b) for i, b in reversed(list(enumerate(bridge[1].sent, 1)))
                        if allowed_markup(b.get('reply_markup')))
    return callback(body, number, uid)


def callback(body, number, uid):
    return {'update_id': uid, 'callback_query': {'id': 'public-planning-confirm-' + str(uid),
        'from': {'id': OWNER, 'is_bot': False}, 'data': body['reply_markup']['inline_keyboard'][0][0]['callback_data'],
        'message': {'message_id': number, 'chat': {'id': OWNER, 'type': 'private'}}}}


def assert_no_authority(store):
    assert not rows(store, Approval) and not rows(store, ExternalGrant) and not rows(store, Outbox)
    assert not rows(store, ExternalAction)


def test_observed_owner_confirmation_is_atomic_and_client_free(bridge, store, profile, monkeypatch):
    monkeypatch.setattr(httpx, 'Client', lambda *a, **k: pytest.fail('no provider client'))
    monkeypatch.setattr(FileCredentials, 'get', lambda *a: pytest.fail('no provider credentials'))
    issue(bridge)
    assert_no_authority(store)
    button = click(bridge)
    body = bridge[1].sent[-1]['text']
    assert 'Тестовый точный план очереди' in body and profile[0].tariff.model in body
    assert '0.000008256 ₽' in body and '/plan 10' in body and 'срок не продлевается' in body
    assert 'SYNTHETIC_ACCOUNT' not in body and 'SYNTHETIC_TARIFF' not in body
    assert len(button['callback_query']['data'].encode()) < 64 and len(body) < 4096
    bridge[0].receive(button)
    assert len(rows(store, Approval)) == len(rows(store, ExternalGrant)) == len(rows(store, Outbox)) == 1
    assert rows(store, Task)[0].state == 'READY' and not rows(store, ExternalAction)
    grant = rows(store, ExternalGrant)[0].document
    assert grant['max_calls'] == 1 and grant['secret_refs'] == [] and not grant['business_execution']
    assert int(rows(store, Approval)[0].expires_at.timestamp()) == grant['review']['expires_at']
    assert sum(a.event['kind'] == CONSUMED for a in rows(store, Audit)) == 1


@pytest.mark.parametrize('change', ['profile', 'price', 'pin', 'missing', 'expiry', 'stop', 'project', 'connection'])
def test_changed_or_expired_conditions_never_authorize(bridge, store, profile, monkeypatch, change):
    issue(bridge)
    button = click(bridge)
    value, save, path, rid = profile
    if change in {'profile', 'price'}:
        value.tariff.model = 'replacement' if change == 'profile' else value.tariff.model
        if change == 'price':
            value.tariff.input_nano_rub += 1
        save()
    elif change == 'pin':
        path.write_text('{}')
    elif change == 'missing':
        monkeypatch.delenv('F1_PLANNING_PROFILE_FILE')
        monkeypatch.delenv('F1_PLANNING_PROFILE_SHA256')
    elif change == 'expiry':
        now = store.now
        monkeypatch.setattr(store, 'now', lambda session: now(session) + timedelta(seconds=121))
    elif change == 'stop':
        store.halt('owner')
    elif change == 'project':
        classify(store, 'owner', rid, 'lnauto', 1, str(uuid4()))
    else:
        bridge[0].client.approved = 'f' * 64
    with pytest.raises(Denied):
        bridge[0].receive(button)
    assert_no_authority(store)


@pytest.mark.parametrize('attack', ['owner', 'group', 'forward', 'message', 'nonce', 'label', 'body'])
def test_callback_and_display_binding(bridge, store, profile, attack):
    issue(bridge)
    button = click(bridge)
    query = button['callback_query']
    if attack == 'owner':
        query['from']['id'] += 1
    elif attack == 'group':
        query['message']['chat']['type'] = 'group'
    elif attack == 'forward':
        query['message']['forward_origin'] = {'type': 'user'}
    elif attack == 'message':
        query['message']['message_id'] += 100
    elif attack == 'nonce':
        query['data'] = 'pa:' + 'z' * 32
    else:
        with store.transaction() as session:
            row = next(r for r in session.scalars(select(TelegramDelivery)) if allowed_markup(r.body.get('reply_markup')))
            body = deepcopy(row.body)
            if attack == 'label':
                body['reply_markup']['inline_keyboard'][0][0]['text'] = 'Free test'
            else:
                body['text'] = 'Free test'
            row.body = body
    with pytest.raises(Denied):
        bridge[0].receive(button)
    assert_no_authority(store)


@pytest.mark.parametrize('state', ['NEW', 'SENDING', 'UNCERTAIN', 'SENT_without_receipt'])
def test_delivery_must_be_observed_sent(bridge, store, profile, state):
    issue(bridge)
    with store.transaction() as session:
        row = next(r for r in session.scalars(select(TelegramDelivery)) if allowed_markup(r.body.get('reply_markup')))
        body = deepcopy(row.body)
        row.state = 'SENT' if state == 'SENT_without_receipt' else state
        row.message_id = 123
    with pytest.raises(Denied, match='not_observed'):
        bridge[0].receive(callback(body, 123, 21))
    assert_no_authority(store)


@pytest.mark.parametrize('concurrent', [False, True])
def test_replay_restart_and_double_click_only_consume_once(bridge, store, profile, concurrent):
    issue(bridge)
    first = click(bridge)
    second = deepcopy(first)
    second['update_id'] += 1
    if concurrent:
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(bridge[0].receive, [first, second]))
    else:
        bridge[0].receive(first)
        restarted = TelegramBridge(store, bridge[0].client, OWNER)
        restarted.receive(first)
        restarted.receive(second)
    assert len(rows(store, ExternalGrant)) == len(rows(store, Approval)) == len(rows(store, Outbox)) == 1
    assert sum(a.event['kind'] == CONSUMED for a in rows(store, Audit)) == 1


def test_missing_profile_offers_no_card(bridge, store, monkeypatch):
    monkeypatch.delenv('F1_PLANNING_PROFILE_FILE', raising=False)
    monkeypatch.delenv('F1_PLANNING_PROFILE_SHA256', raising=False)
    issue(bridge)
    assert not any(a.event['kind'] == ISSUED for a in rows(store, Audit))
    assert_no_authority(store)


def test_consume_failure_rolls_back_card_and_f1_then_pending_recovers(bridge, store, profile, monkeypatch):
    issue(bridge)
    button = click(bridge)
    original = bridge[0].finish
    def fail(session, iid, *args, **kwargs):
        original(session, iid, *args, **kwargs)
        raise Denied('synthetic_finish_failure')
    monkeypatch.setattr(bridge[0], 'finish', fail)
    with pytest.raises(Denied):
        bridge[0].receive(button)
    assert_no_authority(store)
    assert not any(a.event['kind'] == CONSUMED for a in rows(store, Audit))
    monkeypatch.setattr(bridge[0], 'finish', original)
    bridge[0].resume_pending()
    assert len(rows(store, ExternalGrant)) == 1


def test_wrong_profile_number_cannot_offer_card(bridge, store, profile):
    bridge[0].receive(update(20, '/plan_authorize 999'))
    assert not any(a.event['kind'] == ISSUED for a in rows(store, Audit))
    assert_no_authority(store)


@pytest.mark.parametrize('value', ['/plan_authorize', '/plan_authorize x', '/plan_authorize 01',
                                   '/plan_authorize 10 extra', '/plan_authorize 9007199254740992'])
def test_command_reference_fails_closed(bridge, value):
    with pytest.raises(Denied, match='reference_invalid'):
        bridge[0].receive(update(20, value))


def test_maximum_request_text_is_displayed_without_truncation(bridge, store, profile):
    value = 'я' * 1000  # Exact maximum of 2000 UTF-8 bytes.
    rid = bridge[0].receive(update(30, value))['inbox_id']
    classify(store, 'owner', rid, 'command-center', 0, str(uuid4()))
    bridge[0].receive(update(31, '/plan_prepare 30'))
    bridge[0].receive(update(32, '/plan_authorize 30'))
    button = click(bridge, 33)
    body = bridge[1].sent[-1]
    assert value in body['text'] and len(canonical(body).encode()) <= 8192
    bridge[0].receive(button)
    assert len(rows(store, ExternalGrant)) == 1


def test_lost_delivery_receipt_never_authorizes(bridge, store, profile):
    issue(bridge)
    while bridge[0].deliver_one():
        # Stop after the unrelated saved-request/project/preparation messages.
        if any(allowed_markup(b.get('reply_markup')) for b in bridge[1].sent):
            pytest.fail('planning card should be held before delivery failure')
        with store.transaction() as session:
            pending = [r for r in session.scalars(select(TelegramDelivery)) if r.state == 'NEW']
        if len(pending) == 1 and allowed_markup(pending[0].body.get('reply_markup')):
            break
    def lose(method):
        if method == 'sendMessage':
            raise httpx.ReadTimeout('public synthetic delivery loss')
    bridge[1].after = lose
    bridge[0].deliver_one()
    body = bridge[1].sent[-1]
    with pytest.raises(Denied, match='not_observed'):
        bridge[0].receive(callback(body, len(bridge[1].sent), 21))
    assert_no_authority(store)


def test_old_pending_issue_cannot_get_fresh_consent_window(bridge, store, profile, monkeypatch):
    original = bridge[0]._apply_pending
    monkeypatch.setattr(bridge[0], '_apply_pending', lambda *a: (_ for _ in ()).throw(RuntimeError('synthetic crash')))
    with pytest.raises(RuntimeError):
        issue(bridge)
    monkeypatch.setattr(bridge[0], '_apply_pending', original)
    now = store.now
    monkeypatch.setattr(store, 'now', lambda session: now(session) + timedelta(seconds=121))
    bridge[0].resume_pending()
    assert not any(a.event['kind'] == ISSUED for a in rows(store, Audit))
    assert_no_authority(store)


@pytest.mark.parametrize('attack', ['label', 'url', 'extra_button', 'prefix'])
def test_transport_only_admits_exact_planning_keyboard(bridge, attack):
    markup = keyboard('a' * 32)
    button = markup['inline_keyboard'][0][0]
    if attack == 'label':
        button['text'] = 'Another action'
    elif attack == 'url':
        button['url'] = 'https://example.invalid/'
    elif attack == 'extra_button':
        markup['inline_keyboard'][0].append(deepcopy(button))
    else:
        button['callback_data'] = 'fx:' + 'a' * 32
    with pytest.raises(Denied):
        bridge[0].client.validate('sendMessage', {'chat_id': OWNER, 'text': 'Public fixture', 'reply_markup': markup})


@pytest.mark.parametrize('value', ['pa:short', 'pa:' + 'a' * 33, 'rs:' + 'a' * 32, 'pa:' + 'я' * 32])
def test_other_callback_shapes_rejected(value):
    with pytest.raises(Denied):
        parse_callback(value)


def test_help_with_new_commands_stays_inside_transport_limit(bridge):
    bridge[0].receive(update(20, '/help'))
    while bridge[0].deliver_one():
        pass
    body = bridge[1].sent[-1]
    assert '/plan_authorize номер' in body['text'] and '/plan_prepare номер' in body['text']
    assert len(canonical(body).encode()) <= 8192
