"""Real PostgreSQL read-only transactions; no VPS, provider or real Docker calls."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text

from command_center.coding.first_experiment import FirstExperiment
from command_center.models import Audit, ExternalAction, ExternalGrant
from command_center.runtime_ledger import RuntimeLedger
from command_center.worker import Runner
from test_recovery_experiment import recovery as recovery

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('readonly_recovery_pg', ROOT / 'infra/vps/inspect_first_recovery.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class Docker:
    mode = 'rootless-required'

    def preflight(self):
        return {'rootless_verified': True}

    def call(self, *args):
        assert args[0] == 'ps' and '-a' in args and '--filter' in args
        return SimpleNamespace(returncode=0, stdout=b'')


@pytest.fixture
def inspection(store, recovery, tmp_path, monkeypatch):
    config, task_id, _, _, _ = recovery
    with store.transaction() as session:
        grant = session.get(ExternalGrant, task_id)
        original_source = grant.document['revision']
    monkeypatch.setattr(probe, 'EXPECTED_SOURCE', original_source)
    monkeypatch.setattr(probe, 'TASK_ID', task_id)
    store.settings = replace(store.settings, source_revision=original_source)
    old = config.model_copy(deep=True)
    fields = old.first_experiment.model_dump(exclude={'original_task_id', 'original_grant_digest', 'id'})
    old.first_experiment = FirstExperiment(**fields)
    ledger_path = tmp_path / 'ledger.sqlite'
    runtime = RuntimeLedger(ledger_path)
    task = {'id': task_id, 'fence': 1, 'revision': original_source}
    runtime.register(task, Runner.name(task), 30)
    runtime.phase(task_id, 1, 'DONE')
    runtime.watchdog()
    runtime.worker_beat(original_source)
    return old, ledger_path, runtime


def snapshot(store):
    with store.transaction() as session:
        return ([a.digest for a in session.scalars(select(Audit).order_by(Audit.sequence))],
            [(a.id, a.state, a.actual, a.reserved) for a in session.scalars(select(ExternalAction))])


def test_one_report_inspects_all_local_sections_with_pg_read_only_and_no_side_effects(store, inspection, monkeypatch):
    config, path, _ = inspection
    before = snapshot(store), path.read_bytes()
    audit = store.check_audit
    observed = []
    def verify_read_only(session):
        observed.append((session.scalar(text('SHOW transaction_read_only')),
                         session.scalar(text('SHOW transaction_isolation'))))
        audit(session)
    monkeypatch.setattr(store, 'check_audit', verify_read_only)
    report = probe.inspect(store, ledger_path=path, backend=Docker(), config_loader=lambda: config)
    assert report['status'] == 'LOCAL_OBSERVATIONS_COMPLETE', report['blockers']
    assert observed == [('on', 'repeatable read')]
    assert report['database']['grant_digest']
    assert report['database']['saved_response_failure_matches'] is True
    assert report['runtime']['parent_run_done'] is report['container']['parent_container_absent'] is True
    assert report['profile']['matches_original_grant'] is True
    assert report['paid_recovery_authorized'] is report['recovery_authority_verified'] is False
    assert report['provider_credential_values_read'] is False and report['provider_calls'] == 0
    monkeypatch.setattr(store, 'check_audit', audit)
    assert (snapshot(store), path.read_bytes()) == before


def test_postgresql_itself_rejects_accidental_mutation_in_diagnostic(store, inspection, monkeypatch):
    config, path, _ = inspection
    before = snapshot(store)
    def attempt_write(session):
        session.execute(text("UPDATE tasks SET reason='UNAUTHORIZED_DIAGNOSTIC_WRITE'"))
    monkeypatch.setattr(store, 'check_audit', attempt_write)
    report = probe.inspect(store, ledger_path=path, backend=Docker(), config_loader=lambda: config)
    assert report['status'] == 'BLOCKED' and 'database_inspection_failed' in report['blockers']
    assert snapshot(store) == before
    assert 'UNAUTHORIZED_DIAGNOSTIC_WRITE' not in json.dumps(report)


def test_expired_profile_reports_named_gates_without_exposing_references_or_suggesting_consent(store, inspection):
    config, path, _ = inspection
    for item in config.first_experiment.evidence.values():
        item.reference = 'PRIVATE_REFERENCE_MUST_NOT_BE_PRINTED'
    report = probe.inspect(store, ledger_path=path, backend=Docker(), config_loader=lambda: config,
                           now=datetime.now(timezone.utc) + timedelta(hours=1))
    assert report['status'] == 'BLOCKED'
    assert 'profile_evidence_missing_or_expired' in report['blockers']
    assert not any(report['profile']['evidence_current'].values())
    assert report['profile']['token_validity_verified'] is False
    assert 'PRIVATE_REFERENCE' not in json.dumps(report)
    assert report['paid_recovery_authorized'] is report['token_issued'] is False


def test_uncertain_runtime_is_reported_without_reconciliation(store, inspection):
    config, path, runtime = inspection
    runtime.phase(probe.TASK_ID, 1, 'UNCERTAIN')
    before = path.read_bytes()
    report = probe.inspect(store, ledger_path=path, backend=Docker(), config_loader=lambda: config)
    assert 'runtime_requires_review' in report['blockers']
    assert report['runtime']['parent_run_done'] is False
    assert report['runtime']['unresolved_runs'] == 1
    assert path.read_bytes() == before
    assert report['runtime_mutations_requested'] is False
