"""Exact decimal conversion and private unbound profiles, no credentials or provider calls."""
from fractions import Fraction
import hashlib
import json

import pytest

from command_center import planning_operator as operator
from command_center.deployment_profile import atomic_json, checksum
from command_center.store import Denied
from test_deployment import release as release
from test_planning_admission import profile as profile
from test_planning_candidate import inputs as inputs


@pytest.fixture
def reviewed():
    return {'purpose': 'planning-profile-evidence.v1', 'reviewed': True, 'model': 'PUBLIC_TEST_MODEL',
        'pricing_currency': 'USD', 'usd_input_upper_per_million': '0.125',
        'usd_output_upper_per_million': '0.50', 'usd_fixed_upper_per_request': '0',
        'rub_per_usd_upper': '100', 'pricing_evidence': 'PUBLIC_SYNTHETIC_PRICE_REFERENCE',
        'fx_evidence': 'PUBLIC_SYNTHETIC_FX_REFERENCE', 'available_rub': '75',
        'per_plan_limit_rub': '1', 'daily_limit_rub': '10', 'monthly_limit_rub': '50',
        'context_tokens': 8192, 'max_output_tokens': 4096,
        'evidence': {'account': 'SYNTHETIC_ACCOUNT', 'model': 'SYNTHETIC_MODEL',
            'funding': 'SYNTHETIC_FUNDING', 'data_sharing': 'SYNTHETIC_DATA_SHARING',
            'observed_at': 1000, 'expires_at': 2000}}


@pytest.fixture
def files(reviewed, tmp_path, monkeypatch):
    directory = tmp_path / 'input'
    directory.mkdir(mode=0o700)
    path = directory / 'operator-evidence.json'
    atomic_json(path, reviewed)
    monkeypatch.setattr(operator.time, 'time', lambda: 1500)
    return path, hashlib.sha256(path.read_bytes()).hexdigest(), tmp_path / 'output'


def test_known_conversion_is_unbound_and_not_paid_authority(reviewed):
    profile, report = operator.convert(reviewed, now=1500)
    assert profile.tariff.input_nano_rub == 12500 and profile.tariff.output_nano_rub == 50000
    assert profile.tariff.maximum() == 307200000
    assert profile.runtime is None and report['rounding'] == 'rates_up_limits_down'
    assert profile.available_nano_rub == 75 * 10**9
    assert profile.daily_nano_rub == 10 * 10**9 and profile.monthly_nano_rub == 50 * 10**9
    assert not report['paid_calls_authorized'] and not report['deployment_authorized']


@pytest.mark.parametrize('rate', ['0.000000000001', '0.125', '0.333333333333'])
@pytest.mark.parametrize('fx', ['0.000000001', '94.123456789123', '100'])
def test_rate_ceiling_matches_independent_rational_bound(reviewed, rate, fx):
    reviewed.update(usd_input_upper_per_million=rate, rub_per_usd_upper=fx)
    profile, _ = operator.convert(reviewed, now=1500)
    exact = Fraction(rate) * Fraction(fx) * 1000
    expected = (exact.numerator + exact.denominator - 1) // exact.denominator
    assert profile.tariff.input_nano_rub == expected


def test_limits_round_down_and_per_plan_ceiling_is_preserved(reviewed):
    for key in ('available_rub', 'per_plan_limit_rub', 'daily_limit_rub', 'monthly_limit_rub'):
        reviewed[key] += '.000000000999'
    profile, report = operator.convert(reviewed, now=1500)
    assert profile.available_nano_rub == 75 * 10**9
    assert report['ceilings_nano_rub']['per_plan_limit_rub'] == 10**9
    reviewed['per_plan_limit_rub'] = '0.307199999999'
    with pytest.raises(ValueError, match='reviewed_operator_inputs_invalid'):
        operator.convert(reviewed, now=1500)


@pytest.mark.parametrize('field,value', [('reviewed', False), ('reviewed', 1),
    ('usd_input_upper_per_million', 0.125), ('usd_input_upper_per_million', 'NaN'),
    ('usd_output_upper_per_million', '-1'), ('rub_per_usd_upper', '0'),
    ('rub_per_usd_upper', '1e2'), ('available_rub', '0'), ('monthly_limit_rub', '100.000000001'),
    ('pricing_currency', 'RUB'), ('context_tokens', 8191), ('max_output_tokens', 4097)])
def test_unreviewed_or_ambiguous_values_never_create_profile(reviewed, field, value):
    reviewed[field] = value
    with pytest.raises(ValueError, match='reviewed_operator_inputs_invalid'):
        operator.convert(reviewed, now=1500)


@pytest.mark.parametrize('now', [999, 2000, 3000])
def test_evidence_window_is_not_refreshed(reviewed, now):
    with pytest.raises(ValueError):
        operator.convert(reviewed, now=now)


