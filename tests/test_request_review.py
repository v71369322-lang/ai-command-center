"""One coherent read-only snapshot, backed by real restricted PostgreSQL."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from command_center.api import create_app
from command_center.coding.integration_config import FileCredentials, IntegrationConfig
from command_center.models import TelegramInbox
from command_center.project_inbox import classify
from command_center.project_setup import EVENT, save as save_setup, patch
from command_center.request_planning import context
from command_center.request_review import read, CHECKS
from command_center.store import Denied, Store, canonical, digest
from test_project_inbox import capture
from test_project_setup import full
from test_request_plan_store import persist
from test_request_planning import response, state
from test_owner_password import password_config as password_config, login


def selected(store, *, value='Public review request'):
    rid = capture(store, value=value)
    classify(store, 'owner', rid, 'lnauto', 0, str(uuid4()))
    return rid


def configured(store):
    rid = selected(store)
    save_setup(store, 'owner', 'lnauto', 0, full(), str(uuid4()))
    return rid


def no_authority(view):
    assert view['scope'] == 'REQUEST_REVIEW_ONLY' and view['actions_enabled'] == []
    assert all(view[k] is False for k in ('execution_ready', 'execution_authorized', 'external_checks_performed', 'task_created', 'provider_called'))
    assert view['plan']['provider_evidence_verified'] is view['plan']['setup_binding_verified'] is False
    assert [v['id'] for v in view['checks']] == [k for k, _ in CHECKS]
    assert {'plan_setup_binding', 'repository', 'verification', 'delivery', 'authorization'} <= set(view['blocking_checks'])
    raw = {k: v for k, v in view.items() if k not in {'snapshot_digest', 'observed_at'}}
    assert digest(raw) == view['snapshot_digest']


def test_request_assignment_setup_plan_and_blockers_form_one_checked_snapshot(store, client, headers):
    rid = capture(store)
    assert read(store, 'owner', rid)['next_step'] == 'select_project'
    classify(store, 'owner', rid, 'lnauto', 0, str(uuid4()))
    assert read(store, 'owner', rid)['next_step'] == 'complete_setup'
    save_setup(store, 'owner', 'lnauto', 0, full(), str(uuid4()))
    assert read(store, 'owner', rid)['next_step'] == 'prepare_plan'
    persist(store, context(store, 'owner', rid))
    before = state(store)
    first = read(store, 'owner', rid)
    second = client.get('/api/project-inbox/review', params={'request_id': rid}, headers=headers['owner'])
    assert second.status_code == 200 and second.headers['cache-control'] == 'no-store'
    assert second.json()['snapshot_digest'] == first['snapshot_digest']
    assert first['next_step'] == 'verify_scope' and first['project']['draft'] == full()
    assert first['project']['setup_version'] == first['plan']['version'] == 1
    assert first['plan']['proposal']['summary'] == 'Предложение изменения формы'
    no_authority(first)
    assert state(store) == before


def test_setup_change_changes_snapshot_without_claiming_the_old_plan_covers_it(store):
    rid = configured(store)
    persist(store, context(store, 'owner', rid))
    first = read(store, 'owner', rid)
    patch(store, 'owner', 'lnauto', 1, 'acceptance', ['Changed public criterion'], str(uuid4()))
    current = read(store, 'owner', rid)
    assert current['snapshot_digest'] != first['snapshot_digest']
    assert current['plan']['state'] == 'CURRENT' and current['project']['setup_version'] == 2
    assert current['project']['draft']['acceptance'] == ['Changed public criterion']
    no_authority(current)


def test_request_plan_and_setup_are_read_under_one_admission_lock(store, admin, monkeypatch):
    import command_center.request_review as module
    rid = configured(store)
    ready, release = Event(), Event()
    original = module.setup_read
    def held(*args, **kwargs):
        value = original(*args, **kwargs)
        ready.set()
        if not release.wait(2):
            raise RuntimeError('review_test_release_timeout')
        return value
    monkeypatch.setattr(module, 'setup_read', held)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(read, store, 'owner', rid)
        try:
            assert ready.wait(2)
            with pytest.raises(OperationalError) as error:
                with admin.engine.begin() as connection:
                    connection.execute(text('SELECT id FROM control WHERE id=1 FOR UPDATE NOWAIT'))
            assert error.value.orig.sqlstate == '55P03'
        finally:
            release.set()
        assert pending.result()['project']['setup_version'] == 1


@pytest.mark.parametrize('change', ['assignment', 'halt', 'source'])
def test_stale_plans_are_not_presented_as_current_or_returned_as_content(store, change):
    rid = configured(store)
    persist(store, context(store, 'owner', rid))
    reader = store
    if change == 'assignment':
        classify(store, 'owner', rid, 'capital-lab', 1, str(uuid4()))
    elif change == 'halt':
        store.halt('owner')
    else:
        reader = Store(replace(store.settings, source_revision='b' * 40))
    try:
        value = read(reader, 'owner', rid)
        assert value['plan']['state'] == 'STALE' and value['plan']['proposal'] is None
        assert value['next_step'] == ('complete_setup' if change == 'assignment' else 'refresh_plan')
        if change == 'halt':
            assert value['checks'][-1]['state'] == 'HALTED'
        no_authority(value)
    finally:
        if reader is not store:
            reader.engine.dispose()


def test_questions_are_visible_but_do_not_authorize_work(store):
    rid = configured(store)
    snapshot = context(store, 'owner', rid)
    persist(store, snapshot, response(snapshot, questions=['Which public field is required?']))
    value = read(store, 'owner', rid)
    assert value['plan']['state'] == 'NEEDS_CLARIFICATION' and value['next_step'] == 'answer_questions'
    assert value['plan']['proposal']['questions'] == ['Which public field is required?']
    no_authority(value)


def test_reader_never_loads_provider_configuration_or_credentials(store, monkeypatch):
    rid = configured(store)
    before = state(store)
    monkeypatch.setattr(httpx, 'Client', lambda *a, **k: pytest.fail('no external HTTP'))
    monkeypatch.setattr(FileCredentials, 'get', lambda *a: pytest.fail('no credentials'))
    monkeypatch.setattr(IntegrationConfig, 'load', lambda *a: pytest.fail('no integration config'))
    no_authority(read(store, 'owner', rid))
    assert state(store) == before


@pytest.mark.parametrize('role,status', [('anonymous', 401), ('operator', 409), ('agent', 409)])
def test_review_requires_owner(client, store, headers, role, status):
    rid = selected(store)
    result = client.get('/api/project-inbox/review', params={'request_id': rid}, headers=headers.get(role, {}))
    assert result.status_code == status and rid not in result.text


@pytest.mark.parametrize('rid', ['other-profile:1', 'a'*64+':01', 'a'*64+':-1', 'a'*64+':9007199254740992', 'a'*64+':1/stop'])
def test_invalid_references_fail_without_capture_or_echo(client, store, headers, rid):
    before = state(store)
    result = client.get('/api/project-inbox/review', params={'request_id': rid}, headers=headers['owner'])
    assert result.status_code in {409, 422} and rid not in result.text
    after = state(store)
    assert after[:2] == before[:2] and after[3] == before[3]
    if result.status_code == 409:
        assert len(after[2]) == len(before[2]) + 1 and after[2][-1][1]['kind'] == 'request_denied'
    else:
        assert after[2] == before[2]


@pytest.mark.parametrize('location', ['request', 'setup', 'plan'])
def test_currently_known_credentials_block_the_whole_review_without_partial_output(store, location):
    marker = 'PUBLIC_REVIEW_FIXTURE_THAT_BECOMES_A_KNOWN_CREDENTIAL'
    rid = selected(store, value=marker if location == 'request' else 'Public review request')
    save_setup(store, 'owner', 'lnauto', 0, {**full(), 'acceptance': [marker] if location == 'setup' else full()['acceptance']}, str(uuid4()))
    snapshot = context(store, 'owner', rid)
    persist(store, snapshot, response(snapshot, questions=[marker] if location == 'plan' else None))
    reader = Store(replace(store.settings, identities={**store.settings.identities, 'agent': marker}))
    try:
        with TestClient(create_app(reader.settings)) as client:
            result = client.get('/api/project-inbox/review', params={'request_id': rid},
                                headers={'Authorization': 'Bearer ' + reader.settings.identities['owner']})
            assert result.status_code == 409 and marker not in result.text and 'proposal' not in result.text
    finally:
        reader.engine.dispose()


@pytest.mark.parametrize('corruption', ['intake', 'setup_history', 'plan_history'])
def test_integrity_failures_never_fall_back_to_an_empty_or_ready_review(store, corruption):
    rid = configured(store)
    persist(store, context(store, 'owner', rid))
    with store.transaction() as session:
        if corruption == 'intake':
            row = session.get(TelegramInbox, rid)
            row.intent = {'kind': 'capture', 'text': 'Changed without intake anchor'}
        elif corruption == 'setup_history':
            store.audit(session, EVENT, 'owner', project_id='lnauto', version=2)
        else:
            store.audit(session, 'saved_request_plan_draft', 'owner', request_id=rid, document={})
    before = state(store)
    with pytest.raises(Denied):
        read(store, 'owner', rid)
    assert state(store) == before


def test_password_sessions_and_revocation_protect_review(store, password_config):
    rid = configured(store)
    with TestClient(create_app(password_config), base_url='https://testserver') as client:
        assert client.get('/api/project-inbox/review', params={'request_id': rid}).status_code == 401
        csrf = login(client).json()['csrf_token']
        assert client.get('/api/project-inbox/review', params={'request_id': rid}).status_code == 200
        assert client.post('/api/auth/revoke-all', headers={'Origin':'https://testserver', 'X-CSRF-Token':csrf}).status_code == 200
        assert client.get('/api/project-inbox/review', params={'request_id': rid}).status_code == 401


def test_different_requests_projects_and_restart_remain_separate(store, settings):
    first = configured(store)
    second = capture(store, uid=2, value='OTHER_REQUEST_MARKER')
    classify(store, 'owner', second, 'capital-lab', 0, str(uuid4()))
    reader = Store(settings)
    try:
        a, b = read(reader, 'owner', first), read(reader, 'owner', second)
        assert 'OTHER_REQUEST_MARKER' not in canonical(a)
        assert b['project']['setup_version'] == 0 and b['project']['id'] == 'capital-lab'
        assert b['plan']['state'] == 'MISSING' and b['snapshot_digest'] != a['snapshot_digest']
        assert read(store, 'owner', first)['snapshot_digest'] == a['snapshot_digest']
    finally:
        reader.engine.dispose()
