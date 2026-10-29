"""Actual PG, strict Bot API mock; cached terminal fixtures are NOT real AI proof."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import hashlib

import httpx
import pytest
from sqlalchemy import select

from command_center.coding.first_experiment import CAP, REQUEST_KEY, task_payload
from command_center.coding.gateway import Gateway
from command_center.coding.integration_config import FileCredentials
from command_center.coding.spec import BASE_SHA, branch_name
from command_center.models import ExternalGrant, Task, TelegramDelivery
from command_center.store import Denied, canonical, digest
from command_center.telegram_bridge import TelegramBridge
from test_first_experiment import experiment_config
from test_readiness import send
from test_telegram_readiness import bridge as bridge, ledger
from test_telegram_service import OWNER, configured as configured, update
from test_telegram_task_status import authority
from f2_http_support import Credentials, FakeHTTP


def report(bridge, uid=1):
    service, fake = bridge
    service.receive(update(uid, '/experiment'))
    while service.deliver_one():
        pass
    return fake.sent[-1]['text']


def create(store):
    return store.create('owner', REQUEST_KEY, task_payload())


@pytest.fixture
def active(store):
    task = create(store)
    fake = FakeHTTP(model=experiment_config().tariff.model)
    gateway = Gateway(store, experiment_config(), transport=httpx.MockTransport(fake.handle), credentials=Credentials())
    gateway.authorize('owner', task['id'], task['version'], budget_nano_rub=CAP)
    task = store.claim(task['id'])
    yield gateway, task, fake
    gateway.close()


def complete_fixture(store, task, *, live=False, bad=None):
    """Explicit cached-record fixture, not a provider call or independent replay."""
    pr = dict(task_id=task['id'], mode='github' if live else 'http_mock', published=live,
              base_sha=BASE_SHA, head_sha='a' * 40, head_branch=branch_name(task['id'], task['fence']),
              remote_number=12, url='https://github.com/fixture/acc-f2-synthetic-test/pull/12')
    if bad == 'url':
        pr['url'] = 'https://evil.invalid/PRIVATE_DO_NOT_ECHO'
    elif bad == 'head':
        pr['head_sha'] = 'b' * 40
    elif bad == 'published':
        pr['published'] = not live
    if live:
        with store.transaction() as session:
            grant = session.get(ExternalGrant, task['id'])
            grant.document = {**grant.document, 'mode': 'live', 'final_confirmation': True}
            grant.digest = digest(grant.document)
            store.audit(session, 'external_scope_approved', 'owner', task['id'], grant_digest=grant.digest)
    store.coding_stage(task['id'], task['fence'], 'complete', pr=pr, independent_proof='c' * 64,
                       final_sha='a' * 40, summary='PRIVATE_PROVIDER_TEXT_DO_NOT_ECHO')
    artifact = 'PRIVATE_ARTIFACT_DO_NOT_ECHO'
    store.finish(task['id'], task['fence'], artifact, hashlib.sha256(artifact.encode()).hexdigest(), actual_cost=0)


@pytest.mark.parametrize('state', ['open', 'halted', 'recovery'])
def test_empty_snapshot_does_not_create_or_authorize(bridge, store, state, monkeypatch):
    if state != 'open':
        store.halt('owner')
    if state == 'recovery':
        with store.transaction() as session:
            from command_center.models import Control
            session.get(Control, 1).recovery = True
    before = authority(store), ledger(store)
    monkeypatch.setattr(Gateway, '__init__', lambda *a, **k: pytest.fail('no gateway construction'))
    monkeypatch.setattr(FileCredentials, 'get', lambda *a: pytest.fail('no credential read'))
    monkeypatch.setattr(httpx, 'Client', lambda *a, **k: pytest.fail('no new HTTP client'))
    body = report(bridge)
    assert 'ещё не создан' in body and '/readiness' in body
    assert (authority(store), ledger(store)) == before
    assert [method for method, _ in bridge[1].calls] == ['sendMessage']


def test_fixed_api_task_visible_without_broadening_telegram_task_scope(bridge, store):
    task = create(store)
    foreign = store.create('owner', 'other-key', task_payload())
    before = authority(store), ledger(store)
    body = report(bridge)
    assert task['id'] in body and foreign['id'] not in body
    assert 'Ожидает отдельного разрешения' in body
    assert 'Учтённый расход по журналу шлюза: 0 ₽' in body
    assert (authority(store), ledger(store)) == before
    with store.transaction() as session:
        assert not session.scalars(bridge[0].scoped_tasks()).all()


@pytest.mark.parametrize('state', ['READY', 'RUNNING', 'VERIFYING', 'CANCEL_REQUESTED', 'CANCELLED',
                                 'RECONCILING', 'SECURITY_BLOCKED', 'FAILED', 'SUCCEEDED'])
def test_lifecycle_uses_fixed_text_not_provider_output(bridge, store, state):
    task = create(store)
    with store.transaction() as session:
        row = session.get(Task, task['id'])
        row.state = state
        row.reason = 'PRIVATE_REASON_DO_NOT_ECHO'
        row.lease_until = store.now(session) + timedelta(seconds=10)
    before = authority(store), ledger(store)
    body = report(bridge)
    assert task['id'] in body and 'PRIVATE_' not in body
    assert 'Draft PR:' not in body and 'независимо проверен' not in body
    assert (authority(store), ledger(store)) == before


def test_expired_lease_is_not_presented_as_running(bridge, store):
    task = create(store)
    with store.transaction() as session:
        row = session.get(Task, task['id'])
        row.state, row.lease_until = 'RUNNING', store.now(session) - timedelta(seconds=1)
    assert 'текущее выполнение не подтверждено' in report(bridge)


def test_previous_source_task_requires_reconciliation(bridge, store, monkeypatch):
    create(store)
    monkeypatch.setattr(store, 'settings', replace(store.settings, source_revision='a' * 40))
    assert 'создан другой версией' in report(bridge)


@pytest.mark.parametrize('attack', ['user', 'group', 'forward', 'sender_chat'])
def test_only_bound_private_owner_can_view_global_experiment(bridge, attack):
    command = update(1, '/experiment')
    if attack == 'user':
        command['message']['from']['id'] += 1
    elif attack == 'group':
        command['message']['chat']['type'] = 'group'
    elif attack == 'forward':
        command['message']['forward_origin'] = {'type': 'user'}
    else:
        command['message']['sender_chat'] = {'id': OWNER}
    with pytest.raises(Denied, match='owner_private_chat_required'):
        bridge[0].receive(command)
    assert not bridge[1].calls


@pytest.mark.parametrize('uncertain', [False, True])
def test_accounting_reads_existing_gateway_anchors_without_network_or_mutation(bridge, store, active, uncertain, monkeypatch):
    gateway, task, fake = active
    if uncertain:
        fake.after = lambda request: (_ for _ in ()).throw(httpx.ReadTimeout('public fixture loss'))
        with pytest.raises(Denied):
            send(gateway, task)
    else:
        send(gateway, task)
    known = gateway.status(task['id'])
    before, calls = (authority(store), ledger(store)), deepcopy(fake.calls)
    monkeypatch.setattr(Gateway, '__init__', lambda *a, **k: pytest.fail('no gateway construction'))
    monkeypatch.setattr(FileCredentials, 'get', lambda *a: pytest.fail('no credential read'))
    monkeypatch.setattr(httpx, 'Client', lambda *a, **k: pytest.fail('no new HTTP client'))
    body = report(bridge)
    assert 'Операций OpenAI по журналу: 1' in body
    assert ('Внешняя операция не сверена' in body) == uncertain
    from command_center.telegram_experiment import rub
    assert rub(known['actual_nano_rub']) in body and rub(known['uncertain_nano_rub']) in body
    assert 'HTTP-моки; настоящего AI нет' in body
    assert (authority(store), ledger(store)) == before and fake.calls == calls


def test_billing_settlement_does_not_clear_operational_uncertainty(bridge, store, active):
    gateway, task, fake = active
    fake.after = lambda request: (_ for _ in ()).throw(httpx.ReadTimeout('fixture loss'))
    with pytest.raises(Denied):
        send(gateway, task)
    action = gateway.status(task['id'])['actions'][0]['id']
    gateway.reconcile_usage('owner', action, 100, 32, 'public fixture billing attestation')
    before = authority(store), ledger(store)
    body = report(bridge)
    assert 'Спорный резерв по журналу: 0 ₽' in body and 'Внешняя операция не сверена' in body
    assert (authority(store), ledger(store)) == before


@pytest.mark.parametrize('live,bad', [(False, None), (True, None), (True, 'url'), (True, 'head'), (False, 'published')])
def test_cached_completion_needs_matching_proof_and_publication_mode(bridge, store, active, live, bad):
    _, task, _ = active
    complete_fixture(store, task, live=live, bad=bad)
    before = authority(store), ledger(store)
    body = report(bridge)
    assert ('Результат независимо проверен' in body) == (bad is None)
    assert ('Зафиксирован Draft PR:' in body) == (live and bad is None)
    if not live and bad is None:
        assert 'реальный PR не опубликован' in body
    assert 'PRIVATE_' not in body and 'evil.invalid' not in body
    assert (authority(store), ledger(store)) == before


@pytest.mark.parametrize('field', ['payload', 'payload_hash', 'owner_role', 'request_key'])
def test_task_identity_cannot_be_inferred_from_experiment_tag_alone(bridge, store, field):
    task = create(store)
    with store.transaction() as session:
        row = session.get(Task, task['id'])
        if field == 'payload':
            row.payload = {**row.payload, 'cost': 1}
        else:
            setattr(row, field, {'payload_hash': 'a' * 64, 'owner_role': 'operator', 'request_key': 'owner:other'}[field])
    if field == 'request_key':
        assert 'ещё не создан' in report(bridge)
    else:
        with pytest.raises(Denied, match='task_integrity'):
            report(bridge)


@pytest.mark.parametrize('tamper', ['grant', 'ledger', 'completion', 'artifact'])
def test_mutable_rows_without_matching_audit_cannot_claim_success(bridge, store, active, tamper):
    gateway, task, _ = active
    send(gateway, task)
    complete_fixture(store, task)
    with store.transaction() as session:
        if tamper == 'grant':
            row = session.get(ExternalGrant, task['id'])
            row.document = {**row.document, 'mode': 'live'}
        elif tamper == 'ledger':
            from command_center.models import ExternalAction
            row = session.scalar(select(ExternalAction).where(ExternalAction.task_id == task['id']))
            row.actual += 1
        else:
            row = session.get(Task, task['id'])
            if tamper == 'completion':
                row.coding_evidence = {**row.coding_evidence, 'independent_proof': 'b' * 64}
            else:
                row.artifact = 'changed artifact'
    if tamper in {'grant', 'ledger'}:
        with pytest.raises(Denied, match='integrity'):
            report(bridge)
    else:
        assert 'Результат независимо проверен' not in report(bridge)


def test_duplicate_concurrent_snapshot_is_durable_and_fresh_update_rechecks(bridge, store):
    service, fake = bridge
    create(store)
    command = update(1, '/experiment')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(service.receive, [command, command]))
    assert results[0] == results[1]
    assert service.deliver_one()['state'] == 'SENT'
    first = deepcopy(fake.sent)
    store.halt('owner')
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.receive(command)
    assert restarted.deliver_one() is None and fake.sent == first
    report((restarted, fake), 2)
    assert 'Новые запуски остановлены' in fake.sent[-1]['text']


@pytest.mark.parametrize('value', ['/experiment 1', '/experiment resume', '/experiment\nconfirm'])
def test_arguments_cannot_turn_snapshot_into_action(bridge, value):
    with pytest.raises(Denied, match='arguments_forbidden'):
        bridge[0].receive(update(1, value))


def test_send_loss_is_uncertain_not_automatically_resent(bridge, store):
    service, fake = bridge
    fake.after = lambda method: (_ for _ in ()).throw(httpx.ReadTimeout('fixture response loss'))
    service.receive(update(1, '/experiment'))
    assert service.deliver_one()['state'] == 'UNCERTAIN'
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.recover()
    assert restarted.deliver_one() is None and len(fake.sent) == 1
    with store.transaction() as session:
        assert session.scalar(select(TelegramDelivery)).state == 'UNCERTAIN'


def test_transport_size_and_no_arbitrary_model_repository_or_evidence_echo(bridge, store, active):
    _, task, _ = active
    complete_fixture(store, task)
    report(bridge)
    body = bridge[1].sent[-1]
    assert len(body['text']) <= 4096 and len(canonical(body).encode()) <= 8192
    assert 'PRIVATE_' not in canonical(body) and 'parse_mode' not in body
