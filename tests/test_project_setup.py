"""Real PG draft lifecycle; declarations cannot enable project execution."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import select

from command_center.models import Audit
from command_center.project_setup import Draft, EVENT, binding, catalog, patch, preview, read, restore, save
from command_center.store import Denied, Store
from test_owner_password import password_config as password_config, login
from test_telegram_task_status import authority


def full():
    return {'repository_revision': 'a' * 40, 'verification_kind': 'python_node',
            'delivery_kind': 'pipeline_review', 'deployment_target': 'lnauto-staging',
            'acceptance': ['Фильтр по дате проходит согласованные тесты.']}


def body(version=0, draft=None, operation=None):
    return {'expected_version': version, 'draft': full() if draft is None else draft,
            'operation_id': operation or str(uuid4())}


def test_full_draft_preview_save_history_restore_and_initial_reset_without_authority(client, store, headers):
    store.halt('owner')
    before = authority(store)
    path = '/api/projects/lnauto/setup'
    initial = client.get(path, headers=headers['owner']).json()
    assert initial['version'] == 0 and initial['review']['filled'] == 0
    assert initial['review']['blocking_checks'] and initial['review']['execution_ready'] is False
    p = client.post(path + '/preview', headers=headers['owner'], json={'expected_version': 0, 'draft': full()}).json()
    assert p['stored'] is False and len(p['changed_fields']) == 5
    assert p['review']['ready_for_operator_review'] is True
    assert read(store, 'owner', 'lnauto')['version'] == 0
    saved = client.post(path, headers=headers['owner'], json=body()).json()
    assert saved['version'] == 1 and saved['draft_digest'] == p['proposed_digest']
    assert saved['execution_started'] is False
    current = read(store, 'owner', 'lnauto')
    assert current['draft'] == full() and current['actions_enabled'] == []
    patch(store, 'owner', 'lnauto', 1, 'acceptance', ['Public revised condition'], str(uuid4()))
    historical = client.get(path + '?version=1', headers=headers['owner']).json()
    assert historical['state'] == 'HISTORICAL' and historical['latest_version'] == 2
    assert historical['draft'] == full()
    request = {'expected_version': 2, 'target_version': 1, 'target_digest': historical['draft_digest'],
               'operation_id': str(uuid4())}
    assert client.post(path + '/restore', headers=headers['owner'], json=request).json()['version'] == 3
    assert read(store, 'owner', 'lnauto')['draft'] == full()
    assert client.post(path + '/restore', headers=headers['owner'], json=request).json()['version'] == 3
    assert restore(store, 'owner', 'lnauto', 3, 0, initial['draft_digest'], str(uuid4()))['version'] == 4
    assert read(store, 'owner', 'lnauto')['draft'] == Draft().model_dump()
    assert [r['version'] for r in read(store, 'owner', 'lnauto')['history']] == [4, 3, 2, 1, 0]
    assert authority(store) == before


@pytest.mark.parametrize('role,status', [('anonymous', 401), ('operator', 409), ('agent', 409)])
def test_all_setup_routes_require_owner(client, headers, role, status):
    supplied = headers.get(role, {})
    assert client.get('/api/project-setup', headers=supplied).status_code == status
    assert client.get('/api/projects/lnauto/setup', headers=supplied).status_code == status
    assert client.post('/api/projects/lnauto/setup', headers=supplied, json=body()).status_code == status
    assert client.post('/api/projects/lnauto/setup/preview', headers=supplied,
                       json={'expected_version': 0, 'draft': full()}).status_code == status
    assert client.post('/api/projects/lnauto/setup/restore', headers=supplied, json={
        'expected_version': 0, 'target_version': 0, 'target_digest': 'a' * 64,
        'operation_id': str(uuid4())}).status_code == status


@pytest.mark.parametrize('field,value', [('repository_revision', True), ('repository_revision', 'main'),
    ('verification_kind', 'arbitrary-shell'), ('delivery_kind', 'automatic'),
    ('deployment_target', 'root@host'), ('deployment_target', 'https://example.invalid'),
    ('acceptance', ['']), ('acceptance', [' x']), ('acceptance', ['x\n/stop']),
    ('acceptance', ['x'] * 9), ('acceptance', ['я' * 201]), ('execution_connected', True),
    ('credential_file', '/run/secrets/key'), ('repository', 'other/production')])
def test_invalid_or_authority_expanding_drafts_are_not_saved_or_echoed(client, headers, store, field, value):
    draft = {**full(), field: value}
    result = client.post('/api/projects/lnauto/setup', headers=headers['owner'], json=body(draft=draft))
    assert result.status_code == 422 and result.json() == {'detail': 'invalid_request'}
    assert read(store, 'owner', 'lnauto')['version'] == 0


def test_preview_and_save_reject_currently_known_sensitive_content_without_echo(store, client, headers):
    value = 'PUBLIC_STRING_THAT_BECOMES_SYNTHETIC_KNOWN_SECRET'
    changed = Store(replace(store.settings, identities={**store.settings.identities, 'agent': value}))
    try:
        with pytest.raises(Denied, match='sensitive_content'):
            save(changed, 'owner', 'lnauto', 0, {**full(), 'acceptance': [value]}, str(uuid4()))
        assert read(store, 'owner', 'lnauto')['version'] == 0
    finally:
        changed.engine.dispose()
    result = client.post('/api/projects/lnauto/setup', headers=headers['owner'], json=body(
        draft={**full(), 'acceptance': ['-----BEGIN PRIVATE KEY----- public fixture']}))
    assert result.status_code == 409 and 'BEGIN' not in result.text


def test_parallel_saves_idempotency_cross_project_reuse_and_stale_preview(store):
    operation = str(uuid4())
    first = save(store, 'owner', 'lnauto', 0, full(), operation)
    assert save(store, 'owner', 'lnauto', 0, full(), operation) == first
    for pid, draft in [('capital-lab', full()), ('lnauto', {**full(), 'acceptance': ['changed']})]:
        with pytest.raises(Denied, match='idempotency_conflict'):
            save(store, 'owner', pid, 0, draft, operation)
    def change(name):
        try:
            return patch(store, 'owner', 'lnauto', 1, 'deployment_target', name, str(uuid4()))['version']
        except Denied as error:
            return str(error)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(change, ['first-staging', 'second-staging']))
    assert outcomes.count(2) == 1 and outcomes.count('project_setup_stale_version') == 1
    with pytest.raises(Denied, match='stale_version'):
        preview(store, 'owner', 'lnauto', 1, full())
    with pytest.raises(Denied, match='version_missing'):
        read(store, 'owner', 'lnauto', selected=99)
    with pytest.raises(Denied, match='restore_target_changed'):
        restore(store, 'owner', 'lnauto', 2, 1, 'f' * 64, str(uuid4()))


def test_catalog_isolated_projects_and_restarted_store_keep_metadata(store, settings):
    save(store, 'owner', 'lnauto', 0, full(), str(uuid4()))
    restarted = Store(settings)
    try:
        result = catalog(restarted, 'owner')
        assert {p['project_id']: p['version'] for p in result['projects']} == {
            'command-center': 0, 'vanilla-sugar': 0, 'lnauto': 1, 'capital-lab': 0}
        assert read(restarted, 'owner', 'lnauto')['draft'] == full()
        assert result['execution_connected'] is False and result['actions_enabled'] == []
    finally:
        restarted.engine.dispose()


def test_atomic_failure_rechecks_history_and_capacity_without_hiding_old_revisions(store, monkeypatch):
    from command_center import project_setup
    with monkeypatch.context() as patcher:
        patcher.setattr(store, 'audit', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('fixture failure')))
        with pytest.raises(RuntimeError):
            save(store, 'owner', 'lnauto', 0, full(), str(uuid4()))
    assert read(store, 'owner', 'lnauto')['version'] == 0
    with monkeypatch.context() as patcher:
        patcher.setattr(project_setup, 'MAX_EVENTS', 1)
        operation = str(uuid4())
        first = save(store, 'owner', 'lnauto', 0, full(), operation)
        assert save(store, 'owner', 'lnauto', 0, full(), operation) == first
        with pytest.raises(Denied, match='history_capacity'):
            save(store, 'owner', 'capital-lab', 0, full(), str(uuid4()))
        assert read(store, 'owner', 'lnauto')['version'] == 1


@pytest.mark.parametrize('tamper', ['draft_hash', 'version', 'action', 'actor', 'schema', 'extra', 'time', 'revision'])
def test_intact_audit_with_invalid_setup_document_still_blocks_reads(store, tamper):
    save(store, 'owner', 'lnauto', 0, full(), str(uuid4()))
    with store.transaction() as session:
        event = dict(session.scalar(select(Audit).where(Audit.event['kind'].as_string() == EVENT)).event)
        for key in ('kind', 'actor', 'task_id', 'time', 'revision'):
            event.pop(key)
        event['version'], event['operation_id'] = 2, str(uuid4())
        event['input'] = {'action': 'save', 'project_id': 'lnauto', 'expected_version': 1, 'draft': full()}
        from command_center.store import digest
        event['input_hash'] = digest(event['input'])
        if tamper == 'draft_hash':
            event['draft_digest'] = 'f' * 64
        elif tamper == 'version':
            event['version'] = True
        elif tamper == 'action':
            event['input']['action'] = 'deploy'
            event['input_hash'] = digest(event['input'])
        elif tamper == 'schema':
            event['schema'] = True
        elif tamper == 'extra':
            event['execution_connected'] = True
        elif tamper == 'time':
            event['time'] = '2026-10-30T12:00:00'
        elif tamper == 'revision':
            event['revision'] = 'z' * 40
        store.audit(session, EVENT, 'agent' if tamper == 'actor' else 'owner', **event)
    with pytest.raises(Denied, match='history_invalid'):
        read(store, 'owner', 'lnauto')


def test_patch_clear_and_restore_are_only_versioned_draft_changes(store):
    first = patch(store, 'owner', 'lnauto', 0, 'acceptance', ['Public condition'], str(uuid4()))
    assert first['version'] == 1
    cleared = patch(store, 'owner', 'lnauto', 1, 'acceptance', None, str(uuid4()), clear=True)
    assert cleared['version'] == 2
    assert read(store, 'owner', 'lnauto')['draft']['acceptance'] == []
    with pytest.raises(Denied, match='field_invalid'):
        patch(store, 'owner', 'lnauto', 2, 'execution_connected', True, str(uuid4()))
    assert binding('lnauto', full()) != binding('capital-lab', full())


def test_password_sessions_keep_csrf_origin_and_logout_guards(store, password_config):
    from fastapi.testclient import TestClient
    from command_center.api import create_app
    with TestClient(create_app(password_config), base_url='https://testserver') as client:
        assert login(client).status_code == 200
        path = '/api/projects/lnauto/setup'
        assert client.post(path, json=body()).status_code == 403
        csrf = client.get('/api/auth/csrf').json()['csrf_token']
        assert client.post(path, json=body(), headers={
            'X-CSRF-Token': csrf, 'Origin': 'https://attacker.invalid'}).status_code == 403
        assert client.post(path, json=body(), headers={'X-CSRF-Token': csrf}).status_code == 200
        csrf = client.get('/api/auth/csrf').json()['csrf_token']
        assert client.post('/api/auth/logout', json={}, headers={'X-CSRF-Token': csrf}).status_code == 200
        assert client.get(path).status_code == 401


def test_generic_timelines_do_not_expose_draft_values_even_to_operator(client, store, headers):
    text = 'Public-private-criterion-for-explicit-setup-view-only'
    save(store, 'owner', 'lnauto', 0, {**full(), 'acceptance': [text]}, str(uuid4()))
    for role in ('owner', 'operator'):
        response = client.get('/api/state', headers=headers[role])
        assert response.status_code == 200 and text not in response.text and 'lnauto-staging' not in response.text
        event = next(r['event'] for r in response.json()['events'] if r['event']['kind'] == EVENT)
        assert event['details_redacted'] is True and 'draft' not in event and 'input' not in event
        if role == 'operator':
            assert 'project_id' not in event
    assert client.get('/api/projects/lnauto/setup', headers=headers['owner']).json()['draft']['acceptance'] == [text]
    with store.transaction() as session:
        store.check_audit(session)


@pytest.mark.parametrize('field,value', [('expected_version', True), ('expected_version', -1),
    ('operation_id', 'not-a-uuid'), ('execution_authorized', True)])
def test_invalid_save_envelope_does_not_become_a_write(client, store, headers, field, value):
    request = {**body(), field: value}
    result = client.post('/api/projects/lnauto/setup', headers=headers['owner'], json=request)
    assert result.status_code == 422 and result.json() == {'detail': 'invalid_request'}
    assert read(store, 'owner', 'lnauto')['version'] == 0
