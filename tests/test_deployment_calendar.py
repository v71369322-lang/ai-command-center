from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from command_center import assistant_candidate as candidate
from command_center.deployment_calendar import KEY, check_binding
from command_center.deployment_profile import atomic_json, checksum, render, validate_manifest, validate_profile
from command_center.google_script_calendar import ScriptCalendarProfile, ScriptRuntimeConfig
from command_center.store import Denied, digest
from test_assistant_candidate import assistant_release as assistant_release
from test_voice_release import voice_release as voice_release
from test_deployment import release as release


def binding(plain, owner):
    directory = Path(plain['manifest']['data_root']) / 'calendar/v1'
    directory.parent.mkdir(mode=0o700)
    directory.mkdir(mode=0o700)
    key = bytes.fromhex('ab' * 32)  # Public synthetic fixture, never a live credential.
    profile = ScriptCalendarProfile(enabled=True, owner_id=owner,
        source_revision=plain['manifest']['revision'], deployment_id='synthetic_deployment_id_123',
        connection_id='d' * 64, key_fingerprint=hashlib.sha256(key).hexdigest())
    config = ScriptRuntimeConfig(profile=profile, key_file=KEY)
    atomic_json(directory / 'connection.json', config.model_dump())
    (directory / 'calendar.key').write_bytes(key)
    (directory / 'calendar.key').chmod(0o600)
    return {'directory': str(directory), 'profile': profile.model_dump(), 'config_sha256': digest(config.model_dump())}


@pytest.mark.parametrize('already_assistant', [False, True])
def test_calendar_candidate_preserves_identity_and_only_telegram_reads_key(assistant_release, already_assistant):
    args, old, plain, active, _ = assistant_release
    if already_assistant:
        old['manifest']['assistant_only'] = True
        old['manifest']['images'] = {'api': old['manifest']['images']['api']}
        old['compose'] = render(plain['compose'], old['manifest'])
    calendar = binding(plain, active.owner_id)
    target, staged = candidate.assemble(old, plain, active, args['voice'], checksum(old), checksum(plain), calendar)
    check_binding(target['manifest'])
    assert staged.owner_id == active.owner_id and staged.bot_id == active.bot_id
    assert set(target['compose']['services']) == {'db', 'redis', 'api', 'telegram', 'voice'}
    for name, service in target['compose']['services'].items():
        mounts = [v for v in service.get('volumes', []) if v['target'].startswith('/run/calendar')]
        assert bool(mounts) == (name == 'telegram')
        assert all(v['read_only'] for v in mounts)
    telegram = target['compose']['services']['telegram']
    assert telegram['command'][-4:] == ['--calendar-script-config', '/run/calendar/connection.json',
                                      '--approved-calendar', calendar['config_sha256']]
    assert '/run/calendar:rw,noexec,nosuid,nodev,size=16k,mode=0700' in telegram['tmpfs']


@pytest.mark.parametrize('attack', ['owner', 'revision', 'config_pin', 'directory', 'enabled', 'key', 'config', 'mode', 'symlink'])
def test_calendar_rejects_changed_binding_or_custody(assistant_release, attack):
    args, old, plain, active, _ = assistant_release
    calendar = binding(plain, active.owner_id)
    target, _ = candidate.assemble(old, plain, active, args['voice'], checksum(old), checksum(plain), calendar)
    changed = target['manifest']['calendar_script']
    if attack in {'owner', 'revision', 'enabled'}:
        key, value = {'owner': ('owner_id', active.owner_id + 1), 'revision': ('source_revision', 'e' * 40),
                      'enabled': ('enabled', False)}[attack]
        changed['profile'][key] = value
    elif attack == 'config_pin':
        changed['config_sha256'] = '0' * 64
    elif attack == 'directory':
        changed['directory'] = str(Path(plain['manifest']['data_root']) / 'telegram')
    else:
        path = Path(calendar['directory']) / ('connection.json' if attack == 'config' else 'calendar.key')
        if attack == 'mode':
            path.chmod(0o644)
        elif attack == 'symlink':
            path.rename(path.with_suffix('.old'))
            path.symlink_to(path.with_suffix('.old'))
        else:
            path.write_bytes(b'changed')
    with pytest.raises((ValueError, OSError, Denied)):
        check_binding(target['manifest'])


