from datetime import datetime, timezone
from decimal import Decimal
from threading import Event, Thread
from uuid import uuid4

import httpx
import pytest

from command_center.api import create_app
from command_center.coding.contract import CodingRequest, payload
from command_center.coding.first_experiment import (CAP, EXPERIMENT_ID, MODEL, REQUIRED,
    Evidence, FirstExperiment, quote, validate_repository)
from command_center.coding.gateway import Gateway
from command_center.coding.integration_config import Tariff
from command_center.coding.spec import BASE_SHA
from command_center.models import ExternalGrant
from command_center.runtime_broker import RuntimeBroker
from command_center.runtime_ledger import RuntimeLedger
from command_center.runtime_policy import RuntimeBackend, RuntimeLimits
from command_center.store import Denied, digest

from f2_http_support import Credentials, FakeHTTP, config

NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


def experiment_config(*, live=False, missing=None):
    evidence = {key: Evidence(reference='fixture operator preflight, NOT live evidence',
                              expires_at='2026-10-25T00:00:00Z') for key in REQUIRED}
    if missing:
        evidence.pop(missing)
    plan = FirstExperiment(payment_rub_per_usd_upper='90', extra_rub_upper='0',
                           existing_credit_usd='1', repository_id=725000001, evidence=evidence)
    return config(mode='live' if live else 'http_mock', live_authorized=live,
                  first_experiment=plan, daily_nano_rub=CAP, monthly_nano_rub=CAP,
                  credential_files={'openai': '/fixture/not-connected-openai',
                                    'github-installation-token': '/fixture/not-connected-github'},
                  budget_evidence='fixture only, not actual payment authorization',
                  tariff=Tariff(model=MODEL, input_nano_rub=67500, output_nano_rub=405000,
                                context_tokens=400000, max_output_tokens=2048,
                                confirmed=True, evidence='fixture upper bound, not a verified bank quote'))


def test_exact_reference_quote_and_no_hard_cap_claim():
    q = quote()
    assert q['max_usd'] == '0.618432'
    assert q['max_rub'] == '49.8073382592'
    assert q['max_nano_rub'] == 49807338260  # Round up, never down.
    assert q['is_provider_hard_cap'] is False
    assert not quote('200')['within_100_rub']
    assert not quote('80.5381', '51')['within_100_rub']
    assert Decimal('5') * Decimal('80.5381') > Decimal(100)  # No prepaid purchase under this grant.


@pytest.mark.parametrize('missing', REQUIRED)
def test_every_precondition_blocks_live_even_with_final_keyword(missing):
    c = experiment_config(live=True, missing=missing)
    task = CodingRequest(provider='openai', experiment_id=EXPERIMENT_ID).model_dump()
    with pytest.raises(Denied, match='preconditions'):
        c.first_experiment.validate_scope(c, task, CAP, NOW, final_confirmation=True)


def test_final_permission_is_separate_and_exact():
    c = experiment_config(live=True)
    task = CodingRequest(provider='openai', experiment_id=EXPERIMENT_ID).model_dump()
    with pytest.raises(Denied, match='final_confirmation'):
        c.first_experiment.validate_scope(c, task, CAP, NOW)
    c.first_experiment.validate_scope(c, task, CAP, NOW, final_confirmation=True)
    for patch in [{'max_iterations': 3}, {'max_units': 3}, {'experiment_id': None}]:
        with pytest.raises(Denied):
            c.first_experiment.validate_scope(c, {**task, **patch}, CAP, NOW, final_confirmation=True)
    with pytest.raises(Denied):
        c.first_experiment.validate_scope(c, task, CAP + 1, NOW, final_confirmation=True)


def test_stale_evidence_bad_payment_and_insufficient_funding_block():
    for patch in [{'payment_rub_per_usd_upper': 'NaN'}, {'payment_rub_per_usd_upper': 'bad'},
                  {'payment_rub_per_usd_upper': '200'}, {'existing_credit_usd': '0'},
                  {'extra_rub_upper': '100'}, {'repository_id': None}]:
        p = experiment_config().first_experiment.model_copy(update=patch)
        assert not p.report(NOW)['ready_for_final_confirmation']
    c = experiment_config(live=True)
    later = datetime(2026, 10, 26, tzinfo=timezone.utc)
    assert not c.first_experiment.report(later)['ready_for_final_confirmation']


