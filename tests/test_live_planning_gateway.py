"""Real F1/PG + live-shaped bindings, but ONLY public credentials and MockTransport."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import json
from threading import Event
from types import SimpleNamespace

import httpx
import pytest

from command_center.coding.gateway import Uncertain
from command_center.live_planning_gateway import LivePlanningGateway, PlanningCredentials
from command_center.models import Approval, Audit, ExternalAction, ExternalGrant, Task
from command_center.planning_admission import PlanningProfile
from command_center.planning_gateway import KEY
from command_center.planning_approval import CONFIRMATION, PlanningApproval
from command_center.request_plan_store import EVENT, read
from command_center.request_planning import context, request_document
from command_center.store import Denied, digest
from test_request_planning import response
from test_telegram_planning_authorize import profile as profile, issue, click, rows
from test_telegram_readiness import bridge as bridge
from test_telegram_service import configured as configured

PUBLIC_KEY = 'PUBLIC_PLANNING_LIVE_SHAPED_KEY_ONLY_12345'


@pytest.fixture
def prepared(profile, store, monkeypatch):
    original, save, path, rid = profile
    key = path.parent / 'public-key'
    key.write_text(PUBLIC_KEY)
    key.chmod(0o600)
    data = original.model_dump()
    data['tariff']['max_output_tokens'] = 2048
    data['runtime'] = {'source_revision': store.settings.source_revision, 'binding_digest': 'f' * 64,
                       'credential_sha256': hashlib.sha256(key.read_bytes()).hexdigest()}
    config = PlanningProfile.model_validate(data)
    save(config)
    monkeypatch.setenv('F1_PLANNING_OPENAI_KEY_FILE', str(key))
    snapshot = context(store, 'owner', rid)
    state = SimpleNamespace(config=config, key=key, save=save, snapshot=snapshot, calls=[],
        after=None, drop=False, status=200, raw=None, ready=True, constructor_calls=0, binding_checks=[])
    state.data = response(snapshot)
    state.data.update(model=config.tariff.model, service_tier='default')

    def handle(request):
        assert str(request.url) == 'https://api.openai.com/v1/responses'
        assert request.headers['Authorization'] == 'Bearer ' + PUBLIC_KEY
        # Prove INTENT/reservation was committed before any mock network I/O.
        action = rows(store, ExternalAction)[0]
        assert action.state == 'INTENT' and action.reserved == config.tariff.maximum()
        state.calls.append(json.loads(request.content))
        if state.after:
            state.after()
        if state.drop:
            raise httpx.ReadTimeout('public synthetic uncertain outcome')
        if state.raw is not None:
            return httpx.Response(state.status, content=state.raw)
        return httpx.Response(state.status, json=state.data, headers={'x-request-id': 'public-plan-call'})

    client = httpx.Client(transport=httpx.MockTransport(handle), trust_env=False)
    def client_factory(**kwargs):
        assert kwargs == {'transport': None, 'follow_redirects': False, 'timeout': 8, 'trust_env': False}
        state.constructor_calls += 1
        return client
    monkeypatch.setattr(httpx, 'Client', client_factory)
    def guard(binding):
        state.binding_checks.append(binding)
        return state.ready and binding == config.runtime.model_dump()
    state.guard = guard
    yield state
    client.close()


@pytest.fixture
def running(prepared, bridge, store):
    issue(bridge)
    bridge[0].receive(click(bridge))
    waiting = rows(store, Task)[0]
    prepared.task = store.claim(waiting.id)
    prepared.gateway = LivePlanningGateway(store, runtime_guard=prepared.guard)
    return prepared


def drafts(store):
    return [row for row in rows(store, Audit) if row.event['kind'] == EVENT]


def perform(state):
    return state.gateway.perform(state.task['id'], state.task['fence'])


def test_bound_review_one_response_shared_ledger_and_only_advisory_draft(running, store):
    receipt = perform(running)
    assert receipt['stored'] and not receipt['execution_authorized']
    assert running.calls == [request_document(running.snapshot, running.config.tariff.model,
        context_tokens=8192, max_output_tokens=2048)]
    assert len(rows(store, ExternalAction)) == len(drafts(store)) == 1
    action = rows(store, ExternalAction)[0]
    assert action.state == 'COMPLETE' and action.actual == 700 and action.reserved == 0
    assert store.get(running.task['id'])['state'] == 'SUCCEEDED'
    assert read(store, 'owner', running.snapshot.request_id)['state'] == 'CURRENT'
    artifact = json.loads(store.get(running.task['id'])['artifact'])
    assert artifact['mode'] == 'live' and artifact['business_execution'] is False
    assert running.binding_checks and all(b == running.config.runtime.model_dump() for b in running.binding_checks)
    status = running.gateway.status(running.task['id'])
    assert status['actual_nano_rub'] == 700 and not status['financial_values_are_mock']
    assert not status['production_dispatch_enabled']
    assert PUBLIC_KEY not in json.dumps([r.event for r in rows(store, Audit)])


@pytest.mark.parametrize('change', ['no_binding', 'wrong_source', 'no_guard'])
def test_constructor_closed_before_client_construction(prepared, store, change):
    config = prepared.config.model_dump()
    if change == 'no_binding':
        config['runtime'] = None
    elif change == 'wrong_source':
        config['runtime']['source_revision'] = 'a' * 40
    prepared.save(PlanningProfile.model_validate(config))
    with pytest.raises(Denied):
        LivePlanningGateway(store, runtime_guard=None if change == 'no_guard' else prepared.guard)
    assert prepared.constructor_calls == 0 and not prepared.calls


def test_default_disabled_and_no_public_transport_override(prepared, store, monkeypatch):
    with pytest.raises(TypeError):
        LivePlanningGateway(store, runtime_guard=prepared.guard, transport=httpx.MockTransport(lambda r: None))
    monkeypatch.delenv('F1_PLANNING_PROFILE_FILE')
    monkeypatch.delenv('F1_PLANNING_PROFILE_SHA256')
    with pytest.raises(Denied):
        LivePlanningGateway(store, runtime_guard=prepared.guard)
    assert prepared.constructor_calls == 0


def test_internal_review_without_observed_telegram_click_cannot_call(prepared, store, monkeypatch):
    task = rows(store, Task)[0]
    service = PlanningApproval(store, prepared.config)
    quote = service.prepare('owner', task.id, task.version)
    service.authorize('owner', quote, expected_quote_digest=digest(quote.model_dump()), confirmation=CONFIRMATION)
    claimed = store.claim(task.id)
    gateway = LivePlanningGateway(store, runtime_guard=prepared.guard)
    monkeypatch.setattr(PlanningCredentials, 'get', lambda *a: pytest.fail('no key without observed click'))
    with pytest.raises(Denied, match='observed_consent_required'):
        gateway.perform(task.id, claimed['fence'])
    assert not prepared.calls and not rows(store, ExternalAction)


def test_old_unbound_permission_cannot_gain_a_key_binding(profile, prepared, bridge, store):
    prepared.save(profile[0])
    issue(bridge)
    bridge[0].receive(click(bridge))
    task = store.claim(rows(store, Task)[0].id)
    assert rows(store, ExternalGrant)[0].document['secret_refs'] == []
    prepared.save(prepared.config)
    gateway = LivePlanningGateway(store, runtime_guard=prepared.guard)
    with pytest.raises(Denied):
        gateway.perform(task['id'], task['fence'])
    assert not prepared.calls and not rows(store, ExternalAction)


@pytest.mark.parametrize('change', ['fence', 'revoked', 'runtime', 'profile', 'expiry', 'context'])
def test_lost_authority_prevents_even_provider_key_read(running, store, monkeypatch, change):
    if change == 'fence':
        running.task['fence'] += 1
    elif change == 'revoked':
        store.cancel('owner', running.task['id'], revoke=True)
    elif change == 'runtime':
        running.ready = False
    elif change == 'profile':
        data = running.config.model_dump()
        data['runtime']['binding_digest'] = 'e' * 64
        running.save(PlanningProfile.model_validate(data))
    elif change == 'expiry':
        now = store.now
        monkeypatch.setattr(store, 'now', lambda session: now(session) + timedelta(seconds=121))
    else:
        from command_center.project_inbox import classify
        from uuid import uuid4
        classify(store, 'owner', running.snapshot.request_id, 'lnauto', 1, str(uuid4()))
    monkeypatch.setattr(PlanningCredentials, 'get', lambda *a: pytest.fail('no key read without authority'))
    with pytest.raises(Denied):
        perform(running)
    assert not running.calls and not rows(store, ExternalAction)


@pytest.mark.parametrize('change', ['endpoint', 'key', 'query', 'reconcile', 'body'])
def test_only_one_exact_request_document_is_allowed(running, store, monkeypatch, change):
    body = request_document(running.snapshot, running.config.tariff.model, context_tokens=8192, max_output_tokens=2048)
    args = [running.task['id'], running.task['fence'], KEY, 'openai', 'POST', '/v1/responses', body]
    kwargs = {}
    if change == 'endpoint':
        args[5] = '/v1/models'
    elif change == 'key':
        args[2] = 'planning/v2'
    elif change == 'query':
        kwargs['query'] = {}
    elif change == 'reconcile':
        kwargs['reconcile'] = True
    else:
        body['tools'] = []
    monkeypatch.setattr(PlanningCredentials, 'get', lambda *a: pytest.fail('no key read for changed request'))
    with pytest.raises(Denied):
        running.gateway.request(*args, **kwargs)
    assert not running.calls and not rows(store, ExternalAction)


@pytest.mark.parametrize('change', ['missing', 'changed', 'permissions', 'symlink'])
def test_invalid_private_key_binding_stops_before_intent(running, store, change):
    if change == 'missing':
        running.key.unlink()
    elif change == 'changed':
        running.key.write_text('ANOTHER_PUBLIC_SYNTHETIC_CREDENTIAL_12345')
    elif change == 'permissions':
        running.key.chmod(0o644)
    else:
        target = running.key.with_name('public-target')
        running.key.rename(target)
        running.key.symlink_to(target)
    with pytest.raises(Denied, match='credential_binding'):
        perform(running)
    assert not running.calls and not rows(store, ExternalAction)


@pytest.mark.parametrize('change', ['runtime', 'key', 'revocation'])
def test_final_admission_after_durable_intent_blocks_network(running, store, monkeypatch, change):
    original = store.audit
    def alter(session, kind, *args, **kwargs):
        result = original(session, kind, *args, **kwargs)
        if kind == 'external_ledger_anchor':
            if change == 'runtime':
                running.ready = False
            elif change == 'key':
                running.key.write_text('DIFFERENT_PUBLIC_SYNTHETIC_KEY_12345')
            else:
                session.get(Approval, running.task['id']).revoked = True
        return result
    monkeypatch.setattr(store, 'audit', alter)
    with pytest.raises(Denied):
        perform(running)
    assert not running.calls and not drafts(store)
    action = rows(store, ExternalAction)[0]
    assert action.state == 'UNCERTAIN' and action.reserved == running.config.tariff.maximum()


def test_unknown_outcome_preserves_reserve_and_never_retries(running, store):
    running.drop = True
    for _ in range(2):
        with pytest.raises(Uncertain):
            perform(running)
    assert len(running.calls) == 1 and not drafts(store)
    action = rows(store, ExternalAction)[0]
    assert action.state == 'UNCERTAIN' and action.reserved == running.config.tariff.maximum()


@pytest.mark.parametrize('invalid', ['tier', 'missing_tier', 'incomplete', 'usage', 'duplicate_json',
                                   'credential_echo', 'escaped_credential_echo'])
def test_unaccountable_response_retains_unknown_reserve(running, store, invalid):
    if invalid == 'tier':
        running.data['service_tier'] = 'priority'
    elif invalid == 'missing_tier':
        running.data.pop('service_tier')
    elif invalid == 'incomplete':
        running.data['status'] = 'incomplete'
    elif invalid == 'usage':
        running.data['usage']['total_tokens'] += 1
    elif invalid == 'duplicate_json':
        running.raw = json.dumps(running.data)[:-1].encode() + b',"model":"duplicate"}'
    elif invalid == 'escaped_credential_echo':
        escaped = ''.join('\\u%04x' % ord(c) for c in PUBLIC_KEY)
        running.raw = ('{"message":"' + escaped + '"}').encode()
    else:
        running.raw = PUBLIC_KEY.encode()
    with pytest.raises(Uncertain):
        perform(running)
    action = rows(store, ExternalAction)[0]
    assert action.state == 'UNCERTAIN' and action.reserved > 0 and action.actual == 0
    assert len(running.calls) == 1 and not drafts(store)


def test_revocation_during_io_preserves_billing_but_rejects_draft(running, store):
    running.after = lambda: store.cancel('owner', running.task['id'], revoke=True)
    with pytest.raises(Denied):
        perform(running)
    assert rows(store, ExternalAction)[0].actual == 700 and not drafts(store)
    assert len(running.calls) == 1


def test_tariff_change_during_io_does_not_reprice_completed_call(running, store):
    def change():
        data = running.config.model_dump()
        data['tariff']['input_nano_rub'] = 10
        running.save(PlanningProfile.model_validate(data))
    running.after = change
    with pytest.raises(Denied):
        perform(running)
    assert rows(store, ExternalAction)[0].actual == 700 and not drafts(store)


@pytest.mark.parametrize('escaped', [False, True])
def test_known_secret_echo_never_enters_external_evidence(running, store, escaped):
    secret = store.settings.redis_password
    running.raw = (('{"model":"' + ''.join('\\u%04x' % ord(c) for c in secret) + '"}').encode()
                   if escaped else json.dumps({'model': secret}).encode())
    with pytest.raises(Denied):
        perform(running)
    action = rows(store, ExternalAction)[0]
    assert action.state == 'UNCERTAIN' and 'response' not in action.evidence
    assert secret not in json.dumps(action.evidence)


def test_budget_is_rechecked_against_spend_after_approval(running, store):
    from test_planning_approval import add_action
    other = store.create('owner', 'other-live-task', {'kind': 'render', 'cost': 0})
    add_action(store, other['id'], actual=990000)
    with pytest.raises(Denied, match='external_budget_limit'):
        perform(running)
    assert not running.calls and len(rows(store, ExternalAction)) == 1


def test_bad_plan_preserves_billed_response_without_second_call(running, store):
    running.data['output'] = [{'type': 'function_call', 'name': 'run_code'}]
    for _ in range(2):
        with pytest.raises(Denied, match='planning_response_invalid'):
            perform(running)
    assert len(running.calls) == 1 and rows(store, ExternalAction)[0].actual == 700 and not drafts(store)


def test_atomic_finalization_retry_uses_complete_response_without_http(running, store, monkeypatch):
    original = store.audit
    def fail(session, kind, *args, **kwargs):
        result = original(session, kind, *args, **kwargs)
        if kind == 'planning_proposal_bound':
            raise Denied('synthetic_finalization_failure')
        return result
    monkeypatch.setattr(store, 'audit', fail)
    with pytest.raises(Denied):
        perform(running)
    assert not drafts(store) and store.get(running.task['id'])['state'] == 'RUNNING'
    assert rows(store, ExternalAction)[0].actual == 700
    monkeypatch.setattr(store, 'audit', original)
    assert perform(running)['stored']
    assert len(running.calls) == len(drafts(store)) == 1


def test_runtime_loss_during_result_writes_rolls_back_draft(running, store, monkeypatch):
    original = store.audit
    def change(session, kind, *args, **kwargs):
        result = original(session, kind, *args, **kwargs)
        if kind == 'planning_proposal_bound':
            running.ready = False
        return result
    monkeypatch.setattr(store, 'audit', change)
    with pytest.raises(Denied):
        perform(running)
    assert not drafts(store) and store.get(running.task['id'])['state'] == 'RUNNING'
    assert rows(store, ExternalAction)[0].actual == 700


def test_concurrent_attempt_cannot_duplicate_an_inflight_call(running, store):
    entered, release = Event(), Event()
    def pause():
        entered.set()
        assert release.wait(10)
    running.after = pause
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(perform, running)
        assert entered.wait(10)
        try:
            with pytest.raises(Uncertain):
                perform(running)
        finally:
            release.set()
        assert future.result()['stored']
    assert len(running.calls) == len(drafts(store)) == 1