def test_profile_rejects_writable_or_extra_calendar_mount(assistant_release):
    args, old, plain, active, _ = assistant_release
    target, _ = candidate.assemble(old, plain, active, args['voice'], checksum(old), checksum(plain),
                                  binding(plain, active.owner_id))
    validate_manifest(target['manifest'])
    changed = deepcopy(target['compose'])
    changed['services']['telegram']['volumes'][-1]['read_only'] = False
    with pytest.raises(ValueError, match='telegram_service_boundary_changed'):
        validate_profile(changed, target['manifest'])


@pytest.mark.parametrize('already_assistant', [False, True])
def test_prepare_inspect_rechecks_calendar_without_network_or_activation(assistant_release, already_assistant):
    args, old, plain, active, _ = assistant_release
    if already_assistant:
        old['manifest']['assistant_only'] = True
        old['manifest']['images'] = {'api': old['manifest']['images']['api']}
        old['compose'] = render(plain['compose'], old['manifest'])
        args['previous_pin'] = checksum(old)
        atomic_json(args['previous_directory'] / 'bundle.json', old)
        atomic_json(args['previous_directory'] / 'compose.json', old['compose'])
        atomic_json(Path(old['manifest']['data_root']) / 'deployment.json', {
            'phase': 'VERIFIED', 'bundle': checksum(old), 'revision': old['manifest']['revision'],
            'directory': str(args['previous_directory'])})
        atomic_json(args['previous_directory'] / 'activation.json', {'phase': 'VERIFIED', 'target': checksum(old)})
    calendar = binding(plain, active.owner_id)
    before = (Path(old['manifest']['data_root']) / 'deployment.json').read_bytes()
    result = candidate.prepare(**args, calendar=calendar)
    candidate.inspect(args['output'], result['candidate_bundle'], result['preparation_digest'])
    assert (Path(old['manifest']['data_root']) / 'deployment.json').read_bytes() == before
    assert not (args['output'] / 'activation.json').exists()
    (Path(calendar['directory']) / 'calendar.key').write_bytes(b'changed')
    with pytest.raises(ValueError, match='calendar_custody_changed'):
        candidate.inspect(args['output'], result['candidate_bundle'], result['preparation_digest'])


@pytest.mark.parametrize('attack', [None, 'command', 'key_writable', 'key_missing'])
def test_actual_telegram_runtime_calendar_boundary(assistant_release, attack):
    from command_center.assistant_runtime import check_runtime
    args, old, plain, active, _ = assistant_release
    target, _ = candidate.assemble(old, plain, active, args['voice'], checksum(old), checksum(plain),
                                  binding(plain, active.owner_id))
    m = target['manifest']
    service = target['compose']['services']['telegram']
    metadata = {'Image': m['images']['api'],
        'Config': {'User': '0:0', 'Cmd': service['command'][:],
                   'Env': [k + '=' + str(v) for k, v in service['environment'].items()]},
        'HostConfig': {'IpcMode': 'private', 'ReadonlyRootfs': True, 'CapDrop': ['ALL'],
                       'SecurityOpt': ['no-new-privileges'], 'Memory': 256 * 1024**2,
                       'NanoCpus': 250000000, 'PidsLimit': 32},
        'NetworkSettings': {'Networks': {'acc-f23_' + k: {} for k in service['networks']}},
        'Mounts': [{'Source': v['source'], 'Destination': v['target'], 'RW': False}
                   for v in service['volumes']] + [{'Source': str(Path(m['data_root']) / 'secrets/db_password'),
                                                    'Destination': '/run/secrets/db_password', 'RW': False}]}
    if attack == 'command':
        metadata['Config']['Cmd'][-1] = '0' * 64
    elif attack == 'key_writable':
        metadata['Mounts'][-2]['RW'] = True
    elif attack == 'key_missing':
        metadata['Mounts'].pop(-2)
    if attack:
        with pytest.raises(ValueError):
            check_runtime(m, 'telegram', metadata, service)
    else:
        check_runtime(m, 'telegram', metadata, service)
