import json
import subprocess
import time
from uuid import uuid4

import httpx
import pytest

from command_center.coding.agent import execute
from command_center.coding.contract import CodingRequest, payload
from command_center.coding.providers import ResponsesProvider, ProviderUnavailable
from command_center.coding.publication import GitHubPublisher, PublicationUncertain, prepare_draft
from command_center.coding.spec import BASE_SHA, CORRECT
from command_center.coding.verification import inspect_result, replay
from command_center.coding.workspace import Workspace
from command_center.runtime_broker import RuntimeBroker
from command_center.runtime_ledger import RuntimeLedger
from command_center.runtime_policy import RuntimeBackend, RuntimeLimits


def job(**changes):
    return {'operation_id': str(uuid4()), 'fence': 1, 'coding': CodingRequest(**changes).model_dump()}


def test_real_git_edit_test_repair_and_independent_replay(tmp_path):
    request = job()
    result = execute(request, tmp_path / 'repository')
    assert result['status'] == 'ready_for_verification'
    assert [r['checks']['passed'] for r in result['history']] == [False, True]
    report, _, snapshots = inspect_result(result, request['operation_id'], 1, request['coding'])
    assert replay(result, request['operation_id'], 1, request['coding'], tmp_path / 'verify') == report
    branch = subprocess.run(['git', '-C', str(tmp_path / 'repository'), 'branch', '--show-current'],
                            capture_output=True, timeout=5, check=True).stdout.decode().strip()
    assert branch == report['branch']
    assert subprocess.run(['git', '-C', str(tmp_path / 'repository'), 'rev-parse', 'HEAD'],
                          capture_output=True, timeout=5, check=True).stdout.decode().strip() == report['head_sha']
    draft = prepare_draft(request['operation_id'], report, snapshots[-1])
    assert draft['mode'] == 'mock' and not draft['published'] and draft['url'] is None
    assert 'calculator.py' in draft['diff'] and draft['head_sha'] != BASE_SHA


@pytest.mark.parametrize('scenario,status', [('unavailable', 'provider_unavailable'),
    ('always_fail', 'attempt_limit'), ('escape_attempt', 'scope_or_execution_blocked'),
    ('pin_change', 'scope_or_execution_blocked')])
def test_agent_failures_are_bounded(tmp_path, scenario, status):
    result = execute(job(scenario=scenario), tmp_path / 'repository')
    assert result['status'] == status
    assert 'git' not in result
    assert result['usage']['units'] <= 2
    assert not (tmp_path / 'outside.py').exists()


@pytest.mark.parametrize('limits', [{'max_iterations': 1}, {'max_units': 1}, {'max_tokens': 64}])
def test_agent_iteration_token_and_budget_limits(tmp_path, limits):
    result = execute(job(**limits), tmp_path / 'repository')
    assert result['status'] in {'attempt_limit', 'budget_limit'}
    assert len(result['history']) <= 1


def test_workspace_pin_and_symlink_boundaries(tmp_path):
    with pytest.raises(ValueError):
        Workspace(tmp_path / 'bad', str(uuid4()), 1, '0' * 40)
    workspace = Workspace(tmp_path / 'repo', str(uuid4()), 1, BASE_SHA)
    try:
        with pytest.raises(ValueError):
            workspace.apply({'.git/config': 'unsafe'})
        (workspace.root / 'calculator.py').unlink()
        outside = tmp_path / 'outside.py'
        outside.write_text('untouched')
        (workspace.root / 'calculator.py').symlink_to(outside)
        with pytest.raises(ValueError):
            workspace.apply({'calculator.py': CORRECT})
        assert outside.read_text() == 'untouched'
    finally:
        workspace.repo.close()


