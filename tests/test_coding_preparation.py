"""Non-runnable specifications only; repository/runtime/provider access is absent."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from sqlalchemy import select

from command_center.coding_preparation import EVENT, FLAGS, CodingScope, preview, prepare, read
from command_center.models import Audit
from command_center.plan_acceptance import accept
from command_center.store import Denied, ZERO, digest
from test_plan_acceptance import ready, body
from test_telegram_task_status import authority
from test_telegram_readiness import ledger


def scope():
    return {'allowed_files': ['src/command_center/example.py'], 'test_files': ['tests/test_example.py']}


def request(store, rid):
    accepted = accept(store, 'owner', body(store, rid))
    return {'request_id': rid, 'expected_acceptance_digest': accepted['snapshot_digest'], 'scope': scope()}


def saved_request(store, value):
    view = preview(store, 'owner', value)
    return {**value, 'expected_spec_digest': view['spec_digest']}


def rows(store):
    with store.transaction() as tx:
        return list(tx.scalars(select(Audit).where(Audit.event['kind'].as_string() == EVENT)))


def test_pinned_specification_is_reviewable_and_cannot_be_dispatched(store, client, headers):
    rid = ready(store)
    value = request(store, rid)
    before = authority(store), ledger(store)
    p = client.post('/api/project-inbox/coding/preparation-preview', json=value, headers=headers['owner'])
    assert p.status_code == 200 and p.json()['stored'] is False and not rows(store)
    save = {**value, 'expected_spec_digest': p.json()['spec_digest']}
    r = client.post('/api/project-inbox/coding/preparation', json=save, headers=headers['owner'])
    assert r.status_code == 200
    spec = r.json()['specification']
    assert spec['state'] == 'PREPARED_NOT_RUNNABLE'
    assert spec['isolation'] == {'network': 'none', 'credentials': False, 'host_paths': False,
        'base_read_only': True, 'workspace': 'ephemeral', 'runtime_mode': 'rootless-required',
        'non_root_required': True, 'privileged': False, 'cap_drop': ['ALL'], 'no_new_privileges': True,
        'memory_mib': 256, 'millicpus': 500, 'pids_limit': 64}
    assert spec['verification_commands'][-1] == ['python', '-m', 'pytest', '--', 'tests/test_example.py']
    assert {k: spec[k] for k in FLAGS} == FLAGS
    assert (authority(store), ledger(store)) == before
    assert prepare(store, 'owner', save) == r.json() and len(rows(store)) == 1
    assert read(store, 'owner', rid)['state'] == 'PREPARED_NOT_RUNNABLE'


def test_existing_current_acceptance_is_mandatory(store):
    rid = ready(store)
    with pytest.raises(Denied, match='current_acceptance_required'):
        preview(store, 'owner', {'request_id': rid, 'expected_acceptance_digest': 'a'*64, 'scope': scope()})
    assert not rows(store)


def test_concurrent_identical_preparation_is_one_record(store):
    rid = ready(store)
    save = saved_request(store, request(store, rid))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: prepare(store, 'owner', save), range(2)))
    assert results[0] == results[1] and len(rows(store)) == 1


def test_changed_context_or_owner_scope_cannot_reuse_review_digest(store):
    rid = ready(store)
    save = saved_request(store, request(store, rid))
    prepare(store, 'owner', save)
    changed = deepcopy(save)
    changed['scope']['allowed_files'] = ['src/command_center/other.py']
    with pytest.raises(Denied, match='snapshot_changed'):
        prepare(store, 'owner', changed)
    store.halt('owner')
    assert read(store, 'owner', rid)['state'] == 'STALE'
    with pytest.raises(Denied, match='current_acceptance_required'):
        prepare(store, 'owner', save)
    assert len(rows(store)) == 1


@pytest.mark.parametrize('path', ['/etc/passwd.py', '../evil.py', 'tests/../evil.py',
    'tests//test_x.py', 'C:/evil.py', 'tests/test_x.py;id', 'tests/.git/test_x.py',
    'tests/__pycache__/test_x.py', 'infra/vps/test_x.py', '.github/test_x.py', 'tests/test_x.txt'])
def test_host_paths_traversal_hidden_and_command_fragments_are_rejected(path):
    with pytest.raises(ValueError):
        CodingScope.model_validate({**scope(), 'allowed_files': [path]})


@pytest.mark.parametrize('extra', [{'provider': 'openai'}, {'network': 'host'}, {'max_seconds': 121},
    {'max_iterations': 3}, {'max_diff_bytes': 32769}, {'max_seconds': True}, {'shell': 'id'}])
def test_scope_cannot_expand_authority_or_resource_bounds(extra):
    with pytest.raises(ValueError):
        CodingScope.model_validate({**scope(), **extra})


def test_preparation_failure_rolls_back_specification(store, monkeypatch):
    import command_center.coding_preparation as module
    rid = ready(store)
    save = saved_request(store, request(store, rid))
    original = module.history
    def fail(*args):
        result = original(*args)
        if result:
            raise RuntimeError('public fixture rollback')
        return result
    monkeypatch.setattr(module, 'history', fail)
    with pytest.raises(RuntimeError):
        prepare(store, 'owner', save)
    assert not rows(store)


@pytest.mark.parametrize('attack', ['network', 'credentials', 'commands', 'execution', 'acceptance'])
def test_resealed_specification_cannot_change_isolation_commands_or_receipt(store, admin, attack):
    rid = ready(store)
    prepare(store, 'owner', saved_request(store, request(store, rid)))
    with admin.transaction() as tx:
        all_rows = list(tx.scalars(select(Audit).order_by(Audit.sequence)))
        for row in all_rows:
            if row.event['kind'] == EVENT:
                e = deepcopy(row.event)
                spec = e['specification']
                if attack in {'network', 'credentials'}:
                    spec['isolation'][attack] = 'host' if attack == 'network' else True
                elif attack == 'commands':
                    spec['verification_commands'] = [['sh', '-c', 'id']]
                elif attack == 'execution':
                    spec['execution_authorized'] = True
                else:
                    spec['acceptance_digest'] = 'f'*64
                e['spec_digest'] = digest(spec)
                row.event = e
        previous = ZERO
        for row in all_rows:
            row.previous = previous
            row.digest = digest({'previous': previous, 'event': row.event})
            previous = row.digest
    with pytest.raises(Denied, match='coding_preparation_integrity'):
        read(store, 'owner', rid)


@pytest.mark.parametrize('role', ['operator', 'agent'])
def test_nonowner_cannot_prepare_or_read(store, client, headers, role):
    rid = ready(store)
    value = request(store, rid)
    assert client.post('/api/project-inbox/coding/preparation-preview', json=value, headers=headers[role]).status_code == 409
    assert client.get('/api/project-inbox/coding/preparation', params={'request_id': rid}, headers=headers[role]).status_code == 409
    assert client.post('/api/project-inbox/coding/preparation', json=saved_request(store, value),
                       headers=headers[role]).status_code == 409
    assert not rows(store)


def test_restart_and_capacity_preserve_exact_preparations(store, settings, monkeypatch):
    import command_center.coding_preparation as module
    from command_center.store import Store
    rid = ready(store)
    value = request(store, rid)
    save = saved_request(store, value)
    first = prepare(store, 'owner', save)
    restarted = Store(settings)
    try:
        assert prepare(restarted, 'owner', save) == first
        assert read(restarted, 'owner', rid)['preparation'] == first
    finally:
        restarted.engine.dispose()
    monkeypatch.setattr(module, 'MAX_PREPARATIONS', 1)
    assert prepare(store, 'owner', save) == first
    other = deepcopy(value)
    other['scope']['max_seconds'] = 30
    with pytest.raises(Denied, match='capacity'):
        prepare(store, 'owner', saved_request(store, other))
    assert len(rows(store)) == 1


def test_credential_shaped_file_names_are_not_stored(store):
    rid = ready(store)
    value = request(store, rid)
    value['scope']['allowed_files'] = ['src/command_center/ghp_'+'A'*30+'.py']
    with pytest.raises(Denied, match='sensitive_content'):
        preview(store, 'owner', value)
    assert not rows(store)
