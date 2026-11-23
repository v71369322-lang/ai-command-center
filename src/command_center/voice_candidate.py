"""Prepare/inspect a first offline-voice addition without activating it."""
from copy import deepcopy
from datetime import datetime
import os
from pathlib import Path
import stat

from .deployment import Engine, image_check, load_bundle, source_check
from .deployment_profile import atomic_json, checksum, render, validate_manifest, validate_profile
from .deployment_voice import check_binding
from .planning_candidate import predecessor, raw_pin, read_json
from .store import digest
from .telegram_transport import TelegramConnection
from .offline_speech import verify_model
from .voice_profile import VoiceProfile

PURPOSE = 'offline-voice-update.v1'
FILES = {'previous.json', 'plain.json', 'bundle.json', 'compose.json', 'connection.candidate.json'}


def prepare_profile(previous_directory, plain_directory, profile_directory, model_directory,
                    image, since, model_manifest):
    """Create a new private profile only; never replace live bindings or start a worker."""
    from .telegram_transport import connection
    previous, plain = load_bundle(previous_directory), load_bundle(plain_directory)
    old, new = previous['manifest'], plain['manifest']
    root = Path(new['data_root'])
    output = Path(profile_directory)
    info = output.parent.stat()
    when = datetime.fromisoformat(since)
    if (os.getuid() != new['control_uid'] or not output.is_absolute() or output.resolve() != output
            or output.exists() or not output.is_relative_to(root / 'voice')
            or output.is_symlink() or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid() or info.st_mode & 0o077
            or when.tzinfo is None or when.utcoffset() is None):
        raise ValueError('voice_new_private_profile_and_cutoff_required')
    active = connection(Path(old['data_root']) / 'telegram/connection.json')
    staged = active.model_copy(update={'source_revision': new['revision']})
    verify_model(model_directory, model_manifest)
    profile = VoiceProfile(enabled=True, connection_file='/run/telegram/connection.json',
        connection_digest=digest(staged.model_dump()), source_revision=new['revision'],
        model_directory='/models/whisper-base', model_manifest=model_manifest, since=since)
    voice = {'image': image, 'profile_directory': str(output), 'profile_digest': digest(profile.model_dump()),
             'model_directory': str(Path(model_directory)), 'model_manifest': model_manifest}
    target, _ = assemble(previous, plain, active, voice, checksum(previous), checksum(plain))
    output.mkdir(mode=0o700)
    atomic_json(output / 'profile.json', profile.model_dump())
    check_binding(target['manifest'])
    return {'status': 'VOICE_PROFILE_PREPARED_NOT_ACTIVATED', 'voice': voice,
            'profile_digest': digest(profile.model_dump()), 'paid_calls': 0}


def assemble(previous, plain, active, voice, previous_pin, plain_pin):
    old, new = previous['manifest'], plain['manifest']
    for item in (previous, plain):
        validate_manifest(item['manifest'])
        validate_profile(item['compose'], item['manifest'])
    if checksum(previous) != previous_pin or checksum(plain) != plain_pin:
        raise ValueError('voice_exact_bundles_required')
    fixed = ('migration_hash', 'database_image', 'redis_image', 'data_root',
             'control_uid', 'execution_uid', 'owner_login')
    if (any(old.get(k) != new.get(k) for k in fixed) or old['revision'] == new['revision']
            or 'telegram' not in old or any(k in old for k in ('voice', 'planning', 'first_experiment'))
            or any(k in new for k in ('voice', 'telegram', 'planning', 'first_experiment'))):
        raise ValueError('voice_first_offline_addition_required')
    if (active.mode != 'live' or active.source_revision != old['revision']
            or active.token_file != '/run/telegram/token'
            or digest(active.model_dump()) != old['telegram']['connection_digest']
            or any(getattr(active, k) != old['telegram'][k] for k in ('mode', 'owner_id', 'bot_id'))):
        raise ValueError('voice_exact_owner_connection_required')
    staged = TelegramConnection.model_validate({**active.model_dump(), 'source_revision': new['revision']})
    target = deepcopy(plain)
    target['manifest']['telegram'] = {**old['telegram'], 'connection_digest': digest(staged.model_dump())}
    target['manifest']['voice'] = deepcopy(voice)
    target['compose'] = render(plain['compose'], target['manifest'])
    return target, staged


