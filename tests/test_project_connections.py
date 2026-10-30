"""Connection plans never probe servers or confer project execution authority."""
import pytest

from command_center.project_connections import connection_plan
from command_center.project_inbox import PROJECTS
from command_center.store import Denied
from test_telegram_task_status import authority


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