@pytest.mark.parametrize('mutation', ['checks', 'object', 'head', 'branch', 'units', 'negative_tokens', 'unreachable'])
def test_independent_verifier_rejects_fabricated_agent_evidence(tmp_path, mutation):
    request = job()
    result = execute(request, tmp_path / 'repo')
    if mutation == 'checks':
        result['history'][0]['checks']['passed'] = True
    elif mutation == 'object':
        first = next(iter(result['git']['objects']))
        result['git']['objects'][first]['data'] = 'Zm9yZ2Vk'
    elif mutation == 'head':
        result['git']['head_sha'] = BASE_SHA
    elif mutation == 'branch':
        result['git']['branch'] = 'main'
    elif mutation == 'units':
        result['usage']['units'] = 0
    elif mutation == 'negative_tokens':
        result['usage']['tokens'] = -1
    else:
        from dulwich.objects import Blob
        import base64
        extra = Blob.from_string(b'unrelated object')
        result['git']['objects'][extra.id.decode()] = {'type': 3, 'data': base64.b64encode(extra.data).decode()}
    with pytest.raises((ValueError, KeyError)):
        inspect_result(result, request['operation_id'], 1, request['coding'])


def test_responses_adapter_is_authorized_offline_only():
    seen = []
    def transport(request):
        seen.append(request)
        data = json.loads(request.content)
        assert request.url.path == '/v1/responses' and data['max_output_tokens'] == 256
        assert data['store'] is False and data['text']['format']['strict'] is True
        return httpx.Response(200, json={'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps({'source': CORRECT})}]}],
            'usage': {'input_tokens': 100, 'output_tokens': 50}})
    client = httpx.Client(transport=httpx.MockTransport(transport))
    provider = ResponsesProvider(model='synthetic-model', token='public-fixture-not-real', client=client,
                                 max_output_tokens=256)
    with pytest.raises(PermissionError):
        provider.propose({'task': 'synthetic'})
    assert not seen
    provider.authorized = True
    assert provider.propose({'task': 'synthetic'}).changes == {'calculator.py': CORRECT}
    assert len(seen) == 1
    client.close()


def test_provider_timeout_is_uncertain_and_never_retried():
    calls = []
    def transport(request):
        calls.append(1)
        raise httpx.ReadTimeout('synthetic uncertain outcome')
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        provider = ResponsesProvider(model='fixture', token='public-fixture', client=client, authorized=True)
        with pytest.raises(ProviderUnavailable) as unavailable:
            provider.propose({'task': 'synthetic'})
        assert unavailable.value.uncertain and len(calls) == 1


def test_github_adapter_mock_timeout_retains_intent_and_blocks_repeat(tmp_path):
    request = job()
    result = execute(request, tmp_path / 'repo')
    report, _, snapshots = inspect_result(result, request['operation_id'], 1, request['coding'])
    draft = prepare_draft(request['operation_id'], report, snapshots[-1])
    posts = []
    def transport(message):
        if message.method == 'GET':
            sha = draft['base_sha'] if message.url.path.endswith('/main') else draft['head_sha']
            return httpx.Response(200, json={'object': {'sha': sha}})
        posts.append(1)
        raise httpx.ReadTimeout('synthetic PR may exist')
    journal = {}
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        publisher = GitHubPublisher('fixture/synthetic-f2', 'public-test-token', client=client)
        with pytest.raises(PermissionError):
            publisher.publish(draft, journal)
        assert not posts
        publisher.authorized = True
        with pytest.raises(PublicationUncertain):
            publisher.publish(draft, journal)
        with pytest.raises(PublicationUncertain):
            publisher.publish(draft, journal)
    assert len(posts) == 1 and journal[draft['idempotency_key']]['state'] == 'INTENT'


