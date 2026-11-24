"""Restriction-only transition preserving the existing Telegram/offline voice data."""
from copy import deepcopy
import os
from pathlib import Path
import stat

from .deployment import Engine, image_check, load_bundle, source_check
from .deployment_profile import atomic_json, checksum, render, validate_manifest, validate_profile
from .deployment_voice import check_binding
from .planning_candidate import predecessor, raw_pin, read_json
from .store import digest
from .telegram_transport import TelegramConnection
from .voice_profile import VoiceProfile

PURPOSE = 'assistant-only-update.v1'
FILES = {'previous.json', 'plain.json', 'bundle.json', 'compose.json', 'connection.candidate.json'}


def assemble(previous, plain, active, voice, previous_pin, plain_pin, calendar=None):
    for bundle, pin in ((previous, previous_pin), (plain, plain_pin)):
        validate_manifest(bundle['manifest'])
        validate_profile(bundle['compose'], bundle['manifest'])
        if checksum(bundle) != pin:
            raise ValueError('assistant_exact_bundles_required')
    old, new = previous['manifest'], plain['manifest']
    fixed = ('migration_hash', 'database_image', 'redis_image', 'data_root',
             'control_uid', 'execution_uid', 'owner_login')
    if (any(old.get(k) != new.get(k) for k in fixed) or old['revision'] == new['revision']
            or new.get('assistant_only') is not True
            or not {'telegram', 'voice'} <= set(old)
            or any(k in new for k in ('voice', 'telegram', 'planning', 'first_experiment', 'calendar_script'))
            or any(k in old for k in ('planning', 'first_experiment'))):
        raise ValueError('assistant_restriction_only_transition_required')
    if (active.mode != 'live' or active.source_revision != old['revision']
            or active.token_file != '/run/telegram/token'
            or digest(active.model_dump()) != old['telegram']['connection_digest']
            or any(getattr(active, k) != old['telegram'][k] for k in ('mode', 'owner_id', 'bot_id'))):
        raise ValueError('assistant_exact_owner_connection_required')
    if (voice['model_directory'] != old['voice']['model_directory']
            or voice['model_manifest'] != old['voice']['model_manifest']
            or voice['profile_directory'] == old['voice']['profile_directory']):
        raise ValueError('assistant_existing_voice_model_required')
    staged = TelegramConnection.model_validate({**active.model_dump(), 'source_revision': new['revision']})
    target = deepcopy(plain)
    target['manifest']['telegram'] = {**old['telegram'], 'connection_digest': digest(staged.model_dump())}
    target['manifest']['voice'] = deepcopy(voice)
    if calendar is not None:
        target['manifest']['calendar_script'] = deepcopy(calendar)
    target['compose'] = render(plain['compose'], target['manifest'])
    return target, staged


def private_output(path, uid):
    path = Path(path)
    info = path.parent.stat()
    if (os.getuid() != uid or not path.is_absolute() or path.resolve() != path
            or path.exists() or path.is_symlink() or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != uid or info.st_mode & 0o077):
        raise ValueError('assistant_new_private_output_required')
    return path


def prepare_profile(previous_directory, plain_directory, profile_directory, image):
    previous, plain = load_bundle(previous_directory), load_bundle(plain_directory)
    old, new = previous['manifest'], plain['manifest']
    output = private_output(profile_directory, new['control_uid'])
    if not output.is_relative_to(Path(new['data_root']) / 'voice'):
        raise ValueError('assistant_voice_profile_outside_state')
    original = predecessor(previous, previous_directory, checksum(previous))
    profile = check_binding(old)
    staged = original[2].model_copy(update={'source_revision': new['revision']})
    updated = VoiceProfile.model_validate({**profile.model_dump(), 'source_revision': new['revision'],
                                          'connection_digest': digest(staged.model_dump())})
    voice = {**old['voice'], 'image': image, 'profile_directory': str(output),
             'profile_digest': digest(updated.model_dump())}
    assemble(previous, plain, original[2], voice, checksum(previous), checksum(plain))
    source_check(new)
    engine = Engine(new['control_uid'])
    engine.preflight()
    image_check(engine, {'voice': image, 'api': new['images']['api']}, new['revision'])
    if predecessor(previous, previous_directory, checksum(previous)) != original:
        raise ValueError('assistant_predecessor_changed')
    output.mkdir(mode=0o700)
    atomic_json(output / 'profile.json', updated.model_dump())
    return {'status': 'ASSISTANT_VOICE_PROFILE_PREPARED', 'voice': voice, 'paid_calls': 0}


