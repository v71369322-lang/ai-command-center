from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from threading import Event
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, text

from command_center.coding.contract import CodingRequest, payload
from command_center.coding.gateway import Gateway, Uncertain
from command_center.coding.http_contract import GatewayProvider
from command_center.coding.integration_config import IntegrationConfig
from command_center.coding.spec import BASE_SHA, INITIAL, OBJECTIVE, REPOSITORY, TEST_SOURCE
from command_center.models import ExternalAction
from command_center.runtime_broker import RuntimeBroker
from command_center.runtime_ledger import RuntimeLedger
from command_center.runtime_policy import RuntimeBackend, RuntimeLimits
from command_center.store import Denied

from f2_http_support import Credentials, FakeHTTP, config


def context(attempt=1):
    return {'repository': REPOSITORY, 'objective': OBJECTIVE, 'base_sha': BASE_SHA,
            'source': INITIAL, 'acceptance': TEST_SOURCE, 'checks': None, 'attempt': attempt}


def setup(store, *, backend=None, conf=None, budget=1_000_000, credentials=None):
    backend = backend or FakeHTTP()
    gateway = Gateway(store, conf or config(), transport=httpx.MockTransport(backend.handle),
                      credentials=credentials or Credentials())
    task = store.create('owner', str(uuid4()), payload(CodingRequest(provider='openai')))
    gateway.authorize('owner', task['id'], task['version'], budget_nano_rub=budget)
    task = store.claim(task['id'])
    return gateway, task, backend


def send(gateway, task, attempt=1):
    return GatewayProvider(gateway, task).propose(context(attempt))


def test_default_closed_and_no_mock_transport_escape(store):
    gateway = Gateway(store)
    with pytest.raises(Denied, match='not_connected'):
        gateway.request(str(uuid4()), 1, 'x', 'openai', 'POST', '/v1/responses', {})
    gateway.close()
    with pytest.raises(Denied, match='mock_transport_required'):
        Gateway(store, config())
    with pytest.raises(ValueError):
        IntegrationConfig(synthetic_repository='v71369322-lang/ai-command-center')


def test_http_response_contract_usage_and_no_resend(store):
    g, task, fake = setup(store)
    assert send(g, task).changes['calculator.py'].startswith('def sum_positive')
    # Same immutable logical request returns durable evidence without a second HTTP call.
    assert send(g, task).tokens == 132 and fake.ai_calls == 1
    status = g.status(task['id'])
    assert status['actual_nano_rub'] == 1640 and status['uncertain_nano_rub'] == 0
    assert status['actions'][0]['request_id'] == 'fixture-request-id'
    with store.transaction() as s:
        row = s.execute(select(ExternalAction)).scalar_one()
        assert row.evidence['response_id'] == 'resp_fixture_1'
        assert all(v not in json.dumps(row.evidence) for v in Credentials.values.values())
    g.close()


@pytest.mark.parametrize('case', ['missing_key', 'no_tariff', 'unconfirmed', 'budget', 'fence', 'scope', 'model'])
def test_financial_and_scope_fail_closed(store, case):
    g, task, fake = setup(store, budget=100 if case == 'budget' else 1_000_000)
    if case == 'missing_key':
        g.credentials = Credentials()
        g.credentials.values = {}
    elif case in {'no_tariff', 'unconfirmed'}:
        g.config = config(tariff=None) if case == 'no_tariff' else config(tariff=config().tariff.model_copy(update={'confirmed': False}))
    elif case == 'fence':
        task['fence'] += 1
    elif case == 'scope':
        g.config = config(synthetic_repository='fixture/acc-f2-synthetic-other')
    elif case == 'model':
        g.config = config(tariff=config().tariff.model_copy(update={'model': 'other-model'}))
    with pytest.raises((Denied, PermissionError)):
        send(g, task)
    assert fake.ai_calls == 0
    g.close()


def test_concurrent_calls_cannot_overreserve(store):
    entered, release = Event(), Event()
    fake = FakeHTTP()
    def block(request):
        if request.url.host == 'api.openai.com':
            entered.set()
            assert release.wait(5)
    fake.before = block
    g, task, _ = setup(store, backend=fake, budget=config().tariff.maximum())
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(send, g, task)
            assert entered.wait(5)
            second = pool.submit(send, g, task, 2)
            with pytest.raises(Denied, match='budget'):
                second.result(timeout=5)
            release.set()
            first.result(timeout=5)
        assert fake.ai_calls == 1
    finally:
        release.set()
        g.close()