@pytest.mark.parametrize('bad', ['id', 'protected', 'base', 'admin'])
def test_repository_id_and_main_protection_are_required(bad):
    repo = {'id': 725000001, 'full_name': 'fixture/acc-f2-synthetic-test',
            'archived': False, 'disabled': False,
            'permissions': {'admin': False, 'push': True}}
    branch = {'name': 'main', 'protected': True, 'commit': {'sha': BASE_SHA}}
    validate_repository(repo, branch, 'fixture/acc-f2-synthetic-test', 725000001)
    if bad == 'id':
        repo['id'] = 1
    elif bad == 'protected':
        branch['protected'] = False
    elif bad == 'base':
        branch['commit']['sha'] = '0' * 40
    else:
        repo['permissions']['admin'] = True
    with pytest.raises(Denied, match='repository_preflight'):
        validate_repository(repo, branch, 'fixture/acc-f2-synthetic-test', 725000001)


def test_preparation_api_never_authorizes_live_and_repeated_taps_same_task(client, headers):
    before = client.get('/api/experiments/first', headers=headers['owner']).json()
    assert before['live_started'] is False and not before['ready_for_final_confirmation']
    assert before['repository_id'] is None and before['mode'] == 'disabled'
    first = client.post('/api/experiments/first/task', headers=headers['owner'])
    again = client.post('/api/experiments/first/task', headers=headers['owner'])
    assert first.json()['id'] == again.json()['id'] and first.json()['state'] == 'WAITING_APPROVAL'
    task = first.json()
    for confirmation in [None, 'PRELIMINARY_BUDGET_ONLY']:
        data = {'version': task['version'], 'profile_hash': before['profile_hash']}
        if confirmation:
            data['confirmation'] = confirmation
        assert client.post('/api/experiments/first/' + task['id'] + '/authorize',
                           json=data, headers=headers['owner']).status_code == 422
    assert client.post('/api/experiments/first/' + task['id'] + '/authorize',
                       json={'version': task['version'], 'profile_hash': before['profile_hash'],
                             'confirmation': 'AUTHORIZE_FIRST_PAID_EXPERIMENT'},
                       headers=headers['owner']).status_code == 409
    assert client.post('/api/experiments/first/task', headers=headers['agent']).status_code == 409


def test_experiment_binding_cannot_be_reused_for_second_task(store):
    c, fake = experiment_config(), FakeHTTP(model=MODEL)
    g = Gateway(store, c, transport=httpx.MockTransport(fake.handle), credentials=Credentials())
    one = store.create('owner', str(uuid4()), payload(CodingRequest(provider='openai', experiment_id=EXPERIMENT_ID)))
    g.authorize('owner', one['id'], one['version'], budget_nano_rub=CAP)
    two = store.create('owner', str(uuid4()), payload(CodingRequest(provider='openai', experiment_id=EXPERIMENT_ID)))
    with pytest.raises(Denied, match='already_bound'):
        g.authorize('owner', two['id'], two['version'], budget_nano_rub=CAP)
    assert store.get(two['id'])['state'] == 'WAITING_APPROVAL' and not fake.calls
    g.close()


def test_live_authorization_needs_exact_final_permission_and_profile(store, monkeypatch):
    c = experiment_config(live=True)
    g = Gateway(store, c)
    monkeypatch.setattr(store, 'now', lambda s: NOW)
    def no_network(*args, **kwargs):
        raise AssertionError('live I/O forbidden in preparation tests')
    monkeypatch.setattr(g.client, 'stream', no_network)
    task = store.create('owner', str(uuid4()), payload(CodingRequest(provider='openai', experiment_id=EXPERIMENT_ID)))
    with pytest.raises(Denied, match='final_confirmation'):
        g.authorize('owner', task['id'], task['version'], budget_nano_rub=CAP)
    with pytest.raises(Denied, match='profile_changed'):
        g.authorize('owner', task['id'], task['version'], budget_nano_rub=CAP,
                    final_confirmation=True, expected_config_hash='0' * 64)
    assert store.get(task['id'])['state'] == 'WAITING_APPROVAL'
    g.authorize('owner', task['id'], task['version'], budget_nano_rub=CAP,
                final_confirmation=True, expected_config_hash=digest(c.model_dump()))
    with store.transaction() as s:
        assert s.get(ExternalGrant, task['id']).document['final_confirmation'] is True
    g.close()