def prepare(previous_directory, plain_directory, output, voice, previous_pin, plain_pin, calendar=None):
    previous, plain = load_bundle(previous_directory), load_bundle(plain_directory)
    uid = plain['manifest']['control_uid']
    output = private_output(output, uid)
    original = predecessor(previous, previous_directory, previous_pin)
    target, staged = assemble(previous, plain, original[2], voice, previous_pin, plain_pin, calendar)
    source_check(target['manifest'])
    if 'calendar_script' in target['manifest']:
        from .deployment_calendar import check_binding as check_calendar
        check_calendar(target['manifest'])
    before = check_binding(previous['manifest'])
    after = check_binding(target['manifest'])
    if after.model_dump() != {**before.model_dump(), 'source_revision': plain['manifest']['revision'],
                             'connection_digest': digest(staged.model_dump())}:
        raise ValueError('assistant_voice_permissions_changed')
    engine = Engine(uid)
    engine.preflight()
    image_check(engine, {'api': target['manifest']['images']['api'], 'voice': voice['image']},
                target['manifest']['revision'])
    if predecessor(previous, previous_directory, previous_pin) != original:
        raise ValueError('assistant_predecessor_changed')
    output.mkdir(mode=0o700)
    documents = {'previous.json': previous, 'plain.json': plain, 'bundle.json': target,
                 'compose.json': target['compose'], 'connection.candidate.json': staged.model_dump()}
    for name, value in documents.items():
        atomic_json(output / name, value)
    receipt = {'schema': 1, 'purpose': PURPOSE, 'state': 'STAGED_NOT_ACTIVATED',
        'previous_bundle': previous_pin, 'plain_bundle': plain_pin, 'candidate_bundle': checksum(target),
        'files': {k: raw_pin(v) for k, v in documents.items()}, 'paid_calls': 0,
        'deployment_authorized': False, 'task_admission_resumed': False}
    atomic_json(output / 'preparation.json', receipt)
    return {'status': 'ASSISTANT_CANDIDATE_PREPARED_NOT_APPLIED', 'candidate_bundle': checksum(target),
            'preparation_digest': checksum(receipt), 'paid_calls': 0}


def inspect(directory, candidate_pin, preparation_pin):
    path = Path(directory)
    receipt = read_json(path / 'preparation.json')
    documents = {k: read_json(path / k, 1024 * 1024) for k in FILES}
    previous, plain, saved = documents['previous.json'], documents['plain.json'], documents['bundle.json']
    target, staged = assemble(previous, plain, TelegramConnection.model_validate({
        **documents['connection.candidate.json'], 'source_revision': previous['manifest']['revision']}),
        saved['manifest']['voice'], receipt['previous_bundle'], receipt['plain_bundle'],
        saved['manifest'].get('calendar_script'))
    expected = {'schema': 1, 'purpose': PURPOSE, 'state': 'STAGED_NOT_ACTIVATED',
        'previous_bundle': receipt['previous_bundle'], 'plain_bundle': receipt['plain_bundle'],
        'candidate_bundle': checksum(target), 'files': {k: raw_pin(v) for k, v in documents.items()},
        'paid_calls': 0, 'deployment_authorized': False, 'task_admission_resumed': False}
    if (receipt != expected or checksum(receipt) != preparation_pin or checksum(target) != candidate_pin
            or saved != target or documents['compose.json'] != target['compose']
            or documents['connection.candidate.json'] != staged.model_dump()):
        raise ValueError('assistant_candidate_changed')
    allowed = FILES | {'preparation.json', 'activation.json', 'connection.previous.json'}
    if set(p.name for p in path.iterdir()) - allowed:
        raise ValueError('assistant_inventory_changed')
    for item in (path, *path.iterdir()):
        info = item.lstat()
        if (item.resolve() != item or info.st_uid != os.getuid() or info.st_mode & 0o077
                or item != path and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)):
            raise ValueError('assistant_private_custody_required')
    if 'calendar_script' in target['manifest']:
        from .deployment_calendar import check_binding as check_calendar
        check_calendar(target['manifest'])
    before, after = check_binding(previous['manifest']), check_binding(target['manifest'])
    if after.model_dump() != {**before.model_dump(), 'source_revision': plain['manifest']['revision'],
                             'connection_digest': digest(staged.model_dump())}:
        raise ValueError('assistant_voice_permissions_changed')
    if (path / 'connection.previous.json').exists():
        old_connection = {**staged.model_dump(), 'source_revision': previous['manifest']['revision']}
        if read_json(path / 'connection.previous.json') != old_connection:
            raise ValueError('assistant_previous_connection_changed')
    if (path / 'activation.json').exists():
        activation = read_json(path / 'activation.json')
        if (activation.get('purpose') != PURPOSE or activation.get('target') != candidate_pin
                or activation.get('previous') != checksum(previous)
                or activation.get('preparation_digest') != preparation_pin
                or activation.get('phase') not in {'PREPARED', 'BINDING_ACTIVE', 'DEPLOYMENT_ATTEMPTED', 'VERIFIED'}
                or activation.get('paid_calls') != 0 or activation.get('task_admission_resumed') is not False):
            raise ValueError('assistant_activation_scope_changed')
    load_bundle(path)
    source_check(target['manifest'])
    engine = Engine(target['manifest']['control_uid'])
    engine.preflight()
    image_check(engine, {'api': target['manifest']['images']['api'], 'voice': target['manifest']['voice']['image']},
                target['manifest']['revision'])
    return {'status': 'ASSISTANT_CANDIDATE_INSPECTED', 'candidate_bundle': candidate_pin,
            'preparation_digest': preparation_pin, 'paid_calls': 0, 'deployment_authorized': False}
