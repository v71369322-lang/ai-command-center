"""Offline package integrity tests; no provider, database or deployment calls."""
from copy import deepcopy
import json

import pytest

from command_center.deployment_profile import atomic_json, checksum, render
from command_center.deployment_profile import validate_profile
from command_center.planning_release import plan, prepare, verify
from command_center.store import Denied
from test_deployment import release as release


@pytest.fixture
def transition(release, tmp_path):
    original, _ = release
    previous = deepcopy(original)
    scope = {'mode': 'live', 'owner_id': 1234567, 'bot_id': 123456789,
             'connection_digest': 'c' * 64}
    previous['manifest']['telegram'] = scope
    previous['compose'] = render(original['compose'], previous['manifest'])
    candidate = deepcopy(previous)
    candidate['manifest']['revision'] = 'd' * 40
    candidate['manifest']['telegram']['connection_digest'] = 'e' * 64
    candidate['compose'] = render(original['compose'], candidate['manifest'])
    directories = []
    for name, bundle in (('previous', previous), ('candidate', candidate)):
        directory = tmp_path / name
        directory.mkdir(mode=0o700)
        atomic_json(directory / 'bundle.json', bundle)
        atomic_json(directory / 'compose.json', bundle['compose'])
        directories.append(directory)
    return previous, candidate, directories


def test_package_roundtrip_is_blocked_and_verification_is_readonly(transition, tmp_path):
    previous, candidate, directories = transition
    output = tmp_path / 'package'
    pin = prepare(*directories, output, checksum(previous), checksum(candidate))
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in output.iterdir()}
    result = verify(output, pin)
    assert result == plan(previous, candidate, checksum(previous), checksum(candidate))
    assert result['status'] == 'BLOCKED_NOT_ACTIVATABLE'
    assert not result['activation_authorized'] and not result['paid_calls_authorized']
    assert len(result['blockers']) == 5
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in output.iterdir()}
    assert output.stat().st_mode & 0o077 == 0
    assert all(p.stat().st_mode & 0o077 == 0 for p in output.iterdir())
    with pytest.raises(FileExistsError):
        prepare(*directories, output, checksum(previous), checksum(candidate))


@pytest.mark.parametrize('attack', ['candidate', 'plan', 'seal', 'extra', 'symlink',
                                   'hardlink', 'public_file', 'public_directory', 'wrong_pin'])
def test_package_tampering_rejected(transition, tmp_path, attack):
    previous, candidate, directories = transition
    output = tmp_path / 'package'
    pin = prepare(*directories, output, checksum(previous), checksum(candidate))
    path = output / 'candidate.json'
    if attack in {'candidate', 'plan', 'seal'}:
        target = output / (attack + '.json')
        target.write_bytes(target.read_bytes() + b' ')
    elif attack == 'extra':
        (output / 'unexpected').touch()
    elif attack == 'symlink':
        path.unlink()
        path.symlink_to(directories[1] / 'bundle.json')
    elif attack == 'hardlink':
        (tmp_path / 'linked').hardlink_to(path)
    elif attack == 'public_file':
        path.chmod(0o644)
    elif attack == 'public_directory':
        output.chmod(0o755)
    else:
        pin = 'f' * 64
    # Whitespace in seal is harmless: its semantic out-of-band pin still matches.
    if attack == 'seal':
        assert verify(output, pin)['status'] == 'BLOCKED_NOT_ACTIVATABLE'
    else:
        with pytest.raises((ValueError, Denied, OSError)):
            verify(output, pin)


@pytest.mark.parametrize('field', ['migration_hash', 'data_root', 'control_uid', 'owner_login'])
def test_scope_changes_require_separate_review(transition, field):
    previous, candidate, _ = transition
    candidate['manifest'][field] = {'migration_hash': 'f' * 64, 'data_root': '/other',
                                   'control_uid': 1002,
                                   'owner_login': {'origin': 'https://example.org', 'loopback_http': False}}[field]
    base = deepcopy(previous['compose'])
    del base['services']['telegram']
    candidate['compose'] = render(base, candidate['manifest'])
    with pytest.raises(ValueError, match='separate_migration_or_scope_review_required'):
        plan(previous, candidate, checksum(previous), checksum(candidate))


def test_self_resealed_authorizing_plan_still_rejected(transition, tmp_path):
    import hashlib
    previous, candidate, directories = transition
    output = tmp_path / 'package'
    prepare(*directories, output, checksum(previous), checksum(candidate))
    review = json.loads((output / 'plan.json').read_text())
    review['activation_authorized'] = True
    atomic_json(output / 'plan.json', review)
    seal = json.loads((output / 'seal.json').read_text())
    seal['files']['plan.json'] = hashlib.sha256((output / 'plan.json').read_bytes()).hexdigest()
    atomic_json(output / 'seal.json', seal)
    with pytest.raises(ValueError, match='release_package_plan_changed'):
        verify(output, checksum(seal))


@pytest.mark.parametrize('attack', ['previous_pin', 'candidate_pin', 'same_revision',
                                   'owner', 'planning_environment', 'missing_telegram'])
def test_transition_pins_and_admission_cannot_be_bypassed(transition, attack):
    previous, candidate, _ = transition
    if attack == 'same_revision':
        candidate['manifest']['revision'] = previous['manifest']['revision']
    elif attack == 'owner':
        candidate['manifest']['telegram']['owner_id'] += 1
    elif attack == 'planning_environment':
        candidate['compose']['services']['runtime-broker']['environment']['F1_PLANNING_HOST_FILE'] = '/unreviewed'
    elif attack == 'missing_telegram':
        del candidate['manifest']['telegram']
    previous_pin, candidate_pin = checksum(previous), checksum(candidate)
    if attack == 'previous_pin':
        previous_pin = 'f' * 64
    elif attack == 'candidate_pin':
        candidate_pin = 'f' * 64
    with pytest.raises(ValueError):
        plan(previous, candidate, previous_pin, candidate_pin)


@pytest.mark.parametrize('service', ['db', 'redis', 'api', 'worker', 'runtime-broker', 'watchdog', 'telegram'])
def test_existing_deployment_rejects_planning_environment_in_every_service(transition, service):
    _, candidate, _ = transition
    candidate['compose']['services'][service].setdefault('environment', {})['F1_PLANNING_PROFILE_FILE'] = '/profile'
    with pytest.raises(ValueError, match='planning_deployment_binding_not_implemented'):
        validate_profile(candidate['compose'], candidate['manifest'])


def test_interrupted_preparation_cannot_verify(transition, tmp_path, monkeypatch):
    import command_center.planning_release as package
    previous, candidate, directories = transition
    output = tmp_path / 'incomplete'
    real = package.atomic_json

    def fail_on_seal(path, value):
        if path.name == 'seal.json':
            raise OSError('simulated_interruption')
        real(path, value)

    monkeypatch.setattr(package, 'atomic_json', fail_on_seal)
    with pytest.raises(OSError, match='simulated_interruption'):
        prepare(*directories, output, checksum(previous), checksum(candidate))
    with pytest.raises(ValueError, match='release_package_inventory_changed'):
        verify(output, 'f' * 64)
