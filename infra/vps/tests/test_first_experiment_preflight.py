"""Offline profile inspection: no credentials, network, database or authority."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import httpx
import pytest

from command_center.coding.first_experiment import CAP, CALLS, MODEL, REQUIRED, Evidence, FirstExperiment
from command_center.coding.contract import CodingRequest
from command_center.coding.gateway import Gateway
from command_center.coding.integration_config import FileCredentials, IntegrationConfig, Tariff
from command_center.store import Denied, Store, digest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('offline_experiment_preflight', ROOT / 'scripts/first_experiment_preflight.py')
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)
NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


def profile():
    # Public synthetic numbers and declarations, never real account evidence.
    experiment = FirstExperiment(payment_rub_per_usd_upper='90', extra_rub_upper='0',
        existing_credit_usd='1', repository_id=725000001,
        evidence={key: Evidence(reference='PUBLIC_FIXTURE_ONLY', expires_at=(NOW + timedelta(hours=1)).isoformat())
                  for key in REQUIRED})
    return IntegrationConfig(mode='live', live_authorized=True, first_experiment=experiment,
        synthetic_repository='fixture/acc-f2-synthetic-preflight',
        budget_evidence='PUBLIC_FIXTURE_ONLY', daily_nano_rub=CAP, monthly_nano_rub=CAP,
        credential_files={'openai': '/not-read/openai', 'github-installation-token': '/not-read/github'},
        tariff=Tariff(model=MODEL, input_nano_rub=67500, output_nano_rub=405000,
                      context_tokens=400000, max_output_tokens=2048, confirmed=True,
                      evidence='PUBLIC_FIXTURE_ONLY'))


@pytest.fixture(autouse=True)
def no_authority_or_external_access(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('offline inspector attempted a credential/client/database/authorization action')
    monkeypatch.setattr(FileCredentials, 'get', forbidden)
    monkeypatch.setattr(Gateway, '__init__', forbidden)
    monkeypatch.setattr(Gateway, 'authorize', forbidden)
    monkeypatch.setattr(Store, '__init__', forbidden)
    monkeypatch.setattr(Store, 'approve', forbidden)
    monkeypatch.setattr(httpx, 'Client', forbidden)


def test_recovery_local_declarations_use_one_call_without_claiming_parent_verification():
    from command_center.coding.recovery import RECOVERY_CAP, RecoveryExperiment
    config = profile()
    config.first_experiment = RecoveryExperiment.model_validate({**config.first_experiment.model_dump(),
        'id': 'f2.2-recovery-1', 'original_task_id': '11111111-2222-4333-8444-555555555555',
        'original_grant_digest': 'c' * 64})
    report = preflight.inspect_config(config, NOW)
    assert report['status'] == 'LOCAL_CHECKS_PASSED'
    assert report['max_calls'] == 1 and report['max_budget_nano_rub'] == RECOVERY_CAP
    assert report['configured_reservation_nano_rub'] == config.tariff.maximum()
    assert report['live_call_allowed'] is False and report['remote_state_verified'] is False
    assert config.first_experiment.report(NOW)['parent_state_verified'] is False


def test_valid_local_declarations_never_grant_live_permission_or_claim_remote_verification():
    config = profile()
    original = config.model_dump(), dict(config.credential_files)
    report = preflight.inspect_config(config, NOW)
    assert report['status'] == 'LOCAL_CHECKS_PASSED' and report['blockers'] == []
    assert report['profile_hash'] == digest(config.model_dump())
    assert report['configured_two_call_reservation_nano_rub'] == config.tariff.maximum() * CALLS
    assert report['proposed_task_budget_nano_rub'] < CAP
    assert report['live_call_allowed'] is report['final_owner_approval_verified'] is report['remote_state_verified'] is False
    assert report['credential_values_read'] is False and report['external_calls'] == 0
    assert report['provider_hard_cap_verified'] is False
    assert 'exact_final_owner_approval' in report['requires_separate_verification']
    assert original == (config.model_dump(), config.credential_files)
    # Inspection cannot turn the original production consent guard off.
    with pytest.raises(Denied, match='final_confirmation_required'):
        config.first_experiment.validate_scope(config,
            CodingRequest(provider='openai', experiment_id=config.first_experiment.id).model_dump(),
            report['proposed_task_budget_nano_rub'], NOW)


@pytest.mark.parametrize('gate', REQUIRED)
@pytest.mark.parametrize('expired', [False, True])
def test_each_missing_or_expired_evidence_is_a_local_blocker(gate, expired):
    config = profile()
    if expired:
        config.first_experiment.evidence[gate] = Evidence(reference='PUBLIC_FIXTURE_ONLY',
            expires_at=(NOW - timedelta(seconds=1)).isoformat())
    else:
        del config.first_experiment.evidence[gate]
    report = preflight.inspect_config(config, NOW)
    assert report['status'] == 'BLOCKED'
    assert 'evidence_missing_or_expired:' + gate in report['blockers']
    assert report['live_call_allowed'] is False


@pytest.mark.parametrize('change,code', [
    ('disabled', 'live_mode_required'), ('http_mock', 'live_mode_required'),
    ('operator_flag', 'operator_live_flag_missing'), ('no_experiment', 'first_experiment_profile_required'),
    ('no_repository', 'synthetic_repository_missing'), ('no_budget_evidence', 'connection_settings_incomplete'),
    ('no_tariff', 'budget_unconfirmed'), ('unconfirmed_tariff', 'budget_unconfirmed'),
    ('no_daily_budget', 'budget_unconfirmed'), ('daily_capacity', 'two_call_reservation_exceeds_configured_capacity'),
    ('monthly_capacity', 'invalid_task_budget'), ('daily_over_cap', 'first_experiment_global_budget'),
    ('monthly_over_cap', 'first_experiment_global_budget'), ('underpriced', 'first_experiment_underpriced_profile'),
    ('fixed_fee', 'first_experiment_total_cost_bound'), ('model', 'first_experiment_tariff_mismatch'),
    ('output', 'first_experiment_tariff_mismatch'), ('context', 'first_experiment_context_bound'),
    ('overpriced', 'first_experiment_scope_or_budget'),
    ('fractional_fx', 'first_experiment_underpriced_profile'),
])
def test_config_and_integer_reservation_must_pass_existing_production_scope_validation(change, code):
    config = profile()
    maximum = config.tariff.maximum() * CALLS
    if change in {'disabled', 'http_mock'}:
        config.mode = change
    elif change == 'operator_flag':
        config.live_authorized = False
    elif change == 'no_experiment':
        config.first_experiment = None
    elif change == 'no_repository':
        config.synthetic_repository = ''
    elif change == 'no_budget_evidence':
        config.budget_evidence = ''
    elif change == 'no_tariff':
        config.tariff = None
    elif change == 'unconfirmed_tariff':
        config.tariff.confirmed = False
    elif change == 'no_daily_budget':
        config.daily_nano_rub = 0
    elif change == 'daily_capacity':
        config.daily_nano_rub = maximum - 1
    elif change == 'monthly_capacity':
        config.monthly_nano_rub = maximum - 1
    elif change == 'daily_over_cap':
        config.daily_nano_rub = CAP + 1
    elif change == 'monthly_over_cap':
        config.monthly_nano_rub = CAP + 1
    elif change == 'underpriced':
        config.tariff.input_nano_rub -= 1
    elif change == 'fixed_fee':
        config.first_experiment.extra_rub_upper = '1'
    elif change == 'model':
        config.tariff.model = 'PRIVATE_MARKER_MUST_NOT_APPEAR'
    elif change == 'output':
        config.tariff.max_output_tokens = 4096
    elif change == 'context':
        config.tariff.context_tokens = 8192
    elif change == 'overpriced':
        config.tariff.input_nano_rub = 1_000_000
    elif change == 'fractional_fx':
        config.first_experiment.payment_rub_per_usd_upper = '90.000000001'
    report = preflight.inspect_config(config, NOW)
    assert report['status'] == 'BLOCKED' and code in report['blockers']
    assert 'PRIVATE_MARKER_MUST_NOT_APPEAR' not in json.dumps(report)


def test_minimal_two_call_capacity_is_sufficient_without_reserving_full_owner_ceiling():
    config = profile()
    maximum = config.tariff.maximum() * CALLS
    config.daily_nano_rub = config.monthly_nano_rub = maximum
    report = preflight.inspect_config(config, NOW)
    assert report['status'] == 'LOCAL_CHECKS_PASSED'
    assert report['proposed_task_budget_nano_rub'] == maximum < CAP


@pytest.mark.parametrize('change', ['missing', 'empty', 'same_alias', 'same_path'])
def test_credential_references_are_present_separate_and_never_opened(change):
    config = profile()
    if change == 'missing':
        del config.credential_files['openai']
    elif change == 'empty':
        config.credential_files['openai'] = ''
    elif change == 'same_alias':
        config.github_secret_ref = config.openai_secret_ref
    else:
        config.credential_files['github-installation-token'] = config.credential_files['openai']
    report = preflight.inspect_config(config, NOW)
    assert report['status'] == 'BLOCKED'
    expected = 'credential_references_missing' if change in {'missing', 'empty'} else 'separate_provider_credentials_required'
    assert expected in report['blockers']


@pytest.mark.parametrize('field,value,gate', [
    ('payment_rub_per_usd_upper', '200', 'payment_bound'),
    ('payment_rub_per_usd_upper', 'NaN', 'payment_bound'),
    ('extra_rub_upper', '100', 'payment_bound'),
    ('existing_credit_usd', '0', 'existing_funding'),
    ('existing_credit_usd', 'NaN', 'existing_funding'),
    ('repository_id', None, 'repository'),
])
def test_unknown_or_insufficient_money_or_repository_identity_cannot_pass(field, value, gate):
    config = profile()
    setattr(config.first_experiment, field, value)
    report = preflight.inspect_config(config, NOW)
    assert report['status'] == 'BLOCKED' and 'evidence_missing_or_expired:' + gate in report['blockers']


def test_only_selected_json_configuration_is_read_and_references_never_leak(tmp_path, monkeypatch, capsys):
    config = profile()
    marker = 'PRIVATE_INPUT_MARKER_NOT_FOR_OUTPUT'
    config.synthetic_repository = 'private-owner/acc-f2-synthetic-' + marker
    config.budget_evidence = marker
    config.tariff.evidence = marker
    for evidence in config.first_experiment.evidence.values():
        evidence.reference = marker
    config.credential_files = {'openai': str(tmp_path / (marker + '-openai')),
                               'github-installation-token': str(tmp_path / (marker + '-github'))}
    path = tmp_path / 'profile.json'
    data = json.dumps({**config.model_dump(), 'credential_files': config.credential_files})
    path.write_text(data)
    opened = []
    original = Path.open
    def guarded_open(self, *args, **kwargs):
        assert str(self) not in config.credential_files.values(), 'credential path opened'
        opened.append(self)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded_open)
    original_fd_open = os.open
    def guarded_fd_open(selected, *args, **kwargs):
        # The pinned loader uses O_NOFOLLOW descriptors; retain the no-key-read
        # assertion for both pathlib and descriptor-based access paths.
        assert str(selected) not in config.credential_files.values(), 'credential path opened'
        opened.append(Path(selected))
        return original_fd_open(selected, *args, **kwargs)
    monkeypatch.setattr(os, 'open', guarded_fd_open)
    monkeypatch.setenv('F2_INTEGRATION_CONFIG_FILE', str(path))
    monkeypatch.setattr(sys, 'argv', ['preflight'])
    monkeypatch.setattr(preflight, 'datetime', SimpleNamespace(now=lambda zone: NOW))
    assert preflight.main() == 0
    output = capsys.readouterr()
    assert output.err == '' and marker not in output.out and str(tmp_path) not in output.out
    report = json.loads(output.out)
    assert report['live_call_allowed'] is False and report['profile_hash'] == digest(config.model_dump())
    assert opened == [path]


@pytest.mark.parametrize('failure', ['missing', 'malformed', 'oversized', 'symlink', 'crm_scope'])
def test_cli_unreadable_or_invalid_configuration_is_redacted_blocked(tmp_path, monkeypatch, capsys, failure):
    path = tmp_path / 'PRIVATE_PATH_NOT_FOR_OUTPUT'
    if failure == 'malformed':
        path.write_text('{"PRIVATE_VALUE_NOT_FOR_OUTPUT":true}')
    elif failure == 'oversized':
        path.write_text('x' * 16385)
    elif failure == 'symlink':
        path.symlink_to(tmp_path / 'absent')
    elif failure == 'crm_scope':
        path.write_text('{"synthetic_repository":"private-owner/production-crm"}')
    monkeypatch.setenv('F2_INTEGRATION_CONFIG_FILE', str(path))
    monkeypatch.setattr(sys, 'argv', ['preflight'])
    assert preflight.main() == 2
    result = capsys.readouterr()
    report = json.loads(result.out)
    assert report['status'] == 'BLOCKED' and report['blockers'] == ['invalid_or_unreadable_profile']
    assert report['final_owner_approval_verified'] is report['remote_state_verified'] is False
    assert report['provider_hard_cap_verified'] is report['live_call_allowed'] is False
    assert not result.err and 'PRIVATE_' not in result.out and 'production-crm' not in result.out


def test_unknown_cli_arguments_are_never_echoed(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['preflight', '--secret', 'PRIVATE_ARGUMENT_NOT_FOR_OUTPUT'])
    with pytest.raises(SystemExit) as error:
        preflight.main()
    assert error.value.code == 2
    output = capsys.readouterr()
    assert not output.out and output.err == 'invalid preflight arguments; values not displayed\n'


def test_committed_template_and_actual_default_cli_stay_closed_without_network():
    template = ROOT / 'infra/vps/first-experiment.disabled.json'
    data = template.read_bytes()
    config = IntegrationConfig.model_validate_json(data)
    assert config.mode == 'disabled' and config.live_authorized is False and not config.credential_files
    assert config.first_experiment.evidence == {} and config.first_experiment.repository_id is None
    env = {key: value for key, value in os.environ.items() if key not in {'F2_INTEGRATION_CONFIG_FILE', 'PYTHONPATH'}}
    env['PYTHONPATH'] = str(ROOT / 'src')
    for selected in [None, str(template)]:
        if selected:
            env['F2_INTEGRATION_CONFIG_FILE'] = selected
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/first_experiment_preflight.py')],
                                env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode == 2 and result.stderr == ''
        report = json.loads(result.stdout)
        assert report['status'] == 'BLOCKED' and 'live_mode_required' in report['blockers']
        assert report['live_call_allowed'] is False and report['external_calls'] == 0
    assert template.read_bytes() == data