def test_coding_api_scope_and_owner_authority(client, headers, store):
    command = CodingRequest().model_dump()
    for role in ('agent', 'operator'):
        assert client.post('/api/coding/tasks', json=command,
                           headers={**headers[role], 'Idempotency-Key': str(uuid4())}).status_code == 409
    for change in [{'repository': 'CRM'}, {'provider': 'real'}, {'max_iterations': 20}, {'shell': 'unsafe'}]:
        assert client.post('/api/coding/tasks', json={**command, **change},
                           headers={**headers['owner'], 'Idempotency-Key': str(uuid4())}).status_code == 422
    assert client.post('/api/coding/tasks', json={**command, 'base_sha': '0' * 40},
                       headers={**headers['owner'], 'Idempotency-Key': str(uuid4())}).status_code == 409
    result = client.post('/api/coding/tasks', json=command,
                         headers={**headers['owner'], 'Idempotency-Key': 'coding-idempotent'})
    assert result.status_code == 201
    assert client.get('/api/tasks/' + result.json()['id'] + '/pull-request', headers=headers['owner']).status_code == 409


def test_f2_real_broker_two_sandboxes_and_atomic_pr(store, tmp_path):
    ledger = RuntimeLedger(tmp_path / 'runtime.sqlite')
    ledger.watchdog()
    service = RuntimeBroker(store, ledger, RuntimeBackend(mode='cloud-rootful-test'), RuntimeLimits())
    try:
        task = store.create('owner', str(uuid4()), payload(CodingRequest(max_units=3)))
        run = service.submit(task['id'], store.settings.source_revision)
        service.last_future.result(timeout=30)
        result = store.get(task['id'])
        assert result['state'] == 'SUCCEEDED'
        assert result['coding']['pr']['mode'] == 'mock'
        assert [r['checks']['passed'] for r in result['coding']['test_runs']] == [False, True]
        assert 'agent_result' not in result['coding']
        assert result['coding']['provider_usage']['units'] == 2
        assert store.snapshot()['budget']['actual'] == 2 and store.snapshot()['budget']['reserved'] == 0
        assert ledger.get(task['id'], run['fence'])['phase'] == 'DONE'
        assert service.submit(task['id'], store.settings.source_revision)['phase'] == 'NOT_ADMITTED'
    finally:
        service.pool.shutdown(wait=True)


@pytest.mark.parametrize('stop', ['cancel', 'deadline', 'watchdog_lost'])
def test_f2_runtime_stop_never_accepts_pr_or_restarts(store, tmp_path, stop):
    ledger = RuntimeLedger(tmp_path / 'runtime.sqlite')
    ledger.watchdog()
    service = RuntimeBroker(store, ledger, RuntimeBackend(mode='cloud-rootful-test'), RuntimeLimits())
    try:
        task = store.create('owner', str(uuid4()), payload(CodingRequest(
            scenario='slow', max_seconds=2 if stop == 'deadline' else 15)))
        run = service.submit(task['id'], store.settings.source_revision)
        deadline = time.monotonic() + 8
        while ledger.get(task['id'], run['fence'])['phase'] != 'ACTIVE' and time.monotonic() < deadline:
            time.sleep(.05)
        assert ledger.get(task['id'], run['fence'])['phase'] == 'ACTIVE'
        if stop == 'cancel':
            store.cancel('owner', task['id'])
            store.cancel('owner', task['id'])
        elif stop == 'watchdog_lost':
            with ledger.tx() as db:
                db.execute('UPDATE monitor SET heartbeat=0')
        service.last_future.result(timeout=20)
        result = store.get(task['id'])
        assert result['state'] == ('CANCELLED' if stop == 'cancel' else 'FAILED')
        assert not result['coding'].get('pr')
        assert ledger.get(task['id'], run['fence'])['phase'] == 'DONE'
        # Unknown usage is retained; verified absence of a container is not billing evidence.
        assert store.snapshot()['budget']['reserved'] == 2
        with pytest.raises(Exception, match='retry_not_safe'):
            store.retry('owner', task['id'])
        ledger.watchdog()
        assert service.submit(task['id'], store.settings.source_revision)['phase'] == 'NOT_ADMITTED'
    finally:
        service.pool.shutdown(wait=True)
