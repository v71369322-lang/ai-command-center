"""Real PG F1 authority plus offline Git proof/patch/check and broker boundaries."""
import base64
import json
from pathlib import Path
import runpy
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

from dulwich.objects import Blob, Commit, Tree
import pytest
from sqlalchemy import select

from command_center.coding.isolated_entry import execute
from command_center.coding.isolated_runner import IsolatedCodingRunner
from command_center.coding_preparation import prepare
from command_center.isolated_coding import create, preview, report, snapshot_files, validate_payload
from command_center.models import Approval, Outbox, Task
from command_center.runtime_broker import RuntimeBroker
from command_center.runtime_ledger import RuntimeLedger
from command_center.runtime_policy import RuntimeLimits
from command_center.local_docker import run as docker
from command_center.worker import Runner
from command_center.project_setup import patch
from command_center.store import Denied, Store, digest
from test_coding_preparation import request, saved_request
import test_plan_acceptance

SOURCE = 'src/command_center/example.py'
TEST = 'tests/test_example.py'
BASE = 'def value():\n    return 1\n'
FIX = 'def value():\n    return 2\n'
TEST_SOURCE = 'from command_center.example import value\n\ndef test_value():\n    assert value() == 2\n'


def snapshot(test_source=TEST_SOURCE, mode=0o100644):
    objects = []

    def tree(entries):
        result = Tree()
        for name, value in entries.items():
            if isinstance(value, dict):
                child = tree(value)
                result.add(name.encode(), 0o040000, child.id)
            else:
                child = Blob.from_string(value.encode())
                objects.append(child)
                result.add(name.encode(), mode, child.id)
        objects.append(result)
        return result

    root = tree({'src': {'command_center': {'example.py': BASE, '__init__.py': ''}},
                 'tests': {'test_example.py': test_source}})
    commit = Commit()
    commit.tree = root.id
    commit.author = commit.committer = b'Local fixture <fixture@invalid>'
    commit.author_time = commit.commit_time = 0
    commit.author_timezone = commit.commit_timezone = 0
    commit.message = b'Fixture\n'
    objects.append(commit)
    return commit.id.decode(), {'objects': [{'kind': o.type_name.decode(),
        'data': base64.b64encode(o.as_raw_string()).decode()} for o in objects]}


def binding(store, monkeypatch, test_source=TEST_SOURCE):
    revision, bundle = snapshot(test_source)
    original = test_plan_acceptance.full()
    monkeypatch.setattr(test_plan_acceptance, 'full', lambda: {**original, 'repository_revision': revision})
    rid = test_plan_acceptance.ready(store)
    preparation = request(store, rid)
    preparation['scope']['allowed_files'].append('src/command_center/__init__.py')
    spec = prepare(store, 'owner', saved_request(store, preparation))
    return {'request_id': rid, 'expected_spec_digest': spec['spec_digest'],
            'snapshot': bundle, 'replacements': {SOURCE: FIX}}


def save(store, body):
    view = preview(store, 'owner', body)
    return {**body, 'expected_payload_digest': view['payload_digest']}


def test_task_api_requires_separate_f1_approval_and_no_grants(store, client, headers, monkeypatch):
    body = binding(store, monkeypatch)
    p = client.post('/api/project-inbox/coding/task-preview', json=body, headers=headers['owner'])
    assert p.status_code == 200 and p.json()['execution_authorized'] is False
    value = {**body, 'expected_payload_digest': p.json()['payload_digest']}
    r = client.post('/api/project-inbox/coding/task', json=value, headers=headers['owner'])
    assert r.status_code == 200
    task = r.json()
    assert task['state'] == 'WAITING_APPROVAL' and task['payload']['cost'] == 0
    assert store.claim(task['id']) is None
    with store.transaction() as session:
        assert session.scalars(select(Approval)).all() == []
        assert session.scalars(select(Outbox)).all() == []
    assert create(store, 'owner', value)['id'] == task['id']
    store.approve('owner', task['id'], 1)
    claimed = store.claim(task['id'])
    assert claimed['state'] == 'RUNNING' and claimed['fence'] == 1
    assert store.pulse(task['id'], 1)
    assert not store.pulse(task['id'], 0)
    store.cancel('owner', task['id'])
    assert not store.pulse(task['id'], 1)
    with pytest.raises(Denied):
        store.finish(task['id'], 1, 'untrusted', '0'*64)


