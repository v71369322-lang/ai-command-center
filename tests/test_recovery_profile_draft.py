"""Real PG failure -> existing inspection -> disabled draft, without provider I/O."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4
import json

from sqlalchemy import select

from command_center.coding.first_experiment import Evidence, REQUIRED, create_task
from command_center.coding.gateway import Gateway
from command_center.models import Audit, ExternalAction, ExternalGrant
from command_center.runtime_ledger import RuntimeLedger
from command_center.store import digest
from command_center.worker import Runner
from test_first_experiment import experiment_config
from test_recovery_experiment import LOOP

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / ('infra/vps/' + name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


inspector = module('inspect_first_recovery')
creator = module('prepare_first_recovery_profile')


class Docker:
    mode = 'rootless-required'

    def preflight(self):
        return {'rootless_verified': True}

    def call(self, *args):
        assert args[0] == 'ps'
        return SimpleNamespace(returncode=0, stdout=b'')


def test_database_inspection_produces_a_valid_disabled_draft_without_changing_old_failure(store, monkeypatch, tmp_path):
    import command_center.store as store_module
    store.settings = replace(store.settings, source_revision=inspector.EXPECTED_SOURCE)
    config = experiment_config(live=True)
    config.synthetic_repository = creator.REPOSITORY
    config.first_experiment.repository_id = creator.REPOSITORY_ID
    config.first_experiment.payment_rub_per_usd_upper = '112.5'
    config.first_experiment.extra_rub_upper = '0'
    config.tariff.input_nano_rub, config.tariff.output_nano_rub = 84375, 506250
    now = datetime.now(timezone.utc)
    config.first_experiment.evidence = {k: Evidence(reference='PUBLIC_CHAIN_FIXTURE_ONLY',
        expires_at=(now + timedelta(minutes=20)).isoformat()) for k in REQUIRED}
    config.credential_files = {'openai': '/run/f2/openai.key', 'github-installation-token': '/run/f2/github.token'}
    with monkeypatch.context() as local:
        local.setattr(store_module, 'uuid4', lambda: UUID(creator.TASK_ID))
        task = create_task(store, 'owner')
    Gateway.authorize_configured(store, config, 'owner', task['id'], task['version'],
        budget_nano_rub=config.tariff.maximum() * 2, final_confirmation=True)
    claimed = store.claim(task['id'])
    store.coding_stage(task['id'], claimed['fence'], 'provider_running', iteration=1)
    response = {'id': 'resp_public_draft_chain', 'model': config.tariff.model, 'status': 'completed',
        'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
            'content': [{'type': 'output_text', 'text': json.dumps({'source': LOOP})}]}],
        'usage': {'input_tokens': 100, 'output_tokens': 32, 'total_tokens': 132}}
    with store.transaction() as session:
        action = ExternalAction(id=str(uuid4()), task_id=task['id'], key=task['id'] + ':ai/1', kind='openai',
            request_hash='c' * 64, state='COMPLETE', reserved=0, actual=config.tariff.cost(100, 32),
            created_at=store.now(session), evidence={'method': 'POST', 'response': response, 'usage': response['usage']})
        session.add(action)
        store.audit(session, 'external_response', 'gateway', task['id'], action_id=action.id,
                    ledger_digest=Gateway.action_digest(action), response_hash=digest(response))
        grant_digest = session.get(ExternalGrant, task['id']).digest
    store.coding_stage(task['id'], claimed['fence'], 'external_stopped',
        failure='provider_or_verifier_contract_rejected', summary='PUBLIC_CHAIN_FIXTURE_ONLY')
    store.abort(task['id'], claimed['fence'], 'external_coding_blocked', True)
    path = tmp_path / 'ledger.sqlite'
    runtime = RuntimeLedger(path)
    runtime.register({**task, 'fence': claimed['fence'], 'revision': inspector.EXPECTED_SOURCE},
        Runner.name(claimed), 30)
    runtime.phase(task['id'], claimed['fence'], 'DONE')
    runtime.watchdog()
    runtime.worker_beat(inspector.EXPECTED_SOURCE)
    before = store.get(task['id']), path.read_bytes()
    with store.transaction() as session:
        old_audit = [a.digest for a in session.scalars(select(Audit).order_by(Audit.sequence))]
    observed = inspector.inspect(store, ledger_path=path, backend=Docker(), config_loader=lambda: config)
    assert observed['status'] == 'LOCAL_OBSERVATIONS_COMPLETE', observed['blockers']
    prepared, summary = creator.build_draft(config, observed, datetime.now(timezone.utc))
    assert prepared.mode == 'disabled' and not prepared.connected()
    assert prepared.first_experiment.original_grant_digest == grant_digest
    assert prepared.first_experiment.original_task_id == task['id']
    assert not prepared.first_experiment.evidence and prepared.tariff.confirmed is False
    assert summary['max_calls'] == 1 and summary['one_call_reservation_nano_rub'] == 34_786_800_000
    assert summary['paid_recovery_authorized'] is False
    assert before == (store.get(task['id']), path.read_bytes())
    with store.transaction() as session:
        assert old_audit == [a.digest for a in session.scalars(select(Audit).order_by(Audit.sequence))]
        assert len(session.scalars(select(ExternalAction)).all()) == 1
