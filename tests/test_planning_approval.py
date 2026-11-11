"""Reviewed F1 approval on isolated PG; no live provider or Telegram callback."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from command_center.coding.gateway import Gateway
from command_center.coding.integration_config import FileCredentials
from command_center.models import Approval, Audit, Control, ExternalAction, ExternalGrant, Outbox
from command_center.planning_admission import PlanningProfile
from command_center.planning_approval import CONFIRMATION, PlanningApproval
from command_center.planning_task import create_task, payload
from command_center.project_inbox import classify
from command_center.request_planning import context
from command_center.store import Denied, digest
from command_center.runtime_broker import RuntimeBroker
from test_project_inbox import capture


@pytest.fixture
def reviewed(store):
    rid = capture(store)
    classify(store, 'owner', rid, 'command-center', 0, str(uuid4()))
    snapshot = context(store, 'owner', rid)
    task = create_task(store, 'owner', snapshot)
    with store.transaction() as session:
        now = int(store.now(session).timestamp())
    profile = PlanningProfile.model_validate({
        'tariff': {'model': 'SYNTHETIC-model', 'input_nano_rub': 1, 'output_nano_rub': 2,
            'context_tokens': 8192, 'max_output_tokens': 32, 'confirmed': True, 'evidence': 'SYNTHETIC'},
        'evidence': {'account': 'SYNTHETIC', 'model': 'SYNTHETIC', 'funding': 'SYNTHETIC',
            'data_sharing': 'SYNTHETIC', 'observed_at': now - 10, 'expires_at': now + 900},
        'available_nano_rub': 1_000_000, 'daily_nano_rub': 1_000_000, 'monthly_nano_rub': 1_000_000})
    service = PlanningApproval(store, profile)
    return service, service.prepare('owner', task['id'], task['version']), snapshot


def authorize(service, quote, **changes):
    args = {'expected_quote_digest': digest(quote.model_dump()), 'confirmation': CONFIRMATION}
    args.update(changes)
    return service.authorize('owner', quote, **args)


def state(store):
    with store.transaction() as session:
        return ([r.task_id for r in session.scalars(select(Approval))],
                [r.task_id for r in session.scalars(select(ExternalGrant))],
                [r.task_id for r in session.scalars(select(Outbox))],
                [r.id for r in session.scalars(select(ExternalAction))])


def test_exact_approval_is_atomic_bounded_and_client_free(reviewed, store, monkeypatch):
    service, quote, _ = reviewed
    monkeypatch.setattr(httpx, 'Client', lambda *a, **k: pytest.fail('no HTTP client'))
    monkeypatch.setattr(FileCredentials, 'get', lambda *a: pytest.fail('no credentials'))
    result = authorize(service, quote)
    assert result['authorized'] and not result['provider_called'] and not result['runtime_dispatch_enabled']
    assert state(store) == ([quote.task_id], [quote.task_id], [quote.task_id], [])
    assert store.get(quote.task_id)['state'] == 'READY'
    with store.transaction() as session:
        approval = session.get(Approval, quote.task_id)
        assert int(approval.expires_at.timestamp()) == quote.expires_at
        assert not approval.used
        grant = session.get(ExternalGrant, quote.task_id)
        assert grant.digest == digest(grant.document)
        assert grant.document['scope'] == service.profile.purpose
        assert grant.document['review'] == quote.model_dump()
        assert grant.document['secret_refs'] == []
        assert grant.document['max_calls'] == 1 and not grant.document['business_execution']
        assert session.get(Control, 1).reserved == 0  # No money reserved before provider INTENT.


@pytest.mark.parametrize('change', ['digest', 'confirmation', 'profile', 'project', 'halt', 'version'])
def test_changed_scope_rolls_back_every_approval_write(reviewed, store, change):
    service, quote, snapshot = reviewed
    args = {}
    if change == 'digest':
        args['expected_quote_digest'] = 'f' * 64
    elif change == 'confirmation':
        args['confirmation'] = 'AUTHORIZE_SAVED_REQUEST_PLANNING_HTTP_MOCK'
    elif change == 'profile':
        service.profile.tariff.model = 'replacement-model'
    elif change == 'project':
        classify(store, 'owner', snapshot.request_id, 'lnauto', 1, str(uuid4()))
    elif change == 'halt':
        store.halt('owner')
    elif change == 'version':
        quote = quote.model_copy(update={'task_version': 2})
    before = state(store)
    task_before = store.get(quote.task_id)['state']
    with pytest.raises(Denied):
        authorize(service, quote, **args)
    assert state(store) == before
    assert store.get(quote.task_id)['state'] == task_before


def test_replay_and_concurrent_confirmations_create_only_one_grant(reviewed, store):
    service, quote, _ = reviewed
    def attempt(_):
        try:
            authorize(service, quote)
            return True
        except Denied:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == [False, True]
    assert state(store) == ([quote.task_id], [quote.task_id], [quote.task_id], [])


def test_final_hook_failure_rolls_back_task_approval_outbox_and_grant(reviewed, store, monkeypatch):
    service, quote, _ = reviewed
    original = store.audit
    def failing(session, kind, *args, **kwargs):
        original(session, kind, *args, **kwargs)
        if kind == 'external_scope_approved':
            raise Denied('synthetic_commit_failure')
    monkeypatch.setattr(store, 'audit', failing)
    with pytest.raises(Denied, match='synthetic_commit_failure'):
        authorize(service, quote)
    assert state(store) == ([], [], [], [])
    assert store.get(quote.task_id)['state'] == 'WAITING_APPROVAL'


@pytest.mark.parametrize('actor', ['operator', 'agent', 'gateway'])
def test_owner_required_for_both_boundaries(reviewed, actor):
    service, quote, _ = reviewed
    with pytest.raises(Denied):
        service.prepare(actor, quote.task_id, quote.task_version)
    with pytest.raises(Denied):
        service.authorize(actor, quote, expected_quote_digest=digest(quote.model_dump()), confirmation=CONFIRMATION)


def add_action(store, task_id, *, reserved=0, actual=0, state='COMPLETE', anchored=True):
    with store.transaction() as session:
        now = store.now(session)
        row = ExternalAction(id=str(uuid4()), task_id=task_id, key=str(uuid4()), kind='openai',
            request_hash='a' * 64, state=state, reserved=reserved, actual=actual,
            created_at=now, evidence={'settled_day': now.strftime('%Y-%m-%d'),
                                     'settled_month': now.strftime('%Y-%m')})
        session.add(row)
        session.flush()
        if anchored:
            store.audit(session, 'synthetic_ledger_fixture', 'owner', task_id,
                        action_id=row.id, ledger_digest=Gateway.action_digest(row))


@pytest.mark.parametrize('state_name', ['INTENT', 'UNCERTAIN', 'SETTLED'])
def test_prior_unknown_outcome_cannot_be_reapproved(reviewed, store, state_name):
    service, quote, _ = reviewed
    add_action(store, quote.task_id, reserved=100, state=state_name)
    with pytest.raises(Denied, match='planning_request_outcome_unresolved'):
        authorize(service, quote)
    assert state(store)[:3] == ([], [], [])


@pytest.mark.parametrize('limit', ['daily_nano_rub', 'monthly_nano_rub', 'available_nano_rub'])
def test_existing_global_ledger_consumption_is_counted(reviewed, store, limit):
    service, _, snapshot = reviewed
    other = store.create('owner', 'other-task', {'kind': 'render', 'cost': 0, 'text': 'SYNTHETIC'})
    add_action(store, other['id'], actual=4000)
    values = service.profile.model_dump()
    values[limit] = 10000  # Tariff maximum 8256 fits alone, but not with existing spend.
    service.profile = PlanningProfile.model_validate(values)
    task = create_task(store, 'owner', snapshot)
    quote = service.prepare('owner', task['id'], task['version'])
    with pytest.raises(Denied, match='external_budget_limit|planning_funding_limit'):
        authorize(service, quote)
    assert state(store)[:3] == ([], [], [other['id']])


def test_tampered_ledger_cannot_issue_grant(reviewed, store):
    service, quote, _ = reviewed
    add_action(store, quote.task_id, actual=1, anchored=False)
    with pytest.raises(Denied, match='external_ledger_integrity_failure'):
        authorize(service, quote)
    assert state(store)[:3] == ([], [], [])


def test_quote_expiry_during_hook_rolls_back(reviewed, store, monkeypatch):
    service, quote, _ = reviewed
    original = store.now
    def delayed(session):
        count = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == 'external_scope_approved'))
        return original(session) + (timedelta(seconds=121) if count else timedelta())
    monkeypatch.setattr(store, 'now', delayed)
    with pytest.raises(Denied):
        authorize(service, quote)
    assert state(store) == ([], [], [], [])


def test_review_mutation_cannot_change_the_reservation(reviewed, store):
    service, quote, _ = reviewed
    changed = deepcopy(quote).model_copy(update={'maximum_nano_rub': 1})
    with pytest.raises(Denied):
        authorize(service, changed)
    assert state(store) == ([], [], [], [])


def test_expired_quote_is_not_extended_by_approval(reviewed, store, monkeypatch):
    service, quote, _ = reviewed
    original = store.now
    monkeypatch.setattr(store, 'now', lambda session: original(session) + timedelta(seconds=121))
    with pytest.raises(Denied):
        authorize(service, quote)
    assert state(store) == ([], [], [], [])


def test_profile_mutation_during_commit_rolls_back(reviewed, store, monkeypatch):
    service, quote, _ = reviewed
    original = store.audit
    def changed(session, kind, *args, **kwargs):
        original(session, kind, *args, **kwargs)
        if kind == 'external_scope_approved':
            service.profile.tariff.model = 'changed-during-commit'
    monkeypatch.setattr(store, 'audit', changed)
    with pytest.raises(Denied):
        authorize(service, quote)
    assert state(store) == ([], [], [], [])


def test_live_scoped_grant_does_not_enable_production_dispatch(reviewed, store):
    service, quote, _ = reviewed
    authorize(service, quote)
    class Ledger:
        def verify(self):
            pass
        def watchdog_ready(self, *args):
            pytest.fail('must reject before runtime admission')
    class Backend:
        def preflight(self):
            pytest.fail('must not access runtime engine')
    broker = RuntimeBroker(store, Ledger(), Backend())
    try:
        with pytest.raises(Denied, match='planning_runtime_not_connected'):
            broker.submit(quote.task_id, store.settings.source_revision)
    finally:
        broker.pool.shutdown(wait=True)
    assert store.get(quote.task_id)['state'] == 'READY'
    with store.transaction() as session:
        assert not session.get(Approval, quote.task_id).used
        assert session.scalar(select(ExternalAction)) is None


def test_other_creation_key_cannot_reauthorize_same_context(reviewed, store):
    service, quote, snapshot = reviewed
    authorize(service, quote)
    other = store.create('owner', 'alternate-planning-key', payload(snapshot))
    duplicate = service.prepare('owner', other['id'], other['version'])
    with pytest.raises(Denied, match='planning_context_already_bound'):
        authorize(service, duplicate)
    assert store.get(other['id'])['state'] == 'WAITING_APPROVAL'
    assert state(store)[:3] == ([quote.task_id], [quote.task_id], [quote.task_id])


def test_changed_context_cannot_retry_previous_uncertain_request(reviewed, store):
    service, quote, snapshot = reviewed
    add_action(store, quote.task_id, reserved=100, state='UNCERTAIN')
    classify(store, 'owner', snapshot.request_id, None, 1, str(uuid4()))
    classify(store, 'owner', snapshot.request_id, 'command-center', 2, str(uuid4()))
    current = context(store, 'owner', snapshot.request_id)
    task = create_task(store, 'owner', current)
    new_quote = service.prepare('owner', task['id'], task['version'])
    with pytest.raises(Denied, match='planning_request_outcome_unresolved'):
        authorize(service, new_quote)
    assert state(store)[:3] == ([], [], [])
