"""Actual PostgreSQL/audit and HTTP-mock evidence, never a live Telegram call."""
from datetime import timedelta
import json

import pytest
from sqlalchemy import text

from command_center.store import Denied, digest
from command_center.telegram_health import status


def binding(mode='live'):
    return {'mode': mode, 'bot_id': 123456789, 'owner_id': 1234567, 'connection_digest': 'a' * 64}


def event(store, approved, kind='telegram_service_heartbeat', **details):
    with store.transaction() as session:
        store.audit(session, kind, 'telegram_service', profile=digest({
            'owner': approved['owner_id'], 'bot_id': approved['bot_id'], 'mode': approved['mode']}),
            bot_id=approved['bot_id'], connection_digest=approved['connection_digest'], **details)


def test_default_status_and_no_heartbeat_never_claim_connected(store):
    assert status(store, '')['status'] == 'disabled'
    value = status(store, json.dumps(binding()))
    assert value['status'] == 'waiting' and not value['live_connected']


@pytest.mark.parametrize('mode', ['live', 'http_mock'])
def test_only_current_scoped_audited_polling_is_visible(store, mode):
    approved = binding(mode)
    event(store, approved)
    value = status(store, json.dumps(approved))
    assert value['status'] == 'polling' and value['live_connected'] == (mode == 'live')
    assert value['voice_enabled'] is False
    other = {**approved, 'connection_digest': 'b' * 64}
    assert status(store, json.dumps(other))['live_connected'] is False
    assert status(store, json.dumps({**approved, 'owner_id': 9876543}))['status'] == 'waiting'


@pytest.mark.parametrize('kind,wanted', [('telegram_service_stopped', 'stopped'), ('telegram_poll_failed', 'degraded')])
def test_stop_or_poll_failure_overrides_preceding_heartbeat(store, kind, wanted):
    approved = binding()
    event(store, approved)
    event(store, approved, kind)
    value = status(store, json.dumps(approved))
    assert value['status'] == wanted and not value['live_connected']


def test_stale_future_and_other_revision_evidence_are_not_live(store, monkeypatch):
    approved = binding()
    event(store, approved)
    real_now = store.now
    monkeypatch.setattr(store, 'now', lambda s: real_now(s) + timedelta(seconds=61))
    assert status(store, json.dumps(approved))['status'] == 'stale'
    monkeypatch.setattr(store, 'now', lambda s: real_now(s) - timedelta(seconds=10))
    assert not status(store, json.dumps(approved))['live_connected']
    monkeypatch.setattr(store, 'now', real_now)
    with store.transaction() as session:
        store.audit(session, 'telegram_service_stopped', 'telegram_service', revision='b' * 40,
                    profile=digest({'owner': approved['owner_id'], 'bot_id': approved['bot_id'], 'mode': approved['mode']}))
    assert status(store, json.dumps(approved))['live_connected']


def test_audit_corruption_blocks_status(store, admin):
    event(store, binding())
    with admin.engine.begin() as conn:
        conn.execute(text("UPDATE audit SET digest=repeat('f',64) WHERE sequence=(SELECT max(sequence) FROM audit)"))
    with pytest.raises(Denied):
        status(store, json.dumps(binding()))


@pytest.mark.parametrize('bad', ['{}', 'null', '[]', '{"token":"not-accepted"}'])
def test_status_scope_cannot_be_extended(store, bad):
    with pytest.raises(Denied, match='binding_invalid'):
        status(store, bad)


def test_owner_api_uses_only_nonsecret_scope(client, headers, store, monkeypatch):
    approved = binding('http_mock')
    monkeypatch.setenv('F1_TELEGRAM_SCOPE', json.dumps(approved))
    event(store, approved)
    denied = client.get('/api/telegram/status', headers=headers['operator'])
    assert denied.status_code == 409 and denied.json()['detail'] == 'owner_required'
    result = client.get('/api/telegram/status', headers=headers['owner']).json()
    assert result['status'] == 'polling' and not result['live_connected']
    assert 'connection_digest' not in result and 'owner_id' not in result
