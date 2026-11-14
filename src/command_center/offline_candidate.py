"""Remove expired optional AI bindings while retaining exact deployment interlocks."""
from copy import deepcopy
import os
from pathlib import Path
import stat

from .deployment import Engine, image_check, load_bundle, source_check
from .deployment_profile import atomic_json, checksum, render, validate_manifest, validate_profile
from .planning_candidate import predecessor, raw_pin, read_json
from .store import digest
from .telegram_transport import TelegramConnection

PURPOSE = 'offline-code-update.v1'
FILES = {'previous.json', 'disabled.json', 'bundle.json', 'compose.json', 'connection.candidate.json'}


def assemble(previous, disabled, active, previous_pin, disabled_pin):
    old, new = previous['manifest'], disabled['manifest']
    for b in (previous, disabled):
        validate_manifest(b['manifest'])
        validate_profile(b['compose'], b['manifest'])
    if checksum(previous) != previous_pin or checksum(disabled) != disabled_pin:
        raise ValueError('offline_exact_bundle_required')
    fixed = ('migration_hash', 'database_image', 'redis_image', 'data_root',
             'control_uid', 'execution_uid', 'owner_login')
    if (any(old.get(k) != new.get(k) for k in fixed) or 'planning' not in old
            or 'first_experiment' in old or 'telegram' not in old
            or any(k in new for k in ('planning', 'first_experiment', 'telegram'))
            or old['revision'] == new['revision']):
        raise ValueError('offline_restriction_only_transition_required')
    if (active.mode != 'live' or active.source_revision != old['revision']
            or active.token_file != '/run/telegram/token'
            or digest(active.model_dump()) != old['telegram']['connection_digest']
            or any(getattr(active, k) != old['telegram'][k] for k in ('mode', 'owner_id', 'bot_id'))):
        raise ValueError('offline_exact_owner_connection_required')
    staged = TelegramConnection.model_validate({**active.model_dump(), 'source_revision': new['revision']})
    target = deepcopy(disabled)
    target['manifest']['telegram'] = {**old['telegram'], 'connection_digest': digest(staged.model_dump())}
    target['compose'] = render(disabled['compose'], target['manifest'])
    validate_profile(target['compose'], target['manifest'])
    return target, staged


def prepare(previous_directory, disabled_directory, output, previous_pin, disabled_pin):
    previous, disabled = load_bundle(previous_directory), load_bundle(disabled_directory)
    uid = disabled['manifest']['control_uid']
    output = Path(output)
    parent = output.parent.stat()
    if (os.getuid() != uid or not output.is_absolute() or output.resolve() != output
            or output.exists() or output.is_symlink() or not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != uid or parent.st_mode & 0o077):
        raise ValueError('offline_new_private_output_required')
    original = predecessor(previous, previous_directory, previous_pin)
    target, staged = assemble(previous, disabled, original[2], previous_pin, disabled_pin)
    source_check(target['manifest'])
    for uid, names in ((uid, {'api', 'worker', 'broker'}),
                       (target['manifest']['execution_uid'], {'executor', 'coding'})):
        engine = Engine(uid)
        engine.preflight()
        image_check(engine, {k: target['manifest']['images'][k] for k in names}, target['manifest']['revision'])
    if predecessor(previous, previous_directory, previous_pin) != original:
        raise ValueError('offline_predecessor_changed')
    source_check(target['manifest'])
    output.mkdir(mode=0o700)
    documents = {'previous.json': previous, 'disabled.json': disabled, 'bundle.json': target,
                 'compose.json': target['compose'], 'connection.candidate.json': staged.model_dump()}
    for name, value in documents.items():
        atomic_json(output / name, value)
    receipt = {'schema': 1, 'purpose': PURPOSE, 'state': 'STAGED_NOT_ACTIVATED',
        'previous_bundle': previous_pin, 'disabled_bundle': disabled_pin, 'candidate_bundle': checksum(target),
        'files': {k: raw_pin(v) for k, v in documents.items()}, 'provider_bindings_removed': True,
        'deployment_authorized': False, 'task_admission_resumed': False, 'paid_calls': 0}
    atomic_json(output / 'preparation.json', receipt)
    return {'status': 'OFFLINE_CANDIDATE_PREPARED_NOT_APPLIED', 'candidate_bundle': checksum(target),
            'preparation_digest': checksum(receipt), 'paid_calls': 0}


def inspect(directory, candidate_pin, preparation_pin):
    path = Path(directory)
    receipt = read_json(path / 'preparation.json')
    documents = {k: read_json(path / k, 1024 * 1024) for k in FILES}
    previous, disabled = documents['previous.json'], documents['disabled.json']
    target, staged = assemble(previous, disabled, TelegramConnection.model_validate({
        **documents['connection.candidate.json'], 'source_revision': previous['manifest']['revision']}),
        receipt['previous_bundle'], receipt['disabled_bundle'])
    expected = {'schema': 1, 'purpose': PURPOSE, 'state': 'STAGED_NOT_ACTIVATED',
        'previous_bundle': checksum(previous), 'disabled_bundle': checksum(disabled),
        'candidate_bundle': checksum(target), 'files': {k: raw_pin(v) for k, v in documents.items()},
        'provider_bindings_removed': True, 'deployment_authorized': False,
        'task_admission_resumed': False, 'paid_calls': 0}
    if (receipt != expected or checksum(receipt) != preparation_pin or checksum(target) != candidate_pin
            or target != documents['bundle.json'] or target['compose'] != documents['compose.json']
            or staged.model_dump() != documents['connection.candidate.json']):
        raise ValueError('offline_preparation_changed')
    allowed = FILES | {'preparation.json', 'activation.json', 'connection.previous.json'}
    if set(p.name for p in path.iterdir()) - allowed:
        raise ValueError('offline_inventory_changed')
    for p in (path, *path.iterdir()):
        info = p.lstat()
        if (p.resolve() != p or info.st_uid != os.getuid() or info.st_mode & 0o077
                or p != path and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)):
            raise ValueError('offline_private_custody_required')
    if (path / 'activation.json').exists():
        a = read_json(path / 'activation.json')
        if (a.get('purpose') != PURPOSE or a.get('target') != candidate_pin
                or a.get('phase') not in {'PREPARED', 'BINDING_ACTIVE', 'DEPLOYMENT_ATTEMPTED', 'VERIFIED'}
                or a.get('previous') != checksum(previous) or a.get('preparation_digest') != preparation_pin
                or a.get('provider_bindings_removed') is not True or a.get('paid_calls') != 0
                or a.get('task_admission_resumed') is not False):
            raise ValueError('offline_activation_scope_changed')
    if (path / 'connection.previous.json').exists() and read_json(path / 'connection.previous.json') != {
            **staged.model_dump(), 'source_revision': previous['manifest']['revision']}:
        raise ValueError('offline_previous_connection_changed')
    source_check(target['manifest'])
    return {'status': 'OFFLINE_CANDIDATE_INSPECTED', 'candidate_bundle': candidate_pin,
            'preparation_digest': preparation_pin, 'paid_calls': 0}
