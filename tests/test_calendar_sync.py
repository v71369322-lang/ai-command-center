from uuid import uuid4

import pytest

from command_center.calendar_drafts import create, decide
from command_center.calendar_sync import (configure_binding, prepare_sync, reconciliation_plan,
                                           record_outcome, sync_state)
from command_center.google_calendar_contract import insert_request
from command_center.store import Denied, digest
from command_center.telegram_calendar import list_reply


def document():
    return {'title': 'Созвон', 'start': '2026-11-03T15:00:00+05:00',
            'end': '2026-11-03T15:30:00+05:00', 'timezone': 'Asia/Almaty',
            'note': '', 'telegram_reminder_minutes': 20}


def ready(store):
    draft = create(store, 'owner', document(), str(uuid4()), digest('source'))
    decide(store, 'owner', draft['id'], 1, str(uuid4()), True)
    binding = {'enabled': True, 'calendar_id': 'commander@example.com',
               'credential_fingerprint': 'a' * 64}
    configure_binding(store, 'owner', binding, 0, str(uuid4()))
    return draft, binding


def response(draft, binding):
    request = insert_request(binding['calendar_id'], draft['id'], draft['document'])
    body = request['body']
    return {'id': 'commander12345', 'etag': '"etag"', 'status': 'confirmed',
            'summary': body['summary'], 'start': body['start'], 'end': body['end'],
            'extendedProperties': body['extendedProperties']}


def test_prepare_is_offline_idempotent_and_contains_no_credential_value(store):
    draft, _ = ready(store)
    operation = str(uuid4())
    first = prepare_sync(store, 'owner', draft['id'], operation)
    assert first['state'] == 'PREPARED'
    assert prepare_sync(store, 'owner', draft['id'], operation) == first
    assert first.keys() == {'state', 'draft_id', 'request_hash', 'document_hash', 'binding_version'}
    with pytest.raises(Denied, match='already_started'):
        prepare_sync(store, 'owner', draft['id'], str(uuid4()))


def test_unknown_outcome_requires_read_before_retry_then_accepts_exact_event(store):
    draft, binding = ready(store)
    state = prepare_sync(store, 'owner', draft['id'], str(uuid4()))
    unknown = record_outcome(store, draft['id'], state['request_hash'], str(uuid4()), 'unknown')
    assert unknown['state'] == 'UNKNOWN'
    plan = reconciliation_plan(store, 'owner', draft['id'])
    assert plan['external_call_performed'] is False
    assert plan['request']['query']['maxResults'] == '2'
    synced = record_outcome(store, draft['id'], state['request_hash'], str(uuid4()),
                            'synced', response(draft, binding))
    assert synced['state'] == 'SYNCED' and synced['event_id'] == 'commander12345'
    with store.transaction() as session:
        assert 'Google синхронизирован' in list_reply(session)


def test_binding_version_and_outcomes_fail_closed(store):
    draft, binding = ready(store)
    with pytest.raises(Denied, match='stale_version'):
        configure_binding(store, 'owner', binding, 0, str(uuid4()))
    state = prepare_sync(store, 'owner', draft['id'], str(uuid4()))
    with pytest.raises(Denied, match='outcome_stale'):
        record_outcome(store, draft['id'], 'b' * 64, str(uuid4()), 'unknown')
    bad = response(draft, binding)
    bad['summary'] = 'Подмена'
    with pytest.raises(Denied, match='response_binding_invalid'):
        record_outcome(store, draft['id'], state['request_hash'], str(uuid4()), 'synced', bad)
    with store.transaction() as session:
        assert sync_state(session, draft['id'])['state'] == 'PREPARED'


def test_unconfirmed_draft_or_disabled_binding_cannot_prepare(store):
    draft = create(store, 'owner', document(), str(uuid4()), digest('source'))
    configure_binding(store, 'owner', {'enabled': False, 'calendar_id': 'commander@example.com',
                      'credential_fingerprint': 'a' * 64}, 0, str(uuid4()))
    with pytest.raises(Denied, match='not_eligible'):
        prepare_sync(store, 'owner', draft['id'], str(uuid4()))