def test_private_creation_inspection_and_no_network_or_authority(files, monkeypatch):
    path, pin, output = files
    monkeypatch.setattr('httpx.Client', lambda *a, **k: pytest.fail('HTTP in operator conversion'))
    monkeypatch.setattr('command_center.store.Store.__init__', lambda *a, **k: pytest.fail('DB in operator conversion'))
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    result = operator.prepare(path, pin, output)
    snapshots = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in output.iterdir()}
    report = operator.inspect_profile(output, result['creation_digest'])
    assert report['profile_sha256'] == result['profile_sha256']
    assert not report['runtime_bound'] and not report['paid_calls_authorized']
    assert snapshots == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in output.iterdir()}
    assert before == (path.read_bytes(), path.stat().st_mtime_ns)
    assert all(p.stat().st_mode & 0o077 == 0 for p in [output, *output.iterdir()])
    with pytest.raises(FileExistsError):
        operator.prepare(path, pin, output)


@pytest.mark.parametrize('attack', ['wrong_pin', 'changed_input', 'symlink', 'hardlink', 'file_mode', 'parent_mode', 'key_filename'])
def test_input_custody_and_exact_pin(files, attack):
    path, pin, output = files
    if attack == 'wrong_pin':
        pin = 'f' * 64
    elif attack == 'changed_input':
        path.write_bytes(path.read_bytes() + b' ')
    elif attack == 'symlink':
        target = path.with_name('original.json')
        path.rename(target)
        path.symlink_to(target)
    elif attack == 'hardlink':
        path.with_name('link').hardlink_to(path)
    elif attack == 'file_mode':
        path.chmod(0o644)
    elif attack == 'parent_mode':
        path.parent.chmod(0o755)
    else:
        target = path.with_name('openai.key')
        path.rename(target)
        path = target
    with pytest.raises((ValueError, Denied, OSError)):
        operator.prepare(path, pin, output)
    assert not output.exists()


def test_template_is_incomplete_and_diagnostics_do_not_echo_secrets(files):
    path, _, _ = files
    template = operator.template()
    marker = 'sk-proj-PUBLIC_SYNTHETIC_NOT_A_REAL_KEY_12345'
    template[marker] = marker
    atomic_json(path, template)
    report = operator.inspect_input(path)
    assert report['status'] == 'OPERATOR_INPUT_INCOMPLETE_OR_INVALID'
    assert marker not in json.dumps(report)
    with pytest.raises(ValueError):
        operator.convert(template, now=1500)


@pytest.mark.parametrize('attack', ['profile', 'conversion', 'extra', 'creation_pin', 'rebound_profile'])
def test_inspection_rejects_changed_artifacts(files, attack):
    path, pin, output = files
    result = operator.prepare(path, pin, output)
    if attack in {'profile', 'conversion'}:
        target = output / (attack + '.json')
        target.write_bytes(target.read_bytes() + b' ')
    elif attack == 'extra':
        (output / 'unexpected').touch()
    elif attack == 'creation_pin':
        result['creation_digest'] = 'f' * 64
    else:
        document = json.loads((output / 'profile.json').read_bytes())
        document['runtime'] = {'source_revision': 'a' * 40, 'binding_digest': 'b' * 64, 'credential_sha256': 'c' * 64}
        atomic_json(output / 'profile.json', document)
        receipt = json.loads((output / 'creation.json').read_bytes())
        receipt['files']['profile.json'] = operator.profile_pin(document)
        atomic_json(output / 'creation.json', receipt)
        result['creation_digest'] = checksum(receipt)
    with pytest.raises((ValueError, Denied, OSError)):
        operator.inspect_profile(output, result['creation_digest'])


def test_created_profile_flows_into_existing_candidate_without_manual_edits(files, inputs, monkeypatch):
    from command_center import planning_candidate as candidate
    path, pin, output = files
    monkeypatch.setattr('httpx.Client', lambda *a, **k: pytest.fail('HTTP in profile/candidate pipeline'))
    result = operator.prepare(path, pin, output)
    options = inputs[0]
    options.update(operator_file=output / 'profile.json', operator_pin=result['profile_sha256'])
    staged = candidate.prepare(**options)
    verification = candidate.inspect(options['output'], staged['candidate_bundle'], staged['preparation_digest'])
    assert verification['status'] == 'PLANNING_CANDIDATE_INTEGRITY_VERIFIED_NOT_ACTIVATED'
    bound, _ = candidate.check_binding(candidate.load_bundle(options['output'])['manifest'])
    unbound = json.loads((output / 'profile.json').read_bytes())
    assert unbound['runtime'] is None and bound.runtime is not None
    assert bound.tariff.model_dump() == unbound['tariff']
    assert bound.tariff.maximum() == result['maximum_nano_rub']
