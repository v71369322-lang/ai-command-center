"""Explicit file/test scope from the observed owner chat; no coding executor."""
import json

import pytest
from sqlalchemy import select

from command_center.coding_preparation import EVENT
from command_center.models import Audit
from command_center.telegram_coding_preparation import parse
from command_center.store import Denied
from test_telegram_plan_acceptance import content as content, issue, click
from test_telegram_readiness import bridge as bridge
from test_telegram_service import configured as configured, update
from test_telegram_task_status import authority
from test_telegram_readiness import ledger


def test_observed_plan_then_explicit_scope_prepares_without_task(bridge, store, content):
    issue(bridge)
    bridge[0].receive(click(bridge))
    before = authority(store), ledger(store)
    scope = {'allowed_files': ['src/command_center/example.py'], 'test_files': ['tests/test_example.py']}
    command = update(40, '/coding_prepare 10 '+json.dumps(scope))
    bridge[0].receive(command)
    bridge[0].receive(command)
    with store.transaction() as tx:
        rows = list(tx.scalars(select(Audit).where(Audit.event['kind'].as_string() == EVENT)))
    assert len(rows) == 1 and rows[0].event['specification']['state'] == 'PREPARED_NOT_RUNNABLE'
    assert (authority(store), ledger(store)) == before
    bridge[0].receive(update(41, '/coding_prepare 10'))
    while bridge[0].deliver_one():
        pass
    assert any('PREPARED_NOT_RUNNABLE' in body['text'] for body in bridge[1].sent)


def test_no_implicit_files_or_unaccepted_plan(bridge, store, content):
    bridge[0].receive(update(40, '/coding_prepare 10'))
    scope = {'allowed_files': ['src/command_center/example.py'], 'test_files': ['tests/test_example.py']}
    bridge[0].receive(update(41, '/coding_prepare 10 '+json.dumps(scope)))
    with store.transaction() as tx:
        assert tx.scalar(select(Audit).where(Audit.event['kind'].as_string() == EVENT)) is None


def test_reply_failure_rolls_back_specification_and_retry_is_safe(bridge, store, content, monkeypatch):
    issue(bridge)
    bridge[0].receive(click(bridge))
    scope = {'allowed_files': ['src/command_center/example.py'], 'test_files': ['tests/test_example.py']}
    command = update(40, '/coding_prepare 10 '+json.dumps(scope))
    with monkeypatch.context() as patch:
        patch.setattr(bridge[0], 'finish', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('public rollback')))
        with pytest.raises(RuntimeError):
            bridge[0].receive(command)
    with store.transaction() as tx:
        assert tx.scalar(select(Audit).where(Audit.event['kind'].as_string() == EVENT)) is None
    bridge[0].receive(command)
    with store.transaction() as tx:
        assert len(list(tx.scalars(select(Audit).where(Audit.event['kind'].as_string() == EVENT)))) == 1


def test_pending_command_cannot_silently_switch_to_a_new_acceptance(bridge, store, content, monkeypatch):
    from command_center.plan_acceptance import accept
    from command_center.request_planning import context
    from test_plan_acceptance import body
    from test_request_plan_store import persist
    from test_request_planning import response
    issue(bridge)
    bridge[0].receive(click(bridge))
    scope = {'allowed_files': ['src/command_center/example.py'], 'test_files': ['tests/test_example.py']}
    with monkeypatch.context() as patch:
        patch.setattr(bridge[0], '_apply_pending', lambda *a: None)
        bridge[0].receive(update(40, '/coding_prepare 10 '+json.dumps(scope)))
    snapshot = context(store, 'owner', content)
    data = response(snapshot)
    data['id'] = 'resp_public_new_plan'
    persist(store, snapshot, data)
    latest = accept(store, 'owner', body(store, content))
    bridge[0].resume_pending()
    with store.transaction() as tx:
        assert tx.scalar(select(Audit).where(Audit.event['kind'].as_string() == EVENT)) is None
    bridge[0].receive(update(41, '/coding_prepare 10 '+json.dumps(scope)))
    with store.transaction() as tx:
        row = tx.scalar(select(Audit).where(Audit.event['kind'].as_string() == EVENT))
        assert row.event['specification']['acceptance_digest'] == latest['snapshot_digest']


@pytest.mark.parametrize('command', ['/coding_prepare', '/coding_prepare -1', '/coding_prepare 9007199254740992',
    '/coding_prepare 10 {"allowed_files":[],"test_files":[]}',
    '/coding_prepare 10 {"allowed_files":[],"allowed_files":["tests/test_x.py"]}',
    '/coding_prepare 10 {"provider":"openai"}', '/coding_prepare 10 [1,2]'])
def test_invalid_scope_has_fixed_error_without_input_echo(command):
    with pytest.raises(Denied) as caught:
        parse(command)
    assert str(caught.value) in {'coding_preparation_command_invalid', 'coding_preparation_scope_invalid'}