@pytest.mark.parametrize('after_response', [False, True])
def test_timeout_restart_retains_money_and_prevents_retry(store, after_response):
    fake = FakeHTTP()
    def timeout(request):
        raise httpx.ReadTimeout('fixture uncertain result')
    if after_response:
        fake.after = timeout
    else:
        fake.before = timeout
    g, task, _ = setup(store, backend=fake)
    with pytest.raises(Uncertain):
        send(g, task)
    expected = config().tariff.maximum()
    assert g.status(task['id'])['uncertain_nano_rub'] == expected
    g.close()
    fresh = Gateway(store, config(), transport=httpx.MockTransport(fake.handle), credentials=Credentials())
    with pytest.raises(Uncertain, match='reconciliation'):
        send(fresh, task)
    assert len(fake.calls) == 1
    with pytest.raises(Denied):
        fresh.reconcile_usage('operator', fresh.status(task['id'])['actions'][0]['id'], 100, 32, 'fixture billing')
    action_id = fresh.status(task['id'])['actions'][0]['id']
    fresh.reconcile_usage('owner', action_id, 100, 32, 'owner-verified fixture billing evidence')
    assert fresh.status(task['id'])['uncertain_nano_rub'] == 0
    with pytest.raises(Uncertain):
        send(fresh, task)  # Settling money does not authorize a second request.
    fresh.close()


@pytest.mark.parametrize('scenario', ['tool_injection', 'scope_injection', 'credential_echo'])
def test_model_output_injection_cannot_expand_permissions(store, scenario):
    g, task, fake = setup(store, backend=FakeHTTP(scenario))
    with pytest.raises((ValueError, Denied)):
        send(g, task)
    assert not fake.prs and fake.ai_calls == 1
    with store.transaction() as s:
        for row in s.execute(select(ExternalAction)).scalars():
            assert all(v not in json.dumps(row.evidence) for v in Credentials.values.values())
    g.close()


@pytest.mark.parametrize('revoke', [False, True])
def test_cancel_or_revoke_during_http_accounts_but_cannot_continue(store, revoke):
    fake = FakeHTTP()
    g, task, _ = setup(store, backend=fake)
    fake.after = lambda request: store.cancel('owner', task['id'], revoke=revoke)
    with pytest.raises(Denied):
        send(g, task)
    assert g.status(task['id'])['actual_nano_rub'] == 1640
    fake.after = None
    with pytest.raises(Denied):
        send(g, task, 2)
    assert fake.ai_calls == 1
    g.close()


def test_revision_audit_and_unknown_endpoint_block_calls(store, admin):
    g, task, fake = setup(store)
    with pytest.raises(Denied):
        g.request(task['id'], task['fence'], 'escape', 'github', 'POST', '/repos/other/CRM/git/refs', {})
    with pytest.raises(Denied):
        g.request(task['id'], task['fence'], 'escape', 'github', 'POST',
                  '/repos/fixture/acc-f2-synthetic-test/git/refs', {'ref': 'refs/heads/main', 'sha': BASE_SHA})
    store.settings = replace(store.settings, source_revision='f' * 40)
    with pytest.raises(Denied):
        send(g, task)
    store.settings = admin.settings
    with admin.engine.begin() as connection:
        connection.execute(text("UPDATE audit SET digest=:bad WHERE sequence=(SELECT max(sequence) FROM audit)"), {'bad': 'f' * 64})
    with pytest.raises(Denied, match='audit'):
        send(g, task)
    assert not fake.calls
    g.close()


def test_real_http_mock_coding_cycle_broker_containers_and_pr(store, tmp_path):
    fake = FakeHTTP()
    def make_gateway():
        return Gateway(store, config(), transport=httpx.MockTransport(fake.handle), credentials=Credentials())
    g = make_gateway()
    task = store.create('owner', str(uuid4()), payload(CodingRequest(provider='openai', max_seconds=30)))
    g.authorize('owner', task['id'], task['version'], budget_nano_rub=1_000_000)
    g.close()
    ledger = RuntimeLedger(tmp_path / 'runtime.sqlite')
    ledger.watchdog()
    service = RuntimeBroker(store, ledger, RuntimeBackend(mode='cloud-rootful-test'), RuntimeLimits(), make_gateway)
    try:
        service.submit(task['id'], store.settings.source_revision)
        service.last_future.result(timeout=35)
        result = store.get(task['id'])
        assert result['state'] == 'SUCCEEDED', result.get('reason')
        assert fake.ai_calls == 2 and len(fake.prs) == 1
        assert result['coding']['pr']['mode'] == 'http_mock'
        assert result['coding']['pr']['published'] is False
        assert [r['checks']['passed'] for r in result['coding']['test_runs']] == [False, True]
        check = make_gateway()
        assert check.status(task['id'])['actual_nano_rub'] == 3280
        check.close()
    finally:
        service.pool.shutdown(wait=True)