def test_concurrent_bindings_create_one_waiting_task(store, monkeypatch):
    body = save(store, binding(store, monkeypatch))
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = list(pool.map(lambda _: create(store, 'owner', body), range(2)))
    assert tasks[0]['id'] == tasks[1]['id']
    with store.transaction() as session:
        assert len(session.scalars(select(Task)).all()) == 1


@pytest.mark.parametrize('stage', ['create', 'approve', 'claim', 'pulse', 'finish'])
def test_changed_context_fails_closed_at_every_boundary(store, monkeypatch, stage):
    body = save(store, binding(store, monkeypatch))
    task = None if stage == 'create' else create(store, 'owner', body)
    if stage in {'claim', 'pulse', 'finish'}:
        store.approve('owner', task['id'], 1)
    if stage in {'pulse', 'finish'}:
        store.claim(task['id'])
    patch(store, 'owner', 'command-center', 1, 'acceptance', ['New criterion'], '22222222-2222-4222-8222-222222222222')
    with pytest.raises(Denied, match='coding_binding_stale'):
        if stage == 'create':
            create(store, 'owner', body)
        elif stage == 'approve':
            store.approve('owner', task['id'], 1)
        elif stage == 'claim':
            store.claim(task['id'])
        elif stage == 'pulse':
            store.pulse(task['id'], 1)
        else:
            store.finish(task['id'], 1, 'x', '0'*64)


@pytest.mark.parametrize('role', ['operator', 'agent'])
def test_nonowner_cannot_bind_or_directly_create(store, monkeypatch, role):
    body = binding(store, monkeypatch)
    value = preview(store, 'owner', body)['payload']
    with pytest.raises(Denied):
        preview(store, role, body)
    with pytest.raises(Denied):
        store.create(role, 'bypass', value)


def test_exact_review_and_source_pins(store, monkeypatch):
    body = save(store, binding(store, monkeypatch))
    wrong = {**body, 'replacements': {SOURCE: FIX.replace('2', '3')}}
    with pytest.raises(Denied, match='payload_changed'):
        create(store, 'owner', wrong)
    task = create(store, 'owner', body)
    other = Store(replace(store.settings, source_revision='b'*40))
    try:
        with pytest.raises(Denied):
            other.approve('owner', task['id'], 1)
    finally:
        other.engine.dispose()


@pytest.mark.parametrize('change', ['base', 'blob', 'extra', 'missing', 'duplicate', 'symlink', 'executable'])
def test_git_snapshot_proof_rejects_changes(change):
    revision, bundle = snapshot(mode=0o120000 if change == 'symlink' else 0o100755 if change == 'executable' else 0o100644)
    if change == 'base':
        revision = '0'*40
    elif change == 'blob':
        bundle['objects'][0]['data'] = base64.b64encode(b'forged').decode()
    elif change == 'extra':
        bundle['objects'].append({'kind': 'blob', 'data': base64.b64encode(b'extra').decode()})
    elif change == 'missing':
        bundle['objects'].pop(0)
    elif change == 'duplicate':
        bundle['objects'].append(bundle['objects'][0])
    with pytest.raises(Denied, match='coding_snapshot_invalid'):
        snapshot_files(bundle, revision, [SOURCE, TEST, 'src/command_center/__init__.py'])


@pytest.mark.parametrize('kind,raw', [('commit', b'bad'), ('tree', b'bad'), ('blob', b'')])
def test_malformed_git_objects_are_denials(kind, raw):
    revision, bundle = snapshot()
    bundle['objects'][-1] = {'kind': kind, 'data': base64.b64encode(raw).decode()}
    with pytest.raises(Denied):
        snapshot_files(bundle, revision, [SOURCE, TEST, 'src/command_center/__init__.py'])


@pytest.mark.parametrize('change', ['outside', 'tests', 'same', 'cost', 'provider', 'policy', 'large', 'newline'])
def test_fixed_offline_scope_cannot_expand(store, monkeypatch, change):
    value = preview(store, 'owner', binding(store, monkeypatch))['payload']
    if change == 'outside':
        value['replacements'] = {'../../evil.py': FIX}
    elif change == 'tests':
        value['replacements'][TEST] = 'def test_fake(): pass\n'
    elif change == 'same':
        value['replacements'] = {SOURCE: BASE}
    elif change == 'cost':
        value['cost'] = 1
    elif change == 'provider':
        value['provider'] = 'openai'
    elif change == 'policy':
        value['specification']['isolation']['network'] = 'host'
        value['spec_digest'] = digest(value['specification'])
    elif change == 'newline':
        value['replacements'][SOURCE] = FIX.rstrip('\n')
    else:
        value['replacements'] = {SOURCE: 'x'*40000}
    with pytest.raises(Denied):
        validate_payload(value)


