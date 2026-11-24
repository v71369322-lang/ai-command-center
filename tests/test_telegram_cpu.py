from copy import deepcopy

import pytest

from command_center import assistant_candidate as candidate
from command_center.deployment_profile import checksum, render, validate_manifest, validate_profile
from test_assistant_candidate import assistant_release as assistant_release
from test_voice_release import voice_release as voice_release
from test_deployment import release as release


@pytest.mark.parametrize('already_budgeted', [False, True])
def test_cpu_budget_is_explicit_and_legacy_predecessor_stays_valid(assistant_release, already_budgeted):
    args, old, plain, active, _ = assistant_release
    if already_budgeted:
        old['manifest'].update(assistant_only=True, telegram_cpu=1)
        old['manifest']['images'] = {'api': old['manifest']['images']['api']}
        old['compose'] = render(plain['compose'], old['manifest'])
    before = deepcopy(old)
    target, _ = candidate.assemble(old, plain, active, args['voice'], checksum(old), checksum(plain),
                                  telegram_cpu=None if already_budgeted else 1)
    assert old == before
    validate_manifest(old['manifest'])
    validate_profile(old['compose'], old['manifest'])
    assert old['compose']['services']['telegram']['cpus'] == (1 if already_budgeted else .25)
    service = target['compose']['services']['telegram']
    assert service['cpus'] == 1 and service['mem_limit'] == '256m' and service['pids_limit'] == 32
    assert service['networks'] == old['compose']['services']['telegram']['networks']
    assert target['manifest']['telegram_cpu'] == 1
    changed = deepcopy(target['compose'])
    changed['services']['telegram']['cpus'] = .25
    with pytest.raises(ValueError, match='telegram_service_boundary_changed'):
        validate_profile(changed, target['manifest'])


@pytest.mark.parametrize('value', [True, False, 0, 2, 1.0, '1', None])
def test_cpu_budget_cannot_be_arbitrarily_expanded(assistant_release, value):
    args, old, plain, active, _ = assistant_release
    target, _ = candidate.assemble(old, plain, active, args['voice'], checksum(old), checksum(plain))
    target['manifest']['telegram_cpu'] = value
    with pytest.raises(ValueError, match='telegram_exact_assistant_cpu_required'):
        validate_manifest(target['manifest'])
