"""Durable advisory drafts, public imported responses, actual restricted PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from command_center.coding.integration_config import FileCredentials, IntegrationConfig
from command_center.models import Audit
from command_center.project_inbox import classify
from command_center.request_plan_store import EVENT, identity, read, save
from command_center.request_planning import context
from command_center.store import Denied, Store, digest
from test_request_planning import snapshot as snapshot, response, change_plan, MODEL, LIMITS, state
from test_telegram_readiness import ledger
from test_telegram_task_status import authority


def events(store):
    with store.transaction() as session:
        return list(session.scalars(select(Audit).where(Audit.event['kind'].as_string() == EVENT).order_by(Audit.sequence)))


def persist(store, snapshot, data=None, **kwargs):
    return save(store, 'owner', snapshot, data or response(snapshot), MODEL, **LIMITS, **kwargs)


def test_import_is_durable_unverified_advice_without_task_or_external_clients(snapshot, store, monkeypatch):
    before = authority(store), ledger(store)
    monkeypatch.setattr(httpx, 'Client', lambda *a, **k: pytest.fail('no provider client'))
    monkeypatch.setattr(FileCredentials, 'get', lambda *a: pytest.fail('no credentials'))
    monkeypatch.setattr(IntegrationConfig, 'load', lambda *a: pytest.fail('no live config'))
    data = response(snapshot)
    data['private_extra'] = 'PUBLIC_UNUSED_BODY_MARKER'
    result = persist(store, snapshot, data)
    assert result['stored'] and result['version'] == 1
    assert result['origin'] == 'owner_supplied_unverified'
    assert result['provider_evidence_verified'] is result['execution_authorized'] is result['task_created'] is False
    record = events(store)[0].event
    assert record['proposal_id'] == result['proposal_id']
    assert 'text' not in record['document'] and 'output' not in record['document']
    assert 'PUBLIC_UNUSED_BODY_MARKER' not in str(record)
    assert read(store, 'owner', snapshot.request_id)['state'] == 'CURRENT'
    assert (authority(store), ledger(store)) == before


def test_duplicate_and_restarted_import_have_same_receipt_and_no_second_event(snapshot, store, settings):
    result = persist(store, snapshot)
    before = state(store)
    restarted = Store(settings)
    try:
        assert persist(restarted, snapshot) == result
        assert read(restarted, 'owner', snapshot.request_id)['proposal_id'] == result['proposal_id']
    finally:
        restarted.engine.dispose()
    assert state(store) == before and len(events(store)) == 1


def test_lost_local_response_after_commit_does_not_duplicate_draft(snapshot, store, monkeypatch):
    transaction = store.transaction
    @contextmanager
    def lose_result():
        with transaction() as session:
            yield session
        raise RuntimeError('public result loss after commit')
    with monkeypatch.context() as patch:
        patch.setattr(store, 'transaction', lose_result)
        with pytest.raises(RuntimeError, match='after commit'):
            persist(store, snapshot)
    assert persist(store, snapshot)['version'] == 1 and len(events(store)) == 1


def test_composition_failure_rolls_back_storage_and_recovers_once(snapshot, store):
    before = state(store)
    def fail(session, receipt):
        assert receipt['stored']
        raise RuntimeError('public acknowledgement enqueue failure')
    with pytest.raises(RuntimeError):
        persist(store, snapshot, _scope_installer=fail)
    assert state(store) == before
    assert persist(store, snapshot)['version'] == 1


@pytest.mark.parametrize('same', [True, False])
def test_concurrent_imports_have_stable_deduplication_and_versions(snapshot, store, same):
    data = response(snapshot)
    other = deepcopy(data)
    if not same:
        other['id'] += '_second'
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda value: persist(store, snapshot, value), [data, other]))
    assert sorted(r['version'] for r in receipts) == ([1, 1] if same else [1, 2])
    assert len(events(store)) == (1 if same else 2)


def test_same_response_identity_with_different_content_is_a_conflict(snapshot, store):
    persist(store, snapshot)
    other = response(snapshot)
    change_plan(other, lambda p: p.update(summary='Different unverified imported content'))
    with pytest.raises(Denied, match='idempotency_conflict'):
        persist(store, snapshot, other)
    assert len(events(store)) == 1


def test_explicit_version_reads_do_not_silently_switch_to_new_draft(snapshot, store):
    first = persist(store, snapshot)
    other = response(snapshot)
    other['id'] += '_second'
    change_plan(other, lambda p: p.update(summary='Second draft'))
    second = persist(store, snapshot, other)
    assert read(store, 'owner', snapshot.request_id)['proposal_id'] == second['proposal_id']
    assert read(store, 'owner', snapshot.request_id, version=1)['proposal_id'] == first['proposal_id']
    assert read(store, 'owner', snapshot.request_id, version=3)['state'] == 'MISSING_VERSION'


@pytest.mark.parametrize('change', ['assignment', 'source', 'stop'])
def test_changed_context_hides_old_plan_and_cannot_reimport_stale_response(snapshot, store, monkeypatch, change):
    persist(store, snapshot)
    if change == 'assignment':
        classify(store, 'owner', snapshot.request_id, 'capital-lab', 1, str(uuid4()))
    elif change == 'source':
        monkeypatch.setattr(store, 'settings', replace(store.settings, source_revision='a' * 40))
    else:
        store.halt('owner')
    before = state(store)
    value = read(store, 'owner', snapshot.request_id)
    assert value['state'] == 'STALE' and value['proposal'] is None
    with pytest.raises(Denied, match='planning_context_changed'):
        persist(store, snapshot)
    assert state(store) == before
    current = context(store, 'owner', snapshot.request_id)
    assert persist(store, current)['version'] == 2
    assert read(store, 'owner', snapshot.request_id, version=1)['state'] == 'STALE'


@pytest.mark.parametrize('role', ['operator', 'agent', None])
def test_only_owner_can_store_or_read_drafts(snapshot, store, role):
    before = state(store)
    with pytest.raises(Denied, match='owner_required'):
        save(store, role, snapshot, response(snapshot), MODEL, **LIMITS)
    with pytest.raises(Denied, match='owner_required'):
        read(store, role, snapshot.request_id)
    assert state(store) == before


@pytest.mark.parametrize('version', [True, 0, -1, 101, '1'])
def test_invalid_version_cannot_select_a_different_proposal(snapshot, store, version):
    with pytest.raises(Denied, match='draft_version_invalid'):
        read(store, 'owner', snapshot.request_id, version=version)


def test_global_capacity_allows_existing_idempotent_result_but_no_more_records(snapshot, store, monkeypatch):
    monkeypatch.setattr('command_center.request_plan_store.MAX_PROPOSALS', 2)
    first = persist(store, snapshot)
    other = response(snapshot)
    other['id'] += '_second'
    assert persist(store, snapshot, other)['version'] == 2
    assert persist(store, snapshot) == first
    other['id'] += '_third'
    with pytest.raises(Denied, match='draft_capacity'):
        persist(store, snapshot, other)
    assert len(events(store)) == 2


def test_storage_size_limit_rejects_without_any_record(snapshot, store, monkeypatch):
    monkeypatch.setattr('command_center.request_plan_store.MAX_DOCUMENT_BYTES', 64)
    with pytest.raises(Denied, match='draft_size'):
        persist(store, snapshot)
    assert events(store) == []


@pytest.mark.parametrize('attack', ['flag', 'zero_flag', 'schema_bool', 'version', 'document_digest', 'actor',
                                  'request_id', 'proposal_id', 'source', 'usage', 'plan_context', 'extra'])
def test_semantically_invalid_chained_record_is_never_presented_as_a_plan(snapshot, store, attack):
    persist(store, snapshot)
    source = events(store)[0].event
    document = deepcopy(source['document'])
    document['response_id'] += '_forged'
    if attack == 'flag':
        document['provider_evidence_verified'] = True
    elif attack == 'zero_flag':
        document['execution_authorized'] = 0
    elif attack == 'schema_bool':
        document['schema_version'] = True
    elif attack == 'usage':
        document['usage']['total_tokens'] += 1
    elif attack == 'plan_context':
        document['proposal']['context_digest'] = 'a' * 64
    elif attack == 'extra':
        document['permissions'] = ['execute']
    elif attack == 'source':
        document['revision'] = 'a' * 40
    kwargs = {'proposal_id': identity(document), 'request_id': snapshot.request_id, 'version': 2,
              'document': document, 'document_digest': digest(document)}
    actor = 'owner'
    if attack == 'version':
        kwargs['version'] = 1
    elif attack == 'document_digest':
        kwargs['document_digest'] = '0' * 64
    elif attack == 'actor':
        actor = 'agent'
    elif attack == 'request_id':
        kwargs['request_id'] += '1'
    elif attack == 'proposal_id':
        kwargs['proposal_id'] = '0' * 64
    with store.transaction() as session:
        store.audit(session, EVENT, actor, **kwargs)
    with pytest.raises(Denied):
        read(store, 'owner', snapshot.request_id)


def test_stored_text_is_rechecked_after_current_credential_rotation(snapshot, store):
    persist(store, snapshot)
    summary = read(store, 'owner', snapshot.request_id)['proposal']['summary']
    rotated = Store(replace(store.settings, identities={**store.settings.identities, 'owner': summary}))
    try:
        with pytest.raises(Denied, match='sensitive_content'):
            read(rotated, 'owner', snapshot.request_id)
    finally:
        rotated.engine.dispose()


@pytest.mark.parametrize('value', ['Public text\x00invalid', 'Public text\ud800invalid'])
def test_json_text_unrepresentable_in_postgresql_is_rejected_before_writing(snapshot, store, value):
    data = response(snapshot)
    change_plan(data, lambda p: p.update(summary=value))
    before = state(store)
    with pytest.raises(Denied):
        persist(store, snapshot, data)
    assert state(store) == before and events(store) == []
