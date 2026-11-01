from uuid import uuid4

import httpx
import pytest

from command_center.project_connections import (
    PERMISSIONS,
    REPOSITORIES,
    connection_plan,
    register,
    validate,
    validate_provenance,
)
from command_center.project_inbox import PROJECTS, classify, inbox
from command_center.project_repair_control import prepare
from command_center.store import Denied
from command_center.telegram_bridge import MockTelegramHTTP, TelegramBridge
from test_telegram_bridge import BotHTTP, OWNER, message
from test_telegram_task_status import authority, response


def manifest(project='command-center'):
    return {'project_id': project, 'repository': REPOSITORIES[project], 'repository_id': 123456,
            'installation_id': 78910, 'default_branch': 'main', 'baseline_sha': 'a' * 40,
            'permissions': dict(PERMISSIONS), 'repository_selection': 'selected',
            'repository_count_verified': True, 'binding_verified': True,
            'branch_protection_verified': True, 'read_only_probe_verified': True}


def capture(store, text='Исправь ошибку и подготовь Draft PR'):
    client = MockTelegramHTTP(httpx.MockTransport(BotHTTP()))
    try:
        return TelegramBridge(store, client, OWNER).receive(message(1, text))['inbox_id']
    finally:
        client.close()


def test_verified_connection_is_disabled_and_idempotent(store):
    before = authority(store)
    operation = str(uuid4())
    first = register(store, 'owner', manifest(), operation)
    assert first['state'] == 'VERIFIED_DISABLED'
    assert first['execution_enabled'] is first['paid_ai_enabled'] is False
    assert first['merge_enabled'] is first['deployment_enabled'] is False
    assert register(store, 'owner', manifest(), operation) == first
    assert authority(store) == before


@pytest.mark.parametrize('change', [
    {'repository': '../bad'}, {'permissions': {'contents': 'write'}},
    {'repository_selection': 'all'}, {'repository_count_verified': False},
    {'binding_verified': False}, {'branch_protection_verified': False},
    {'read_only_probe_verified': False}, {'baseline_sha': 'b' * 39},
])
def test_incomplete_or_broad_connection_evidence_is_rejected(change):
    value = manifest() | change
    with pytest.raises(Denied, match='manifest_invalid'):
        validate(value)


def test_project_identity_is_bound_to_fixed_repository_catalog():
    with pytest.raises(Denied, match='manifest_invalid'):
        validate(manifest() | {'repository': 'owner/other-valid-repository'})


def test_connection_provenance_is_strict_and_idempotency_bound(store):
    operation = str(uuid4())
    provenance = {'evidence_sha256': 'b' * 64, 'operator_revision': 'c' * 40,
                  'plan_digest': 'd' * 64}
    first = register(store, 'owner', manifest(), operation, provenance)
    assert register(store, 'owner', manifest(), operation, provenance) == first
    with pytest.raises(Denied, match='idempotency_conflict'):
        register(store, 'owner', manifest(), operation, provenance | {'plan_digest': 'e' * 64})
    for bad in ({}, provenance | {'extra': 'x'}, provenance | {'evidence_sha256': 'x'}):
        with pytest.raises(Denied, match='provenance_invalid'):
            validate_provenance(bad)


def test_connection_cannot_be_silently_rebound(store):
    register(store, 'owner', manifest(), str(uuid4()))
    changed = manifest() | {'repository_id': 999, 'baseline_sha': 'b' * 40}
    with pytest.raises(Denied, match='replacement_requires_disconnect'):
        register(store, 'owner', changed, str(uuid4()))


def test_repair_plan_requires_assignment_and_verified_connection(store):
    rid = capture(store)
    with pytest.raises(Denied, match='assignment_required'):
        prepare(store, 'owner', rid)
    classify(store, 'owner', rid, 'command-center', 0, str(uuid4()))
    with pytest.raises(Denied, match='connection_required'):
        prepare(store, 'owner', rid)
    register(store, 'owner', manifest(), str(uuid4()))
    plan = prepare(store, 'owner', rid)
    assert plan['stages'] == ['read_only_analysis', 'isolated_edit', 'project_tests',
                              'independent_verification', 'draft_pr']
    assert plan['publication'] == {'draft_pr': True, 'merge': False, 'deploy': False}
    assert plan['authority'] == {'execution': False, 'paid_ai': False, 'repository_write': False}
    assert plan['base_sha'] == 'a' * 40 and len(plan['plan_hash']) == 64
    assert inbox(store, 'owner')['projects'][0]['connection_state'] == 'VERIFIED_DISABLED'


