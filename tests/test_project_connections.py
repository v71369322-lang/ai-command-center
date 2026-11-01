from uuid import uuid4

import httpx
import pytest

from command_center.project_connections import PERMISSIONS, register, validate
from command_center.project_inbox import classify, inbox
from command_center.project_repair_control import prepare
from command_center.store import Denied
from command_center.telegram_bridge import MockTelegramHTTP, TelegramBridge
from test_telegram_bridge import BotHTTP, OWNER, message
from test_telegram_task_status import authority, response


def manifest(project='command-center'):
    return {'project_id': project, 'repository': 'owner/example-project', 'repository_id': 123456,
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