@pytest.mark.parametrize('scenario', ['normal', 'wrong_repo', 'lost_response'])
def test_first_experiment_dry_run_real_sandboxes(store, settings, headers, tmp_path, scenario):
    from fastapi.testclient import TestClient
    c, fake = experiment_config(), FakeHTTP(model=MODEL)
    if scenario == 'wrong_repo':
        fake.repository_id = 1
    if scenario == 'lost_response':
        def timeout(request):
            if request.url.host == 'api.openai.com':
                raise httpx.ReadTimeout('fixture response lost')
        fake.after = timeout
    def gateway():
        return Gateway(store, c, transport=httpx.MockTransport(fake.handle), credentials=Credentials())
    with TestClient(create_app(settings, gateway_factory=gateway)) as client:
        task = client.post('/api/experiments/first/task', headers=headers['owner']).json()
        prepared = client.get('/api/experiments/first', headers=headers['owner']).json()
        answer = client.post('/api/experiments/first/' + task['id'] + '/authorize', headers=headers['owner'],
                             json={'version': task['version'], 'profile_hash': prepared['profile_hash'],
                                   'confirmation': 'AUTHORIZE_FIRST_PAID_EXPERIMENT'})
        assert answer.status_code == 200 and fake.ai_calls == 0
        ledger = RuntimeLedger(tmp_path / 'first.sqlite')
        ledger.watchdog()
        stop = Event()
        def heartbeat():
            while not stop.wait(.5):
                ledger.watchdog()
        monitor = Thread(target=heartbeat, daemon=True)
        monitor.start()
        service = RuntimeBroker(store, ledger, RuntimeBackend(mode='cloud-rootful-test'), RuntimeLimits(), gateway)
        try:
            service.submit(task['id'], settings.source_revision)
            service.last_future.result(timeout=35)
            result = store.get(task['id'])
            g = gateway()
            status = g.status(task['id'])
            if scenario == 'normal':
                assert result['state'] == 'SUCCEEDED', result['coding'].get('failure')
                assert [r['checks']['passed'] for r in result['coding']['test_runs']] == [False, True]
                assert fake.ai_calls == 2 and len(fake.prs) == 1
                assert result['coding']['pr']['published'] is False and result['coding']['pr']['mode'] == 'http_mock'
                assert status['actual_nano_rub'] < CAP and status['uncertain_nano_rub'] == 0
                with store.transaction() as s:
                    grant = s.get(ExternalGrant, task['id'])
                    assert grant.document['repository_id'] == 725000001
                assert all(v not in str(result) for v in Credentials.values.values())
                from pathlib import Path
                import json
                Path('.runtime/f22-dry-run.json').write_text(json.dumps({
                    'revision': settings.source_revision, 'mode': 'http_mock', 'paid_calls': 0,
                    'real_publications': 0, 'http_model_calls': fake.ai_calls, 'task_id': task['id'],
                    'tests': result['coding']['test_runs'], 'budget': status['budget_nano_rub'],
                    'hypothetical_actual_nano_rub': status['actual_nano_rub'], 'unknown': status['uncertain_nano_rub'],
                    'published': False}, indent=2)+'\n')
            elif scenario == 'wrong_repo':
                assert result['state'] == 'FAILED' and fake.ai_calls == 0 and not fake.prs
                assert result['coding']['failure'] == 'first_experiment_repository_preflight'
            else:
                assert result['state'] == 'RECONCILING' and status['uncertain_nano_rub'] == c.tariff.maximum()
                assert fake.ai_calls == 1 and not fake.prs
                with pytest.raises(Denied):
                    service.submit(task['id'], settings.source_revision)
            # Read the actual pipeline's persisted outcome through the new owner
            # view; this must not recontact the provider or publish anything.
            from command_center.telegram_bridge import MockTelegramHTTP, TelegramBridge
            from test_telegram_bridge import BotHTTP, OWNER, message
            bot = BotHTTP()
            telegram_client = MockTelegramHTTP(httpx.MockTransport(bot))
            calls_before = len(fake.calls)
            try:
                bridge = TelegramBridge(store, telegram_client, OWNER)
                bridge.receive(message(901, '/experiment'))
                assert bridge.deliver_one()['state'] == 'SENT'
                body = bot.sent[-1]['text']
                assert task['id'] in body and 'HTTP-моки; настоящего AI нет' in body
                if scenario == 'normal':
                    assert 'Результат независимо проверен в HTTP-моках' in body
                    assert 'реальный PR не опубликован' in body
                elif scenario == 'lost_response':
                    assert 'Внешняя операция не сверена' in body
                assert len(fake.calls) == calls_before and 'Зафиксирован Draft PR:' not in body
            finally:
                telegram_client.close()
            g.close()
        finally:
            service.pool.shutdown(wait=True)
            stop.set()
            monitor.join(timeout=2)
