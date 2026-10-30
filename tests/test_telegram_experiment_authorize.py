"""Real PG and public, live-shaped declarations; no actual paid/provider calls."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import hashlib
import json

import httpx
import pytest
from sqlalchemy import select, text

from command_center.coding.first_experiment import Evidence, REQUIRED, create_task, task_payload
from command_center.coding.gateway import Gateway
from command_center.coding.integration_config import FileCredentials
from command_center.models import Approval, Audit, Control, ExternalAction, ExternalGrant, Outbox, Task, TelegramDelivery
from command_center.store import Denied
from command_center.telegram_bridge import TelegramBridge
from command_center.telegram_experiment_authorize import CONSUMED, ISSUED, allowed_markup, keyboard, parse_callback
from command_center.telegram_service import TelegramService
from test_first_experiment import experiment_config
from test_telegram_readiness import bridge as bridge, ledger
from test_telegram_service import OWNER, configured as configured, update
from test_telegram_task_status import authority


@pytest.fixture
def profile(tmp_path, store, monkeypatch):
    config = experiment_config(live=True)
    with store.transaction() as session:
        expires = store.now(session) + timedelta(minutes=10)
    config.first_experiment.evidence = {key: Evidence(reference='PUBLIC_FIXTURE_NOT_LIVE_PROOF',
        expires_at=expires.isoformat()) for key in REQUIRED}
    path = tmp_path / 'public-profile.json'

    def save(value=config):
        raw = json.dumps({**value.model_dump(), 'credential_files': value.credential_files}).encode()
        path.write_bytes(raw)
        path.chmod(0o600)
        monkeypatch.setenv('F2_INTEGRATION_CONFIG_FILE', str(path))
        monkeypatch.setenv('F2_INTEGRATION_CONFIG_SHA256', hashlib.sha256(raw).hexdigest())

    save()
    create_task(store, 'owner')
    return config, save, path


def issue(bridge, uid=1):
    bridge[0].receive(update(uid, '/authorize_experiment'))


def click(bridge, uid=2):
    while bridge[0].deliver_one():
        pass
    number, body = next((i, b) for i, b in reversed(list(enumerate(bridge[1].sent, 1)))
                        if allowed_markup(b.get('reply_markup')))
    return {'update_id': uid, 'callback_query': {'id': 'public-paid-confirmation-' + str(uid),
        'from': {'id': OWNER, 'is_bot': False}, 'data': body['reply_markup']['inline_keyboard'][0][0]['callback_data'],
        'message': {'message_id': number, 'chat': {'id': OWNER, 'type': 'private'}}}}


def rows(store, model):
    with store.transaction() as session:
        return list(session.scalars(select(model)))


def test_request_only_displays_terms_then_observed_owner_click_reuses_f1_without_http(bridge, store, profile, monkeypatch):
    before = authority(store), ledger(store)
    monkeypatch.setattr(Gateway, '__init__', lambda *a, **k: pytest.fail('no gateway construction'))
    monkeypatch.setattr(FileCredentials, 'get', lambda *a: pytest.fail('no provider credential read'))
    monkeypatch.setattr(httpx, 'Client', lambda *a, **k: pytest.fail('no new HTTP client'))
    issue(bridge)
    assert (authority(store), ledger(store)) == before
    assert not rows(store, Approval) and not rows(store, ExternalGrant) and not rows(store, Outbox)
    button = click(bridge)
    body = bridge[1].sent[-1]['text']
    assert '55.65888 ₽' in body and profile[0].first_experiment.model in body
    assert profile[0].synthetic_repository in body and 'реальные AI-вызовы' in body
    assert 'PUBLIC_FIXTURE' not in body and '/fixture/' not in body
    assert len(button['callback_query']['data'].encode()) < 64
    bridge[0].receive(button)
    task = store.snapshot()['tasks'][0]
    assert task['state'] == 'READY'
    assert len(rows(store, Approval)) == len(rows(store, ExternalGrant)) == len(rows(store, Outbox)) == 1
    grant = rows(store, ExternalGrant)[0]
    assert grant.document['final_confirmation'] is True and grant.document['mode'] == 'live'
    assert grant.document['budget'] == profile[0].tariff.maximum() * 2
    assert not rows(store, ExternalAction)
    assert sum(a.event['kind'] == CONSUMED for a in rows(store, Audit)) == 1


@pytest.mark.parametrize('missing', REQUIRED)
def test_each_missing_gate_prevents_paid_card(bridge, store, profile, missing):
    config, save, _ = profile
    config.first_experiment.evidence.pop(missing)
    save()
    before = authority(store), ledger(store)
    issue(bridge)
    assert (authority(store), ledger(store)) == before
    assert not any(a.event['kind'] == ISSUED for a in rows(store, Audit))
    assert not any(allowed_markup(r.body.get('reply_markup')) for r in rows(store, TelegramDelivery))


@pytest.mark.parametrize('blocked', ['disabled', 'mock', 'live_flag', 'tariff', 'capacity', 'halt', 'recovery', 'state',
                                   'payment_bound', 'underpriced', 'funding', 'output', 'context', 'model'])
def test_unready_profile_or_control_cannot_offer_paid_confirmation(bridge, store, profile, blocked):
    config, save, _ = profile
    if blocked == 'disabled':
        config.mode = 'disabled'
    elif blocked == 'mock':
        config.mode = 'http_mock'
    elif blocked == 'live_flag':
        config.live_authorized = False
    elif blocked == 'tariff':
        config.tariff.confirmed = False
    elif blocked == 'capacity':
        config.monthly_nano_rub = 1
    elif blocked == 'payment_bound':
        config.first_experiment.payment_rub_per_usd_upper = '200'
    elif blocked == 'underpriced':
        config.tariff.input_nano_rub = 1
    elif blocked == 'funding':
        config.first_experiment.existing_credit_usd = '0'
    elif blocked == 'output':
        config.tariff.max_output_tokens = 2049
    elif blocked == 'context':
        config.tariff.context_tokens = 8192
    elif blocked == 'model':
        config.tariff.model = 'unapproved-model'
    elif blocked == 'state':
        with store.transaction() as session:
            session.scalar(select(Task)).state = 'READY'
    else:
        store.halt('owner')
        if blocked == 'recovery':
            with store.transaction() as session:
                session.get(Control, 1).recovery = True
                store.audit(session, 'fixture_recovery', 'system')
    save()
    before = authority(store), ledger(store)
    issue(bridge)
    assert (authority(store), ledger(store)) == before
    assert not any(a.event['kind'] == ISSUED for a in rows(store, Audit))


@pytest.mark.parametrize('concurrent', [False, True])
def test_duplicate_update_and_restart_authorize_exactly_once(bridge, store, profile, concurrent):
    issue(bridge)
    button = click(bridge)
    if concurrent:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(bridge[0].receive, [button, button]))
        assert results[0] == results[1]
    else:
        result = bridge[0].receive(button)
        restarted = TelegramBridge(store, bridge[0].client, OWNER)
        assert restarted.receive(button) == result
    assert len(rows(store, Approval)) == len(rows(store, ExternalGrant)) == len(rows(store, Outbox)) == 1
    assert sum(a.event['kind'] == CONSUMED for a in rows(store, Audit)) == 1


def test_distinct_callbacks_for_same_card_have_one_grant(bridge, store, profile):
    issue(bridge)
    first = click(bridge)
    second = deepcopy(first)
    second['update_id'] += 1
    second['callback_query']['id'] += '-second'
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(bridge[0].receive, [first, second]))
    assert len(rows(store, Approval)) == len(rows(store, ExternalGrant)) == len(rows(store, Outbox)) == 1


@pytest.mark.parametrize('change', ['expiry', 'stop', 'stop_resume', 'recovery', 'version', 'epoch', 'source',
                                  'payload', 'config', 'price', 'references', 'byte_pin', 'connection'])
def test_stale_card_cannot_grant_when_bound_inputs_change(bridge, store, profile, monkeypatch, admin, change):
    issue(bridge)
    button = click(bridge)
    config, save, path = profile
    if change == 'expiry':
        now = store.now
        monkeypatch.setattr(store, 'now', lambda s: now(s) + timedelta(seconds=121))
    elif change in {'stop', 'stop_resume'}:
        store.halt('owner')
        if change == 'stop_resume':
            view = store.snapshot()
            store.resume('owner', view['epoch'], view['checkpoint_digest'])
    elif change in {'version', 'epoch', 'recovery'}:
        with store.transaction() as session:
            if change == 'recovery':
                session.get(Control, 1).recovery = True
            else:
                task = session.scalar(select(Task))
                setattr(task, change, getattr(task, change) + 1)
            store.audit(session, 'fixture_change', 'system')
    elif change == 'source':
        monkeypatch.setattr(store, 'settings', replace(store.settings, source_revision='a' * 40))
    elif change == 'payload':
        with admin.transaction() as session:
            session.execute(text("UPDATE tasks SET payload=jsonb_set(payload,'{cost}','2.0'::jsonb)"))
    elif change in {'config', 'price', 'references'}:
        if change == 'config':
            config.budget_evidence += ' changed'
        elif change == 'price':
            config.tariff.input_nano_rub += 1
        else:
            config.credential_files['openai'] += '-changed'
        save()
    elif change == 'byte_pin':
        path.write_text('{}')
    else:
        config_path = bridge[0].client.config_file
        value = bridge[0].client.config.model_copy(update={'mode': 'disabled'})
        from pathlib import Path
        Path(config_path).write_text(value.model_dump_json())
    before = ledger(store)
    with pytest.raises(Denied):
        bridge[0].receive(button)
    assert ledger(store) == before
    assert not rows(store, ExternalGrant) and not rows(store, Outbox)


@pytest.mark.parametrize('attack', ['owner', 'group', 'message', 'nonce', 'forward', 'label', 'body'])
def test_forged_callback_or_changed_display_never_authorizes(bridge, store, profile, attack):
    issue(bridge)
    button = click(bridge)
    if attack == 'owner':
        button['callback_query']['from']['id'] += 1
    elif attack == 'group':
        button['callback_query']['message']['chat']['type'] = 'group'
    elif attack == 'message':
        button['callback_query']['message']['message_id'] += 10
    elif attack == 'nonce':
        button['callback_query']['data'] = 'fx:' + 'a' * 32
    elif attack == 'forward':
        button['callback_query']['message']['forward_origin'] = {'type': 'user'}
    else:
        with store.transaction() as session:
            row = session.scalar(select(TelegramDelivery))
            body = deepcopy(row.body)
            if attack == 'label':
                body['reply_markup']['inline_keyboard'][0][0]['text'] = 'Free demo'
            else:
                body['text'] = 'Free demo, no actual spending'
            row.body = body
    with pytest.raises(Denied):
        bridge[0].receive(button)
    assert not rows(store, Approval) and not rows(store, ExternalGrant) and not rows(store, Outbox)


@pytest.mark.parametrize('state', ['NEW', 'SENDING', 'UNCERTAIN', 'SENT_without_receipt'])
def test_card_must_have_a_confirmed_sent_receipt(bridge, store, profile, state):
    issue(bridge)
    with store.transaction() as session:
        delivery = session.scalar(select(TelegramDelivery))
        body = deepcopy(delivery.body)
        delivery.state = 'SENT' if state == 'SENT_without_receipt' else state
        delivery.message_id = 123
    button = {'update_id': 2, 'callback_query': {'id': 'public-unobserved-confirmation',
        'from': {'id': OWNER, 'is_bot': False}, 'data': body['reply_markup']['inline_keyboard'][0][0]['callback_data'],
        'message': {'message_id': 123, 'chat': {'id': OWNER, 'type': 'private'}}}}
    with pytest.raises(Denied, match='card_not_observed'):
        bridge[0].receive(button)
    assert not rows(store, Approval) and not rows(store, ExternalGrant) and not rows(store, Outbox)


def test_lost_card_delivery_response_does_not_allow_paid_confirmation(bridge, store, profile):
    issue(bridge)
    def lose(method):
        if method == 'sendMessage':
            raise httpx.ReadTimeout('public delivery receipt loss')
    bridge[1].after = lose
    button = click(bridge)
    assert rows(store, TelegramDelivery)[0].state == 'UNCERTAIN'
    with pytest.raises(Denied, match='card_not_observed'):
        bridge[0].receive(button)
    assert not rows(store, Approval) and not rows(store, ExternalGrant)


def test_gate_expiring_before_card_does_not_authorize(bridge, store, profile, monkeypatch):
    config, save, _ = profile
    with store.transaction() as session:
        expires = store.now(session) + timedelta(seconds=30)
    config.first_experiment.evidence['current_price'].expires_at = expires.isoformat()
    save()
    issue(bridge)
    button = click(bridge)
    now = store.now
    monkeypatch.setattr(store, 'now', lambda s: now(s) + timedelta(seconds=31))
    with pytest.raises(Denied, match='preconditions_missing'):
        bridge[0].receive(button)
    assert not rows(store, Approval) and not rows(store, ExternalGrant)


def test_profile_change_between_review_and_grant_commit_rolls_back_authority(bridge, store, profile, monkeypatch):
    issue(bridge)
    button = click(bridge)
    authorize = Gateway.authorize_configured
    def change(*args, **kwargs):
        config, save, _ = profile
        config.budget_evidence += ' changed during approval'
        save()
        return authorize(*args, **kwargs)
    monkeypatch.setattr(Gateway, 'authorize_configured', staticmethod(change))
    with pytest.raises(Denied, match='profile_or_task_changed'):
        bridge[0].receive(button)
    assert store.snapshot()['tasks'][0]['state'] == 'WAITING_APPROVAL'
    assert not rows(store, Approval) and not rows(store, ExternalGrant) and not rows(store, Outbox)


def test_previous_live_experiment_grant_prevents_another_card(bridge, store, profile):
    other = store.create('owner', 'public-other-fixed-experiment', task_payload())
    Gateway.authorize_configured(store, profile[0], 'owner', other['id'], other['version'],
                                 budget_nano_rub=profile[0].tariff.maximum() * 2, final_confirmation=True)
    before = authority(store), ledger(store)
    issue(bridge)
    assert (authority(store), ledger(store)) == before
    assert not any(a.event['kind'] == ISSUED for a in rows(store, Audit))


def test_reply_enqueue_failure_rolls_back_grant_and_recovers_once(bridge, store, profile, monkeypatch):
    issue(bridge)
    button = click(bridge)
    with monkeypatch.context() as patch:
        patch.setattr(bridge[0], 'enqueue', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('public reply loss')))
        with pytest.raises(RuntimeError):
            bridge[0].receive(button)
    assert store.snapshot()['tasks'][0]['state'] == 'WAITING_APPROVAL'
    assert not rows(store, Approval) and not rows(store, ExternalGrant) and not rows(store, Outbox)
    bridge[0].resume_pending()
    bridge[0].resume_pending()
    assert len(rows(store, Approval)) == len(rows(store, ExternalGrant)) == len(rows(store, Outbox)) == 1


def test_lost_local_result_after_commit_is_not_a_second_authorization(bridge, store, profile, monkeypatch):
    issue(bridge)
    button = click(bridge)
    authorize = Gateway.authorize_configured
    def lose(*args, **kwargs):
        authorize(*args, **kwargs)
        raise RuntimeError('public local result loss after commit')
    with monkeypatch.context() as patch:
        patch.setattr(Gateway, 'authorize_configured', staticmethod(lose))
        with pytest.raises(RuntimeError):
            bridge[0].receive(button)
    restarted = TelegramBridge(store, bridge[0].client, OWNER)
    restarted.resume_pending()
    restarted.receive(button)
    assert len(rows(store, Approval)) == len(rows(store, ExternalGrant)) == len(rows(store, Outbox)) == 1
    assert sum(a.event['kind'] == CONSUMED for a in rows(store, Audit)) == 1


def test_slow_final_commit_past_card_expiry_rolls_back_authority(bridge, store, profile, monkeypatch):
    issue(bridge)
    button = click(bridge)
    finish, now = bridge[0].finish, store.now

    def slow(*args, **kwargs):
        result = finish(*args, **kwargs)
        monkeypatch.setattr(store, 'now', lambda s: now(s) + timedelta(seconds=121))
        return result

    monkeypatch.setattr(bridge[0], 'finish', slow)
    with pytest.raises(Denied, match='expired_during_commit'):
        bridge[0].receive(button)
    assert store.snapshot()['tasks'][0]['state'] == 'WAITING_APPROVAL'
    assert not rows(store, Approval) and not rows(store, ExternalGrant) and not rows(store, Outbox)


def test_lost_callback_acknowledgement_never_repeats_financial_authorization(bridge, store, profile):
    issue(bridge)
    button = click(bridge)
    bridge[1].updates = [button]

    def lose(method):
        if method == 'answerCallbackQuery':
            raise httpx.ReadTimeout('public acknowledgement loss')

    bridge[1].after = lose
    for _ in range(2):
        TelegramService(store, bridge[0].client, poll_seconds=0).run(max_cycles=1)
    assert len(rows(store, Approval)) == len(rows(store, ExternalGrant)) == len(rows(store, Outbox)) == 1
    assert sum(method == 'answerCallbackQuery' for method, _ in bridge[1].calls) == 1
    assert not rows(store, ExternalAction)


def test_used_card_cannot_restore_permission_after_stop(bridge, store, profile):
    issue(bridge)
    button = click(bridge)
    bridge[0].receive(button)
    store.halt('owner')
    before = authority(store), ledger(store)
    button['update_id'] += 1
    button['callback_query']['id'] += '-replay'
    bridge[0].receive(button)
    assert (authority(store), ledger(store)) == before
    assert rows(store, Approval)[0].revoked is True


def test_missing_task_or_profile_is_not_an_implicit_prepare_or_authorize(bridge, store):
    issue(bridge)
    assert not store.snapshot()['tasks']
    assert not rows(store, Approval) and not rows(store, ExternalGrant)


@pytest.mark.parametrize('attack', ['extra', 'url', 'label', 'nonce'])
def test_paid_markup_does_not_expand_existing_transport_scope(attack):
    value = keyboard('a' * 32)
    assert allowed_markup(value)
    if attack == 'extra':
        value['resize_keyboard'] = True
    elif attack == 'url':
        value['inline_keyboard'][0][0]['url'] = 'https://example.invalid'
    elif attack == 'label':
        value['inline_keyboard'][0][0]['text'] = 'Free demo'
    else:
        value['inline_keyboard'][0][0]['callback_data'] = 'fx:short'
    assert not allowed_markup(value)
    with pytest.raises(Denied):
        parse_callback('fx:short')