def prepare(previous_directory, plain_directory, output, voice, previous_pin, plain_pin):
    previous, plain = load_bundle(previous_directory), load_bundle(plain_directory)
    uid = plain['manifest']['control_uid']
    output = Path(output)
    info = output.parent.stat()
    if (os.getuid() != uid or not output.is_absolute() or output.resolve() != output
            or output.exists() or output.is_symlink() or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != uid or info.st_mode & 0o077):
        raise ValueError('voice_new_private_output_required')
    original = predecessor(previous, previous_directory, previous_pin)
    target, staged = assemble(previous, plain, original[2], voice, previous_pin, plain_pin)
    source_check(target['manifest'])
    check_binding(target['manifest'])
    for owner, images in ((uid, {**{k: target['manifest']['images'][k] for k in ('api', 'worker', 'broker')},
                                'voice': voice['image']}),
                          (target['manifest']['execution_uid'],
                           {k: target['manifest']['images'][k] for k in ('executor', 'coding')})):
        engine = Engine(owner)
        engine.preflight()
        image_check(engine, images, target['manifest']['revision'])
    if predecessor(previous, previous_directory, previous_pin) != original:
        raise ValueError('voice_predecessor_changed')
    source_check(target['manifest'])
    check_binding(target['manifest'])
    output.mkdir(mode=0o700)
    documents = {'previous.json': previous, 'plain.json': plain, 'bundle.json': target,
                 'compose.json': target['compose'], 'connection.candidate.json': staged.model_dump()}
    for name, value in documents.items():
        atomic_json(output / name, value)
    receipt = {'schema': 1, 'purpose': PURPOSE, 'state': 'STAGED_NOT_ACTIVATED',
        'previous_bundle': previous_pin, 'plain_bundle': plain_pin, 'candidate_bundle': checksum(target),
        'files': {k: raw_pin(v) for k, v in documents.items()},
        'voice_capability': digest(voice), 'paid_calls': 0, 'deployment_authorized': False,
        'task_admission_resumed': False}
    atomic_json(output / 'preparation.json', receipt)
    return {'status': 'VOICE_CANDIDATE_PREPARED_NOT_APPLIED', 'candidate_bundle': checksum(target),
            'preparation_digest': checksum(receipt), 'voice_capability': digest(voice), 'paid_calls': 0}


def inspect(directory, candidate_pin, preparation_pin):
    path = Path(directory)
    receipt = read_json(path / 'preparation.json')
    documents = {k: read_json(path / k, 1024 * 1024) for k in FILES}
    previous, plain = documents['previous.json'], documents['plain.json']
    voice = documents['bundle.json']['manifest']['voice']
    target, staged = assemble(previous, plain, TelegramConnection.model_validate({
        **documents['connection.candidate.json'], 'source_revision': previous['manifest']['revision']}),
        voice, receipt['previous_bundle'], receipt['plain_bundle'])
    expected = {'schema': 1, 'purpose': PURPOSE, 'state': 'STAGED_NOT_ACTIVATED',
        'previous_bundle': receipt['previous_bundle'], 'plain_bundle': receipt['plain_bundle'],
        'candidate_bundle': checksum(target), 'files': {k: raw_pin(v) for k, v in documents.items()},
        'voice_capability': digest(voice), 'paid_calls': 0, 'deployment_authorized': False,
        'task_admission_resumed': False}
    if (receipt != expected or checksum(receipt) != preparation_pin or checksum(target) != candidate_pin
            or documents['bundle.json'] != target or documents['compose.json'] != target['compose']
            or documents['connection.candidate.json'] != staged.model_dump()):
        raise ValueError('voice_candidate_changed')
    allowed = FILES | {'preparation.json', 'activation.json', 'connection.previous.json'}
    if set(p.name for p in path.iterdir()) - allowed:
        raise ValueError('voice_inventory_changed')
    for item in (path, *path.iterdir()):
        info = item.lstat()
        if (item.resolve() != item or info.st_uid != os.getuid() or info.st_mode & 0o077
                or item != path and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)):
            raise ValueError('voice_private_custody_required')
    if (path / 'activation.json').exists():
        activation = read_json(path / 'activation.json')
        if (activation.get('purpose') != PURPOSE or activation.get('target') != candidate_pin
                or activation.get('previous') != checksum(previous)
                or activation.get('preparation_digest') != preparation_pin
                or activation.get('voice_capability') != digest(voice)
                or activation.get('phase') not in {'PREPARED', 'BINDING_ACTIVE', 'DEPLOYMENT_ATTEMPTED', 'VERIFIED'}
                or activation.get('paid_calls') != 0 or activation.get('task_admission_resumed') is not False):
            raise ValueError('voice_activation_scope_changed')
    if (path / 'connection.previous.json').exists() and read_json(path / 'connection.previous.json') != {
            **staged.model_dump(), 'source_revision': previous['manifest']['revision']}:
        raise ValueError('voice_previous_connection_changed')
    load_bundle(directory)
    source_check(target['manifest'])
    check_binding(target['manifest'])
    engine = Engine(target['manifest']['control_uid'])
    engine.preflight()
    image_check(engine, {'voice': voice['image']}, target['manifest']['revision'])
    return {'status': 'VOICE_CANDIDATE_INSPECTED_NOT_APPLIED', 'candidate_bundle': candidate_pin,
            'preparation_digest': preparation_pin, 'voice_capability': digest(voice), 'paid_calls': 0}