def test_known_secret_rejected_after_base64_decoding(store, monkeypatch):
    value = binding(store, monkeypatch)
    value['replacements'][SOURCE] = 'secret = ' + repr(store.settings.redis_password) + '\n'
    with pytest.raises(Denied, match='sensitive_content'):
        preview(store, 'owner', value)


def test_real_patch_and_checks_repeat_in_fresh_workspaces(store, monkeypatch, tmp_path):
    value = preview(store, 'owner', binding(store, monkeypatch))['payload']
    first = execute(value, tmp_path / 'agent')
    second = execute(value, tmp_path / 'verifier')
    assert first == second and first['passed']
    IsolatedCodingRunner.validate_result(first, report(value), value)
    assert (tmp_path / 'agent' / SOURCE).read_text() == FIX
    bad = deepcopy(first)
    bad['files'][SOURCE] = '0'*64
    with pytest.raises(Denied):
        IsolatedCodingRunner.validate_result(bad, report(value), value)


def test_failed_checks_do_not_become_verified(store, monkeypatch, tmp_path):
    value = preview(store, 'owner', binding(store, monkeypatch))['payload']
    value['replacements'][SOURCE] = FIX.replace('2', '3')
    result = execute(value, tmp_path / 'failed')
    assert not result['passed']
    with pytest.raises(Denied):
        IsolatedCodingRunner.validate_result(result, report(value), value)


def test_tests_cannot_modify_workspace_and_return_success(store, monkeypatch, tmp_path):
    source = "from pathlib import Path\n\ndef test_escape():\n    Path('src/command_center/example.py').write_text('forged')\n"
    value = preview(store, 'owner', binding(store, monkeypatch, source))['payload']
    with pytest.raises(ValueError, match='workspace_changed'):
        execute(value, tmp_path / 'changed')


def test_runner_requires_rootless(store, monkeypatch):
    runner = object.__new__(IsolatedCodingRunner)
    runner.runtime = SimpleNamespace(mode='cloud-rootful-test')
    value = preview(store, 'owner', binding(store, monkeypatch))['payload']
    with pytest.raises(Denied, match='rootless_required'):
        runner.execute({'payload': value})


@pytest.mark.parametrize('mode,limits,reason', [
    ('cloud-rootful-test', RuntimeLimits(), 'rootless_required'),
    ('rootless-required', RuntimeLimits(cpu=1), 'runtime_limits'),
    ('rootless-required', RuntimeLimits(), 'watchdog_unavailable')])
def test_broker_rejects_before_consuming_approval(store, monkeypatch, tmp_path, mode, limits, reason):
    task = create(store, 'owner', save(store, binding(store, monkeypatch)))
    store.approve('owner', task['id'], 1)
    backend = SimpleNamespace(mode=mode, preflight=lambda: pytest.fail('no runtime I/O'))
    service = RuntimeBroker(store, RuntimeLedger(tmp_path / 'runtime.sqlite'), backend, limits)
    try:
        with pytest.raises(Denied, match=reason):
            service.submit(task['id'], store.settings.source_revision)
        assert store.get(task['id'])['state'] == 'READY'
        with store.transaction() as session:
            assert session.get(Approval, task['id']).used is False
    finally:
        service.pool.shutdown(wait=True)


