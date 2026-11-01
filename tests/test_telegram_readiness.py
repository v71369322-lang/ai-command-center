"""Actual PostgreSQL + strict mock Bot API; no provider/credential/host access."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import hashlib
import json

import httpx
import pytest
from sqlalchemy import select, text

from command_center.coding.first_experiment import Evidence, FirstExperiment, REQUIRED
from command_center.coding.integration_config import FileCredentials, IntegrationConfig
from command_center.models import Control, ExternalAction, ExternalGrant, Task, TelegramDelivery, TelegramInbox
from command_center.store import Denied, canonical
from command_center.telegram_bridge import TelegramBridge
from test_readiness import setup as external_setup, send
from test_telegram_service import FakeBot, OWNER, client_for, update
from test_telegram_service import configured as configured
from test_telegram_task_status import authority


@pytest.fixture
def bridge(store, configured, monkeypatch):
    monkeypatch.delenv('F2_INTEGRATION_CONFIG_FILE', raising=False)
    fake = FakeBot()
    client = client_for(configured, fake)
    yield TelegramBridge(store, client, OWNER), fake
    client.close()


def report(service, uid=1):
    service.receive(update(uid, '/readiness'))
    while service.deliver_one():
        pass


def ledger(store):
    with store.transaction() as session:
        return ([(r.id, r.task_id, r.state, r.reserved, r.actual, r.evidence) for r in
                 session.scalars(select(ExternalAction).order_by(ExternalAction.id))],
                [(r.task_id, r.document, r.digest) for r in
                 session.scalars(select(ExternalGrant).order_by(ExternalGrant.task_id))])


@pytest.mark.parametrize('state', ['open', 'halted', 'recovery'])
def test_summary_reads_control_without_changing_authority(bridge, store, state):
    service, fake = bridge
    if state != 'open':
        store.halt('owner')
    if state == 'recovery':
        with store.transaction() as session:
            session.get(Control, 1).recovery = True
            store.audit(session, 'fixture_recovery', 'system')
    before = authority(store), ledger(store)
    report(service)
    result = fake.sent[-1]
    expected = {'open': 'приём разрешённых задач открыт', 'halted': 'обычная остановка',
                'recovery': 'восстановление; новые запуски заблокированы'}[state]
    assert expected in result['text']
    assert store.settings.source_revision in result['text']
    assert 'Состояние gateway неизвестно' in result['text']
    assert 'Синтетический бюджет не является балансом OpenAI' in result['text']
    assert 'Голосовые поручения до расшифровки: 0' in result['text']
    assert 'Проверенные подключения проектов: 0 из 4; execution не включён' in result['text']
    assert result['chat_id'] == OWNER and 'reply_markup' not in result
    assert len(canonical(result).encode()) <= 8192 and len(result['text']) <= 4096
    assert (authority(store), ledger(store)) == before
    assert [method for method, _ in fake.calls] == ['sendMessage']


def test_pending_count_is_bound_to_this_connection_and_excludes_commands(bridge, store):
    service, fake = bridge
    service.receive(update(1, 'Public request, not executable code'))
    with store.transaction() as session:
        session.add(TelegramInbox(id='other:1', profile='other', fingerprint='f' * 64,
                    intent={'kind': 'capture', 'text': 'Foreign private request'},
                    state='NEEDS_PLANNING', created_at=store.now(session)))
    report(service, 2)
    assert 'ожидающие планирования: 1' in fake.sent[-1]['text']
    assert 'Foreign private request' not in canonical(fake.sent)


@pytest.mark.parametrize('mode', ['disabled', 'http_mock', 'live'])
def test_local_config_is_not_live_verification_and_credentials_are_never_read(bridge, tmp_path, monkeypatch, mode):
    service, fake = bridge
    profile = tmp_path / 'profile.json'
    marker = 'PRIVATE_CONFIGURATION_MARKER_NOT_A_SECRET'
    config = IntegrationConfig(mode=mode, live_authorized=True, budget_evidence=marker,
        credential_files={'openai': str(tmp_path / marker), 'github-installation-token': str(tmp_path / marker)})
    # credential_files is excluded from serialization; raw operator input has it.
    profile.write_text(json.dumps({**config.model_dump(), 'credential_files': config.credential_files}))
    monkeypatch.setenv('F2_INTEGRATION_CONFIG_FILE', str(profile))
    monkeypatch.setattr(FileCredentials, 'get', lambda *args: pytest.fail('credential values must never be opened'))
    report(service)
    body = fake.sent[-1]['text']
    assert 'Режим локального AI-профиля' in body and 'Профиль первого AI-эксперимента не задан' in body
    assert marker not in body and str(tmp_path) not in body
    assert 'этой командой не проверяются' in body
    if mode == 'live':
        assert 'не подтверждает работоспособность' in body
        assert 'Операторский live-флаг: включён' in body
    assert [method for method, _ in fake.calls] == ['sendMessage']


@pytest.mark.parametrize('evidence_state', ['missing', 'expired', 'current'])
def test_first_experiment_uses_current_gates_but_never_authorizes(bridge, store, tmp_path, monkeypatch, evidence_state):
    service, fake = bridge
    with store.transaction() as session:
        now = store.now(session)
    expiry = now + timedelta(minutes=5) if evidence_state == 'current' else now - timedelta(seconds=1)
    marker = 'PRIVATE_EVIDENCE_REFERENCE_NOT_FOR_TELEGRAM'
    evidence = {} if evidence_state == 'missing' else {
        key: Evidence(reference=marker, expires_at=expiry.isoformat()) for key in REQUIRED}
    experiment = FirstExperiment(payment_rub_per_usd_upper='100', extra_rub_upper='0',
        existing_credit_usd='1', repository_id=725000001, evidence=evidence)
    profile = tmp_path / 'profile.json'
    profile.write_text(IntegrationConfig(first_experiment=experiment).model_dump_json())
    monkeypatch.setenv('F2_INTEGRATION_CONFIG_FILE', str(profile))
    before = authority(store), ledger(store)
    report(service)
    body = fake.sent[-1]['text']
    assert 'не более 100 ₽ суммарно, до 2 вызовов и 1 исправления' in body
    if evidence_state == 'current':
        assert 'это ещё не окончательное разрешение запуска' in body
        assert 'Не подтверждено или просрочено' not in body
    else:
        assert 'Не подтверждено или просрочено' in body and 'доступный API-баланс' in body
    assert marker not in body
    assert (authority(store), ledger(store)) == before


@pytest.mark.parametrize('failure', ['missing', 'malformed', 'oversized', 'symlink'])
def test_unavailable_local_config_reports_unknown_without_echoing_errors(bridge, tmp_path, monkeypatch, failure):
    service, fake = bridge
    profile = tmp_path / 'PRIVATE_PATH_MUST_NOT_LEAK'
    if failure == 'malformed':
        profile.write_text('{"PRIVATE_VALUE_MUST_NOT_LEAK":true}')
    elif failure == 'oversized':
        profile.write_text('x' * 16385)
    elif failure == 'symlink':
        profile.symlink_to(tmp_path / 'missing-target')
    monkeypatch.setenv('F2_INTEGRATION_CONFIG_FILE', str(profile))
    report(service)
    body = fake.sent[-1]['text']
    assert 'Локальный AI-профиль не удалось проверить' in body and 'Состояние gateway неизвестно' in body
    assert 'PRIVATE_' not in body and str(tmp_path) not in body


@pytest.mark.parametrize('tampered', [False, True])
def test_deployment_byte_pin_is_checked_before_readiness(bridge, store, tmp_path, monkeypatch, tampered):
    service, fake = bridge
    profile = tmp_path / 'config.json'
    raw = IntegrationConfig(mode='live', first_experiment=FirstExperiment()).model_dump_json().encode()
    profile.write_bytes(raw + (b'\n' if tampered else b''))
    monkeypatch.setenv('F2_INTEGRATION_CONFIG_FILE', str(profile))
    monkeypatch.setenv('F2_INTEGRATION_CONFIG_SHA256', hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(FileCredentials, 'get', lambda *a: pytest.fail('no credential read'))
    before = authority(store), ledger(store)
    report(service)
    body = fake.sent[-1]['text']
    assert ('Состояние gateway неизвестно' in body) == tampered
    assert ('Режим локального AI-профиля: live' in body) != tampered
    assert (authority(store), ledger(store)) == before
    assert [method for method, _ in fake.calls] == ['sendMessage']


def test_duplicate_concurrent_replay_and_restart_keep_original_snapshot(bridge, store):
    service, fake = bridge
    request = update(1, '/readiness')
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(service.receive, [request, request]))
    assert values[0] == values[1]
    assert service.deliver_one()['state'] == 'SENT'
    first = deepcopy(fake.sent)
    store.halt('owner')
    restarted = TelegramBridge(store, service.client, OWNER)
    assert restarted.receive(request) == values[0]
    assert restarted.deliver_one() is None and fake.sent == first
    report(restarted, 2)
    assert 'обычная остановка' in fake.sent[-1]['text']


def test_crash_rolls_back_and_restart_completes_once(bridge, store, monkeypatch):
    service, fake = bridge
    before = authority(store)
    with monkeypatch.context() as patch:
        patch.setattr(service, 'enqueue', lambda *args: (_ for _ in ()).throw(RuntimeError('crash')))
        with pytest.raises(RuntimeError, match='crash'):
            service.receive(update(1, '/readiness'))
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.resume_pending()
    restarted.receive(update(1, '/readiness'))
    assert restarted.deliver_one()['state'] == 'SENT' and restarted.deliver_one() is None
    assert len(fake.sent) == 1 and authority(store) == before


def test_unknown_send_outcome_is_preserved_without_automatic_resend(bridge, store):
    service, fake = bridge
    fake.after = lambda method: (_ for _ in ()).throw(httpx.ReadTimeout('public fixture loss'))
    service.receive(update(1, '/readiness'))
    assert service.deliver_one()['state'] == 'UNCERTAIN'
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.recover()
    restarted.receive(update(1, '/readiness'))
    assert restarted.deliver_one() is None and len(fake.sent) == 1


def test_unknown_ai_spend_is_not_released_or_retried_by_status(bridge, store):
    service, fake = bridge
    gateway, task, provider = external_setup(store)
    provider.after = lambda request: (_ for _ in ()).throw(httpx.ReadTimeout('public fixture loss'))
    from command_center.coding.gateway import Uncertain
    try:
        with pytest.raises(Uncertain):
            send(gateway, task)
        before = authority(store), ledger(store)
        report(service)
        assert (authority(store), ledger(store)) == before
        assert gateway.status(task['id'])['uncertain_nano_rub'] > 0
        assert provider.ai_calls == 1 and len(fake.sent) == 1
    finally:
        gateway.close()


@pytest.mark.parametrize('attack', ['sender', 'group', 'forward', 'arguments'])
def test_query_denied_before_persistence_or_http_outside_owner_scope(bridge, store, attack):
    service, fake = bridge
    value = update(1, '/readiness')
    if attack == 'sender':
        value['message']['from']['id'] += 1
    elif attack == 'group':
        value['message']['chat']['type'] = 'group'
    elif attack == 'forward':
        value['message']['forward_origin'] = {'type': 'user'}
    else:
        value['message']['text'] += ' enable-live'
    with pytest.raises(Denied):
        service.receive(value)
    with store.transaction() as session:
        assert session.scalar(select(TelegramInbox)) is None
        assert session.scalar(select(TelegramDelivery)) is None
    assert fake.calls == []


@pytest.mark.parametrize('state', ['RUNNING', 'VERIFYING', 'CANCEL_REQUESTED', 'RECONCILING', 'SECURITY_BLOCKED'])
def test_unresolved_count_matches_existing_f1_resume_denial(bridge, store, state):
    service, fake = bridge
    task = store.create('owner', 'public-fixture', {'kind': 'approved_render', 'values': {'request': 'fixture'}})
    store.halt('owner')
    with store.transaction() as session:
        session.get(Task, task['id']).state = state
        store.audit(session, 'fixture_unresolved', 'system', task['id'])
    before = authority(store)
    report(service)
    assert 'Исполнения, требующие сверки перед resume: 1' in fake.sent[-1]['text']
    assert authority(store) == before
    snapshot = store.snapshot()
    with pytest.raises(Denied, match='unreconciled_resume'):
        store.resume('owner', snapshot['epoch'], snapshot['checkpoint_digest'])


def test_revocation_blocks_queued_summary_before_http(bridge, configured):
    service, fake = bridge
    service.receive(update(1, '/readiness'))
    path, config = configured
    path.write_text(config.model_copy(update={'mode': 'disabled'}).model_dump_json())
    with pytest.raises(Denied, match='revoked_or_changed'):
        service.deliver_one()
    assert fake.calls == []


def test_unavailable_database_never_sends_a_cached_healthy_reply(bridge, store, monkeypatch):
    from sqlalchemy.exc import OperationalError
    service, fake = bridge
    monkeypatch.setattr(store.engine, 'connect', lambda: (_ for _ in ()).throw(
        OperationalError('public synthetic database outage', {}, None)))
    with pytest.raises(OperationalError):
        service.receive(update(1, '/readiness'))
    assert fake.calls == []


def test_audit_tampering_blocks_summary(bridge, admin):
    service, fake = bridge
    with admin.engine.begin() as connection:
        connection.execute(text("UPDATE audit SET digest=:bad WHERE sequence=(SELECT max(sequence) FROM audit)"),
                           {'bad': 'f' * 64})
    with pytest.raises(Denied, match='audit'):
        service.receive(update(1, '/readiness'))
    assert fake.calls == []