def test_owner_api_and_telegram_show_connection_without_enabling_execution(client, store, headers):
    register(store, 'owner', manifest('capital-lab'), str(uuid4()))
    result = client.get('/api/projects/capital-lab', headers=headers['owner'])
    assert result.status_code == 200
    body = result.json()
    assert body['connection']['state'] == 'VERIFIED_DISABLED'
    assert body['execution_connected'] is body['merge_enabled'] is body['deployment_enabled'] is False
    bot = BotHTTP()
    transport = MockTelegramHTTP(httpx.MockTransport(bot))
    bridge = TelegramBridge(store, transport, OWNER)
    try:
        text = response(bridge, message(10, '/project capital-lab'))
        assert 'Соединение проверено' in text and 'execution, paid AI, merge и deployment выключены' in text
        assert 'торговые и финансовые операции запрещены' in text
    finally:
        transport.close()


@pytest.mark.parametrize('role', ['operator', 'agent'])
def test_non_owner_cannot_register_or_prepare(store, role):
    with pytest.raises(Denied, match='owner_required'):
        register(store, role, manifest(), str(uuid4()))
    with pytest.raises(Denied, match='owner_required'):
        prepare(store, role, 'a' * 64 + ':1')
@pytest.mark.parametrize('project_id', [key for key, _ in PROJECTS])
def test_plan_is_owner_metadata_with_no_claim_of_verified_connectivity(client, store, headers, project_id):
    store.halt('owner')
    before = authority(store)
    result = client.get('/api/projects/' + project_id + '/connection-plan', headers=headers['owner'])
    assert result.status_code == 200
    value = result.json()
    assert value['project_id'] == project_id and value['scope'] == 'PLAN_ONLY'
    assert value['checked_at'] is None and value['external_checks_performed'] is False
    assert value['execution_connected'] is False and value['actions_enabled'] == []
    assert [v['id'] for v in value['components']] == ['repository', 'verification_environment', 'deployment_channel']
    assert all(v['state'] == 'NOT_CHECKED' for v in value['components'])
    assert set(value) == {'schema', 'project_id', 'scope', 'expected_repository', 'checked_at', 'components',
                          'execution_connected', 'external_checks_performed', 'actions_enabled'}
    assert authority(store) == before


@pytest.mark.parametrize('role,status', [('anonymous', 401), ('operator', 409), ('agent', 409)])
def test_project_connections_use_existing_owner_identity(client, headers, role, status):
    response = client.get('/api/projects/lnauto/connection-plan', headers=headers.get(role, {}))
    assert response.status_code == status
    assert 'expected_repository' not in response.json()


def test_unknown_project_and_write_requests_do_not_create_bindings(client, headers, store):
    before = authority(store)
    result = client.get('/api/projects/private-project-fixture/connection-plan', headers=headers['owner'])
    assert result.status_code == 422 and result.json() == {'detail': 'invalid_request'}
    for verb in (client.post, client.put, client.delete):
        assert verb('/api/projects/lnauto/connection-plan', headers=headers['owner']).status_code == 404
    assert authority(store) == before


def test_pure_plan_has_fixed_catalog_and_cannot_be_mutated_into_authority():
    assert {key: connection_plan('owner', key)['expected_repository'] for key, _ in PROJECTS} == {
        'command-center': 'v71369322-lang/ai-command-center',
        'vanilla-sugar': 'v71369322-lang/Vanilla-Sugar-CRM',
        'lnauto': 'v71369322-lang/LNAuto',
        'capital-lab': 'v71369322-lang/Capital-Lab'}
    value = connection_plan('owner', 'lnauto')
    value['components'][0]['state'] = 'VERIFIED'
    value['actions_enabled'].append('deploy')
    assert connection_plan('owner', 'lnauto')['components'][0]['state'] == 'NOT_CHECKED'
    assert connection_plan('owner', 'lnauto')['actions_enabled'] == []
    for bad in ('other', '../lnauto', ['lnauto'], None):
        with pytest.raises(Denied, match='unknown_project'):
            connection_plan('owner', bad)
    with pytest.raises(Denied, match='owner_required'):
        connection_plan('operator', 'lnauto')