@pytest.mark.parametrize('failure', [None, 'forged', 'stop', 'revoked'])
def test_runner_composition_uses_f1_and_durable_stage_fencing(store, monkeypatch, tmp_path, failure):
    task = create(store, 'owner', save(store, binding(store, monkeypatch)))
    store.approve('owner', task['id'], 1)
    task = store.claim(task['id'])
    task['revision'] = store.settings.source_revision
    ledger = RuntimeLedger(tmp_path / 'runtime.sqlite')
    ledger.register(task, Runner.name(task), 120)
    runner = IsolatedCodingRunner(store, SimpleNamespace(mode='rootless-required'), RuntimeLimits(), ledger)
    stages = []

    def stage(task, job):
        assert store.pulse(task['id'], task['fence'])
        ledger.phase(task['id'], task['fence'], 'ACTIVE')
        runner.launch_attempted = True
        stages.append(job['mode'])
        result = {**report(task['payload']), 'checks': [
            {'command': c, 'passed': True} for c in task['payload']['specification']['verification_commands']],
            'passed': True}
        if failure == 'forged' and job['mode'] == 'verify':
            result['passed'] = 1  # bool/int confusion must not count as verifier proof.
        if failure == 'revoked' and job['mode'] == 'verify':
            store.cancel('owner', task['id'])
        return result

    monkeypatch.setattr(runner, 'stage', stage)
    monkeypatch.setattr(runner, 'stop', lambda _: failure != 'stop')
    monkeypatch.setattr(runner, 'quiesce', lambda _: failure != 'stop')
    if failure:
        with pytest.raises(Denied):
            runner.execute(task)
        assert store.get(task['id'])['state'] in {'FAILED', 'CANCELLED', 'RECONCILING'}
        assert store.get(task['id'])['artifact'] is None
    else:
        runner.execute(task)
        assert stages == ['agent', 'verify']
        final = store.get(task['id'])
        assert final['state'] == 'SUCCEEDED'
        assert json.loads(final['artifact'])['independent_verification'] is True
        assert store.snapshot()['budget']['actual'] == 0


@pytest.mark.parametrize('downgrade', [False, True])
def test_normal_stop_and_payload_tampering_fail_closed(store, monkeypatch, downgrade):
    body = save(store, binding(store, monkeypatch))
    task = create(store, 'owner', body)
    with store.transaction() as session:
        row = session.get(Task, task['id'])
        value = deepcopy(row.payload)
        value['replacements'][SOURCE] = FIX.replace('2', '3')
        if downgrade:
            value = {'kind': 'approved_render', 'values': {'x': 'forged'}, 'cost': 0}
        row.payload = value
        row.payload_hash = digest(value)
    with pytest.raises(Denied, match='payload_integrity'):
        store.approve('owner', task['id'], 1)
    store.halt('owner')
    with pytest.raises(Denied):
        create(store, 'owner', body)


def test_actual_container_applies_patch_and_checks_with_no_mounts_or_network(store, monkeypatch):
    """Cloud rootful sandbox smoke, deliberately NOT rootless/VPS acceptance."""
    value = preview(store, 'owner', binding(store, monkeypatch))['payload']
    metadata = docker('image', 'inspect', store.settings.coding_image, '--format', '{{json .}}')
    assert metadata.returncode == 0
    image = json.loads(metadata.stdout)
    assert image['Config']['Labels']['org.opencontainers.image.revision'] == store.settings.source_revision
    job = {'operation_id': str(uuid4()), 'fence': 1, 'mode': 'agent', 'payload': value}
    results = []
    for mode in ['agent', 'verify']:
        name = 'acc-isolated-smoke-' + uuid4().hex
        args = Runner.command(name, image['Id'])[2:]
        try:
            result = docker(*args, input=json.dumps({**job, 'mode': mode}).encode(), timeout=25)
            assert result.returncode == 0, 'isolated_container_failed'
            envelope = json.loads(result.stdout)
            IsolatedCodingRunner.validate_result(envelope['result'], report(value), value)
            results.append(envelope['result'])
            info = docker('inspect', name)
            assert info.returncode == 0
            assert Runner.valid_isolation(json.loads(info.stdout)[0])
        finally:
            docker('rm', '--force', name)
    assert results[0] == results[1]


def test_offline_materializer_reads_exact_git_objects_not_worktree(store, monkeypatch, tmp_path):
    from dulwich.repo import Repo
    body = binding(store, monkeypatch)
    payload = preview(store, 'owner', body)['payload']
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/prepare_isolated_coding.py'))
    root = tmp_path / 'local-repository'
    root.mkdir()
    with Repo.init(root) as repo:
        for item in body['snapshot']['objects']:
            obj = {'commit': Commit, 'tree': Tree, 'blob': Blob}[item['kind']].from_string(
                base64.b64decode(item['data']))
            repo.object_store.add_object(obj)
    (root / 'untracked-private.txt').write_text('Must never be exported')
    preparation = {'specification': payload['specification'], 'spec_digest': body['expected_spec_digest']}
    result = module['materialize'](str(root), preparation, body['replacements'])
    assert preview(store, 'owner', result)['payload_digest'] == digest(payload)
