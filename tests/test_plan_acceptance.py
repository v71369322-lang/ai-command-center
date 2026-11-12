"""Content acceptance uses actual PG/audit, never an executor or provider."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, text

from command_center.models import Audit
from command_center.plan_acceptance import EVENT, FLAGS, accept, preview, read
from command_center.project_inbox import classify
from command_center.project_setup import patch, save as setup_save
from command_center.request_planning import context
from command_center.store import Denied, Store, ZERO, digest
from test_project_inbox import capture
from test_project_setup import full
from test_request_plan_store import persist
from test_request_planning import response, state
from test_telegram_task_status import authority
from test_telegram_readiness import ledger
from test_owner_password import password_config as password_config, login


def ready(store, *, questions=None):
    rid = capture(store, value='Public Command Center improvement')
    classify(store, 'owner', rid, 'command-center', 0, str(uuid4()))
    setup_save(store, 'owner', 'command-center', 0,
               {**full(), 'deployment_target': 'command-center-staging'}, str(uuid4()))
    snapshot = context(store, 'owner', rid)
    persist(store, snapshot, response(snapshot, questions=questions))
    return rid


def body(store, rid):
    view = preview(store, 'owner', rid)
    return {'request_id': rid, 'expected_snapshot_digest': view['snapshot_digest']}


def receipts(store):
    with store.transaction() as tx:
        return list(tx.scalars(select(Audit).where(Audit.event['kind'].as_string() == EVENT)))


def test_preview_accept_read_and_retry_do_not_create_authority(store, client, headers, monkeypatch):
    rid = ready(store)
    before = state(store)
    monkeypatch.setattr(httpx, 'Client', lambda *a, **k: pytest.fail('no provider client'))
    view = preview(store, 'owner', rid)
    assert view['proposal']['steps'] and view['reference']['plan_version'] == 1
    assert view['reference']['origin'] == 'owner_supplied_unverified'
    assert read(store, 'owner', rid)['state'] == 'MISSING'
    assert state(store) == before
    api_view = client.get('/api/project-inbox/plan/acceptance-preview',
                          params={'request_id': rid}, headers=headers['owner'])
    assert api_view.status_code == 200 and api_view.json() == view
    request = {'request_id': rid, 'expected_snapshot_digest': view['snapshot_digest']}
    saved = client.post('/api/project-inbox/plan/acceptance', json=request, headers=headers['owner'])
    assert saved.status_code == 200 and saved.headers['cache-control'] == 'no-store'
    receipt = saved.json()
    assert {k: receipt[k] for k in FLAGS} == FLAGS
    assert 'proposal' not in receipt and 'text' not in receipt
    assert accept(store, 'owner', request) == receipt and len(receipts(store)) == 1
    assert read(store, 'owner', rid)['state'] == 'CURRENT'
    assert (authority(store), ledger(store)) == before[:2]


def test_manual_origin_is_preserved_and_acceptance_works_during_halt(store):
    from command_center.manual_plan import save
    from test_manual_plan import request
    rid = ready(store)
    store.halt('owner')
    save(store, 'owner', request(store, rid), str(uuid4()))
    receipt = accept(store, 'owner', body(store, rid))
    assert receipt['reference']['origin'] == 'owner_authored'
    assert read(store, 'owner', rid)['state'] == 'CURRENT'
    assert store.snapshot()['halted'] and receipt['execution_authorized'] is False


def test_concurrent_acceptance_is_one_append_only_receipt(store):
    rid = ready(store)
    request = body(store, rid)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: accept(store, 'owner', request), range(2)))
    assert results[0] == results[1] and len(receipts(store)) == 1


@pytest.mark.parametrize('change', ['setup', 'plan', 'halt', 'source', 'assignment'])
def test_preview_pins_are_rechecked_and_old_acceptance_becomes_stale(store, change):
    rid = ready(store)
    request = body(store, rid)
    accept(store, 'owner', request)
    reader = store
    if change == 'setup':
        patch(store, 'owner', 'command-center', 1, 'acceptance', ['Changed public criterion'], str(uuid4()))
    elif change == 'plan':
        snapshot = context(store, 'owner', rid)
        data = response(snapshot)
        data['id'] = 'resp_second_public_fixture'
        persist(store, snapshot, data)
    elif change == 'halt':
        store.halt('owner')
    elif change == 'assignment':
        classify(store, 'owner', rid, 'command-center', 1, str(uuid4()))
    else:
        reader = Store(replace(store.settings, source_revision='b' * 40))
    try:
        assert read(reader, 'owner', rid)['state'] == 'STALE'
        with pytest.raises(Denied):
            accept(reader, 'owner', request)
        assert len(receipts(store)) == 1
    finally:
        if reader is not store:
            reader.engine.dispose()


@pytest.mark.parametrize('reason', ['questions', 'incomplete_setup'])
def test_questions_or_incomplete_setup_cannot_be_accepted(store, reason):
    rid = ready(store, questions=['Which public field?'] if reason == 'questions' else None)
    if reason == 'incomplete_setup':
        patch(store, 'owner', 'command-center', 1, 'verification_kind', 'not_selected', str(uuid4()))
    with pytest.raises(Denied, match='not_ready'):
        preview(store, 'owner', rid)
    assert receipts(store) == []


def test_changed_preview_digest_does_not_append(store):
    rid = ready(store)
    request = {**body(store, rid), 'expected_snapshot_digest': 'f' * 64}
    before = state(store)
    with pytest.raises(Denied, match='snapshot_changed'):
        accept(store, 'owner', request)
    assert state(store) == before


@pytest.mark.parametrize('role', ['operator', 'agent'])
def test_nonowners_cannot_preview_accept_or_read(store, client, headers, role):
    rid = ready(store)
    request = body(store, rid)
    for method, path in [('get', 'acceptance-preview'), ('get', 'acceptance'), ('post', 'acceptance')]:
        response = (client.post('/api/project-inbox/plan/'+path, json=request, headers=headers[role])
                    if method == 'post' else client.get('/api/project-inbox/plan/'+path,
                                                       params={'request_id': rid}, headers=headers[role]))
        assert response.status_code == 409
    assert receipts(store) == []


def test_other_project_is_context_not_an_access_grant(store):
    rid = ready(store)
    classify(store, 'owner', rid, 'lnauto', 1, str(uuid4()))
    with pytest.raises(Denied, match='command_center_only'):
        preview(store, 'owner', rid)


def test_transaction_failure_rolls_back_the_new_receipt(store, monkeypatch):
    import command_center.plan_acceptance as module
    rid = ready(store)
    request = body(store, rid)
    original = module._history
    def fail_after_append(*args):
        result = original(*args)
        if result:
            raise RuntimeError('public fixture transaction failed')
        return result
    monkeypatch.setattr(module, '_history', fail_after_append)
    with pytest.raises(RuntimeError):
        accept(store, 'owner', request)
    assert receipts(store) == []


def test_audit_corruption_fails_closed(store, admin):
    rid = ready(store)
    request = body(store, rid)
    with admin.transaction() as tx:
        tx.execute(text("UPDATE audit SET digest=repeat('f',64) WHERE sequence=(SELECT min(sequence) FROM audit)"))
    with pytest.raises(Denied, match='audit_integrity_failure'):
        accept(store, 'owner', request)


def test_password_owner_session_still_requires_csrf(store, password_config):
    from fastapi.testclient import TestClient
    from command_center.api import create_app
    rid = ready(store)
    request = body(store, rid)
    with TestClient(create_app(password_config), base_url='https://testserver') as client:
        assert login(client).status_code == 200
        csrf = client.get('/api/auth/csrf').json()['csrf_token']
        assert client.post('/api/project-inbox/plan/acceptance', json=request).status_code == 403
        assert client.post('/api/project-inbox/plan/acceptance', json=request,
                           headers={'X-CSRF-Token': csrf}).status_code == 200


@pytest.mark.parametrize('attack', ['flags', 'origin', 'document', 'version', 'revision'])
def test_semantic_tamper_is_rejected_even_after_rehashing_the_chain(store, admin, attack):
    rid = ready(store)
    accept(store, 'owner', body(store, rid))
    with admin.transaction() as tx:
        rows = list(tx.scalars(select(Audit).order_by(Audit.sequence)))
        for row in rows:
            if row.event['kind'] == EVENT:
                event = deepcopy(row.event)
                if attack == 'flags':
                    event['flags']['execution_authorized'] = True
                elif attack == 'origin':
                    event['reference']['origin'] = 'owner_authored'
                elif attack == 'document':
                    event['reference']['plan_document_digest'] = 'f' * 64
                elif attack == 'version':
                    event['reference']['plan_version'] = True
                else:
                    event['reference']['source_revision'] = 'b' * 40
                event['snapshot_digest'] = digest(event['reference'])
                row.event = event
        previous = ZERO
        for row in rows:
            row.previous = previous
            row.digest = digest({'previous': previous, 'event': row.event})
            previous = row.digest
    with pytest.raises(Denied, match='plan_acceptance_integrity'):
        read(store, 'owner', rid)


def test_duplicate_receipts_are_not_a_second_owner_acceptance(store):
    rid = ready(store)
    saved = accept(store, 'owner', body(store, rid))
    with store.transaction() as tx:
        store.audit(tx, EVENT, 'owner', reference=saved['reference'],
                    snapshot_digest=saved['snapshot_digest'], flags=FLAGS)
    with pytest.raises(Denied, match='plan_acceptance_integrity'):
        read(store, 'owner', rid)


def test_strict_api_body_cannot_inject_authority_or_echo_untrusted_fields(store, client, headers):
    rid = ready(store)
    request = {**body(store, rid), 'execution_authorized': 'UNTRUSTED_INPUT_MARKER'}
    result = client.post('/api/project-inbox/plan/acceptance', json=request, headers=headers['owner'])
    assert result.status_code == 422 and result.json() == {'detail': 'invalid_request'}
    assert receipts(store) == []


def test_restart_readback_and_capacity_do_not_duplicate_or_overwrite(store, settings, monkeypatch):
    import command_center.plan_acceptance as module
    rid = ready(store)
    request = body(store, rid)
    saved = accept(store, 'owner', request)
    restarted = Store(settings)
    try:
        assert read(restarted, 'owner', rid)['receipt'] == saved
        assert accept(restarted, 'owner', request) == saved
    finally:
        restarted.engine.dispose()
    monkeypatch.setattr(module, 'MAX_ACCEPTANCES', 1)
    assert accept(store, 'owner', request) == saved
    snapshot = context(store, 'owner', rid)
    data = response(snapshot)
    data['id'] = 'resp_next_public_fixture'
    persist(store, snapshot, data)
    with pytest.raises(Denied, match='plan_acceptance_capacity'):
        accept(store, 'owner', body(store, rid))
    assert len(receipts(store)) == 1
