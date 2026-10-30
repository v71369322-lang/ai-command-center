"""Public synthetic offline draft fixtures. No database, Docker or provider I/O."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import httpx
import pytest

from command_center.coding.first_experiment import (CAP, CONTEXT_TOKENS, MODEL, OUTPUT_TOKENS, REQUIRED,
    Evidence, FirstExperiment)
from command_center.coding.gateway import Gateway
from command_center.coding.integration_config import FileCredentials, IntegrationConfig, Tariff
from command_center.deployment_integrations import _configuration
from command_center.store import Denied, Store, digest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('offline_recovery_draft', ROOT / 'infra/vps/prepare_first_recovery_profile.py')
draft = importlib.util.module_from_spec(spec)
spec.loader.exec_module(draft)
NOW = datetime(2026, 10, 30, 14, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def no_remote_authority(monkeypatch):
    def forbidden(*a, **kw):
        pytest.fail('draft preparation requested provider/database/credentials/authority')
    for cls, method in [(Gateway, '__init__'), (Gateway, 'authorize_configured'), (Store, '__init__'),
                        (Store, 'approve'), (FileCredentials, 'get'), (httpx, 'Client')]:
        monkeypatch.setattr(cls, method, forbidden)


def inputs():
    config = IntegrationConfig(mode='live', live_authorized=True, synthetic_repository=draft.REPOSITORY,
        first_experiment=FirstExperiment(repository_id=draft.REPOSITORY_ID,
            payment_rub_per_usd_upper='112.5', extra_rub_upper='0', existing_credit_usd='8',
            evidence={k: Evidence(reference='PRIVATE_REFERENCE_MUST_NOT_BE_PRINTED',
                expires_at=(NOW + timedelta(hours=1)).isoformat()) for k in REQUIRED}),
        daily_nano_rub=CAP, monthly_nano_rub=CAP, budget_evidence='PRIVATE_OLD_BUDGET_REFERENCE',
        tariff=Tariff(model=MODEL, input_nano_rub=84375, output_nano_rub=506250,
            context_tokens=CONTEXT_TOKENS, max_output_tokens=OUTPUT_TOKENS, confirmed=True,
            evidence='PUBLIC_SYNTHETIC_TARIFF_FIXTURE'),
        credential_files={'openai': '/run/f2/openai.key', 'github-installation-token': '/run/f2/github.token'})
    source_hash = digest(config.model_dump())
    db = {k: True for k in ('state_failed', 'reason_matches', 'fixed_payload_matches', 'owner_matches',
        'attempts_is_one', 'synthetic_reserve_zero', 'failure_matches', 'grant_self_digest_matches',
        'grant_source_matches', 'grant_mode_live', 'all_actions_closed', 'saved_response_failure_matches',
        'audit_chain_verified', 'action_ledger_verified')}
    db.update(task_id=draft.TASK_ID, fence=1, openai_count=1, reserved_nano_rub=0,
        grant_digest='a' * 64, grant_profile_hash=source_hash, recovery_authority_verified=False,
        actual_nano_rub=47_840_625, grant_budget_nano_rub=69_573_600_000, action_count=1,
        actions=[{'kind': 'openai', 'state': 'COMPLETE', 'actual_nano_rub': 47_840_625, 'reserved_nano_rub': 0}])
    report = {'schema': 1, 'scope': 'fixed_parent_local_read_only', 'task_id': draft.TASK_ID,
        'checked_at_utc': NOW.isoformat(), 'read_only': True, 'source_matches_installed': True,
        'provider_calls': 0, 'paid_calls': 0, 'status': 'LOCAL_OBSERVATIONS_COMPLETE', 'blockers': [],
        'database': db, 'runtime': {**{k: True for k in ('audit_chain_verified', 'parent_run_done',
            'parent_revision_matches', 'container_name_matches', 'watchdog_fresh', 'worker_fresh')}, 'unresolved_runs': 0},
        'container': {'rootless_preflight_verified': True, 'parent_container_absent': True},
        'profile': {'profile_hash': source_hash, 'matches_original_grant': True}}
    report.update({k: False for k in ('provider_credential_values_read', 'response_text_printed', 'task_restarted',
        'application_mutations_requested', 'runtime_mutations_requested', 'token_issued',
        'deployment_authorized', 'paid_recovery_authorized', 'recovery_authority_verified')})
    return config, report


def test_draft_is_one_call_disabled_and_drops_all_old_freshness_and_authority():
    config, report = inputs()
    before = config.model_dump(), dict(config.credential_files), deepcopy(report)
    result, summary = draft.build_draft(config, report, NOW)
    assert result.mode == 'disabled' and result.live_authorized is False and result.connected() is False
    assert result.first_experiment.call_limit == 1 and result.first_experiment.evidence == {}
    assert result.first_experiment.original_task_id == draft.TASK_ID
    assert result.first_experiment.original_grant_digest == 'a' * 64
    assert result.first_experiment.existing_credit_usd is None
    assert result.budget_evidence == '' and result.tariff.confirmed is False
    assert result.credential_files == config.credential_files
    assert result.tariff.maximum() == 34_786_800_000
    assert summary['cumulative_max_nano_rub'] == 34_834_640_625
    assert summary['original_budget_nano_rub'] == 69_573_600_000
    assert summary['max_calls'] == 1 and summary['max_repairs'] == 0
    assert summary['paid_recovery_authorized'] is summary['recovery_authority_verified'] is False
    assert set(summary['requires_fresh_evidence']) == set(REQUIRED)
    assert 'PRIVATE_REFERENCE' not in json.dumps(summary)
    assert before == (config.model_dump(), config.credential_files, report)


def test_flipping_operator_flags_does_not_supply_fresh_evidence_or_final_consent():
    from command_center.coding.first_experiment import RECOVERY_ID, task_payload
    config, report = inputs()
    result, _ = draft.build_draft(config, report, NOW)
    result.mode, result.live_authorized, result.budget_evidence = 'live', True, 'PUBLIC_TEST_ONLY'
    result.tariff.confirmed = True
    assert result.first_experiment.report(NOW)['ready_for_final_confirmation'] is False
    with pytest.raises(Denied, match='preconditions_missing'):
        result.first_experiment.validate_scope(result, task_payload(RECOVERY_ID)['coding'],
            result.tariff.maximum(), NOW, final_confirmation=True)


def test_expected_expired_evidence_allows_only_disabled_draft_not_a_refresh():
    config, report = inputs()
    report.update(status='BLOCKED', blockers=['profile_evidence_missing_or_expired'])
    result, _ = draft.build_draft(config, report, NOW)
    assert result.first_experiment.report(NOW)['ready_for_final_confirmation'] is False
    assert not result.first_experiment.evidence and result.mode == 'disabled'


@pytest.mark.parametrize('change', ['old', 'future', 'naive', 'schema_bool', 'wrong_task', 'source', 'paid',
    'approval', 'runtime_blocker', 'false_status', 'parent_failure', 'parent_digest', 'unresolved_action',
    'unknown_action', 'two_ai', 'mismatched_cost', 'bool_cost', 'reserve', 'runtime_unknown', 'pending_runs',
    'container_present', 'daemon_unknown', 'wrong_profile', 'profile_changed', 'report_missing'])
def test_changed_unresolved_or_stale_observations_cannot_prepare_draft(change):
    config, report = inputs()
    if change == 'old':
        report['checked_at_utc'] = (NOW - timedelta(seconds=301)).isoformat()
    elif change == 'future':
        report['checked_at_utc'] = (NOW + timedelta(seconds=1)).isoformat()
    elif change == 'naive':
        report['checked_at_utc'] = '2026-10-30T14:00:00'
    elif change == 'schema_bool':
        report['schema'] = True
    elif change == 'wrong_task':
        report['task_id'] = 'b' * 36
    elif change == 'source':
        report['source_matches_installed'] = False
    elif change == 'paid':
        report['paid_calls'] = 1
    elif change == 'approval':
        report['paid_recovery_authorized'] = True
    elif change == 'runtime_blocker':
        report.update(status='BLOCKED', blockers=['runtime_requires_review'])
    elif change == 'false_status':
        report['status'] = 'BLOCKED'
    elif change == 'parent_failure':
        report['database']['saved_response_failure_matches'] = False
    elif change == 'parent_digest':
        report['database']['grant_digest'] = 'PRIVATE_UNTRUSTED_INPUT'
    elif change == 'unresolved_action':
        report['database']['actions'][0]['state'] = 'UNCERTAIN'
    elif change == 'unknown_action':
        report['database']['actions'][0]['kind'] = 'UNEXPECTED'
    elif change == 'two_ai':
        report['database'].update(openai_count=2, action_count=2)
        report['database']['actions'] *= 2
    elif change == 'mismatched_cost':
        report['database']['actual_nano_rub'] += 1
    elif change == 'bool_cost':
        report['database']['actions'][0]['actual_nano_rub'] = True
    elif change == 'reserve':
        report['database']['reserved_nano_rub'] = 1
    elif change == 'runtime_unknown':
        report['runtime']['parent_run_done'] = False
    elif change == 'pending_runs':
        report['runtime']['unresolved_runs'] = 1
    elif change == 'container_present':
        report['container']['parent_container_absent'] = False
    elif change == 'daemon_unknown':
        report['container']['rootless_preflight_verified'] = False
    elif change == 'wrong_profile':
        config.budget_evidence = 'CHANGED_PROFILE'
    elif change == 'profile_changed':
        report['profile']['matches_original_grant'] = False
    else:
        report.pop('database')
    with pytest.raises(draft.DraftError):
        draft.build_draft(config, report, NOW)


@pytest.mark.parametrize('change', ['repository', 'credentials', 'model', 'context', 'output', 'rate',
    'old_budget', 'new_cap', 'no_tariff', 'two_call_mode'])
def test_source_scope_and_cumulative_budget_cannot_be_widened(change):
    config, report = inputs()
    if change == 'repository':
        config.synthetic_repository = 'other/acc-f2-synthetic-other'
    elif change == 'credentials':
        config.credential_files['openai'] = '/private/arbitrary-key'
    elif change == 'model':
        config.tariff.model = 'other-model'
    elif change == 'context':
        config.tariff.context_tokens += 1
    elif change == 'output':
        config.tariff.max_output_tokens += 1
    elif change == 'rate':
        config.first_experiment.payment_rub_per_usd_upper = '200'
    elif change == 'old_budget':
        report['database']['grant_budget_nano_rub'] = config.tariff.maximum()
    elif change == 'new_cap':
        config.tariff.input_nano_rub += 1
    elif change == 'no_tariff':
        config.tariff = None
    else:
        config.mode = 'http_mock'
    changed = digest(config.model_dump())
    report['profile']['profile_hash'] = report['database']['grant_profile_hash'] = changed
    with pytest.raises(draft.DraftError):
        draft.build_draft(config, report, NOW)


@pytest.fixture
def protected_files(tmp_path, monkeypatch):
    monkeypatch.setattr(draft, 'check_operator', lambda value: None)
    config, report = inputs()
    # A current observation is required even for a non-executing draft.
    report['checked_at_utc'] = datetime.now(timezone.utc).isoformat()
    source, observed, output = tmp_path / 'source.json', tmp_path / 'inspection.json', tmp_path / 'new-draft'
    source.write_text(json.dumps({**config.model_dump(), 'credential_files': config.credential_files}))
    observed.write_text(json.dumps(report))
    source.chmod(0o600)
    observed.chmod(0o600)
    return source, observed, output


def invoke(files, **kwargs):
    return draft.prepare(*(str(path) for path in files), 'f' * 40, **kwargs)


def test_plan_is_read_only_prepare_is_private_and_never_overwrites(protected_files):
    source, observed, output = protected_files
    before = source.read_bytes(), observed.read_bytes()
    plan = invoke(protected_files)
    assert plan['files_created'] is False and not output.exists()
    result = invoke(protected_files, plan_digest=plan['plan_digest'], write=True)
    assert result['files_created'] is True and output.stat().st_mode & 0o777 == 0o700
    assert {p.name for p in output.iterdir()} == {'profile.disabled.json', 'preparation.json'}
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in output.iterdir())
    stored = IntegrationConfig.model_validate_json((output / 'profile.disabled.json').read_bytes())
    assert stored.mode == 'disabled' and not stored.connected() and not stored.first_experiment.evidence
    with pytest.raises(ValueError, match='deployment_scope_invalid'):
        _configuration(output / 'profile.disabled.json', os.geteuid())
    with pytest.raises(draft.DraftError, match='existing_draft_requires_inspection'):
        invoke(protected_files, plan_digest=plan['plan_digest'], write=True)
    assert before == (source.read_bytes(), observed.read_bytes())


@pytest.mark.parametrize('change', ['profile', 'inspection', 'output', 'wrong_pin'])
def test_changed_input_or_destination_cannot_reuse_a_plan(protected_files, change):
    plan = invoke(protected_files)
    source, observed, output = protected_files
    pin = plan['plan_digest']
    if change == 'profile':
        source.write_bytes(source.read_bytes() + b'\n')
    elif change == 'inspection':
        observed.write_bytes(observed.read_bytes() + b'\n')
    elif change == 'output':
        protected_files = source, observed, output.with_name('another')
    else:
        pin = '0' * 64
    with pytest.raises(draft.DraftError, match='exact_draft_plan_required'):
        invoke(protected_files, plan_digest=pin, write=True)
    assert not output.exists()


@pytest.mark.parametrize('change', ['symlink', 'public', 'hardlink'])
def test_unsafe_input_custody_is_rejected(protected_files, change):
    source, observed, output = protected_files
    if change == 'symlink':
        alias = source.with_name('alias')
        alias.symlink_to(source)
        protected_files = alias, observed, output
    elif change == 'public':
        source.chmod(0o644)
    else:
        source.with_name('alias').hardlink_to(source)
    with pytest.raises((ValueError, draft.DraftError)):
        invoke(protected_files)
    assert not output.exists()


def test_partial_draft_is_preserved_not_removed_or_retried(protected_files, monkeypatch):
    plan = invoke(protected_files)
    original = draft.os.open
    def fail_second(path, flags, *args, **kwargs):
        if str(path).endswith('/preparation.json'):
            raise OSError('PRIVATE_WRITE_ERROR')
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(draft.os, 'open', fail_second)
    with pytest.raises(OSError):
        invoke(protected_files, plan_digest=plan['plan_digest'], write=True)
    assert (protected_files[2] / 'profile.disabled.json').exists()
    with pytest.raises(draft.DraftError, match='existing_draft_requires_inspection'):
        invoke(protected_files, plan_digest=plan['plan_digest'], write=True)


def test_cli_errors_never_echo_paths_or_untrusted_values():
    result = subprocess.run([sys.executable, str(ROOT / 'infra/vps/prepare_first_recovery_profile.py'),
        '--unexpected', 'PRIVATE_INPUT_MUST_NOT_BE_ECHOED'], capture_output=True, timeout=10)
    assert result.returncode == 2
    assert b'PRIVATE_INPUT' not in result.stdout + result.stderr


def test_cli_runtime_failure_redacts_even_known_argument_values():
    result = subprocess.run([sys.executable, str(ROOT / 'infra/vps/prepare_first_recovery_profile.py'),
        'plan', '--operator-revision', 'f' * 40, '--source-profile', '/PRIVATE_PROFILE_PATH',
        '--inspection-file', '/PRIVATE_INSPECTION_PATH', '--output-directory', '/PRIVATE_OUTPUT_PATH'],
        capture_output=True, timeout=10)
    assert result.returncode == 2
    assert b'PRIVATE_' not in result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report['state'] == 'BLOCKED' and report['files_created'] is False


def test_inspection_expiring_during_preparation_cannot_create_output(protected_files, monkeypatch):
    original = draft.datetime
    base = original.fromisoformat(json.loads(protected_files[1].read_text())['checked_at_utc'])
    times = iter((base, base, base + timedelta(seconds=301)))
    class Clock(original):
        @classmethod
        def now(cls, tz=None):
            return next(times)
    monkeypatch.setattr(draft, 'datetime', Clock)
    plan = invoke(protected_files)
    with pytest.raises(draft.DraftError, match='fresh_inspection_required'):
        invoke(protected_files, plan_digest=plan['plan_digest'], write=True)
    assert not protected_files[2].exists()


def test_input_change_during_preparation_is_rejected_before_directory_creation(protected_files, monkeypatch):
    plan = invoke(protected_files)
    calls = []
    def change_on_second_check(revision):
        calls.append(revision)
        if len(calls) == 2:
            protected_files[0].write_bytes(protected_files[0].read_bytes() + b'\n')
    monkeypatch.setattr(draft, 'check_operator', change_on_second_check)
    with pytest.raises(draft.DraftError, match='input_changed_before_write'):
        invoke(protected_files, plan_digest=plan['plan_digest'], write=True)
    assert not protected_files[2].exists()
